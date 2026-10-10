"""The OpenAI-compatible endpoint users call with their sk-mysite-... key.

Per request: verify key -> rate limit -> budget -> route -> cache -> provider (with fallback)
-> stream back + cache -> record tokens / cost / latency.
"""

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy import select, update

import cache
from config import settings
from db import ApiKey, RequestLog, SessionLocal, User, utcnow
from llm import CHAINS, TIERS, AllProvidersFailed, call_with_fallback, cost_usd, count_tokens, pick_tier
from security import KEY_PREFIX, hash_api_key, redis

log = logging.getLogger("gateway")
router = APIRouter(tags=["gateway"])

# Keeps references to post-response tasks so they aren't garbage-collected mid-flight.
_background: set[asyncio.Task] = set()


class ChatRequest(BaseModel):
    model_config = {
        "json_schema_extra": {
            "examples": [{"model": "auto", "stream": False, "messages": [{"role": "user", "content": "What is the capital of France?"}]}]
        }
    }

    model: str = "auto"  # "auto", "cheap" or "strong"
    messages: list[dict] = Field(min_length=1)
    stream: bool = False
    temperature: float | None = None
    max_tokens: int | None = None
    top_p: float | None = None
    stop: str | list[str] | None = None


# ---------- 1. key verification, rate limit, budget ----------


async def _load_key(key_hash: str) -> dict | None:
    cached = await redis.get(f"key:{key_hash}")
    if cached:
        return json.loads(cached)
    async with SessionLocal() as db:
        row = (
            await db.execute(
                select(ApiKey, User.is_active).join(User, User.id == ApiKey.user_id).where(ApiKey.key_hash == key_hash)
            )
        ).first()
    if not row:
        return None
    key, user_active = row
    info = {
        "id": key.id,
        "user_id": key.user_id,
        "revoked": key.revoked or not user_active,
        "expires_at": key.expires_at.isoformat() if key.expires_at else None,
        "rpm_limit": key.rpm_limit,
        "budget_usd": key.budget_usd,
        "spent_usd": key.spent_usd,
    }
    await redis.set(f"key:{key_hash}", json.dumps(info), ex=settings.key_cache_ttl_seconds)
    return info


async def _spent(info: dict) -> float:
    spend_key = f"spend:{info['id']}"
    value = await redis.get(spend_key)
    if value is None:
        # Seed the fast counter from Postgres (the source of truth).
        await redis.set(spend_key, info["spent_usd"], nx=True, ex=3600)
        value = await redis.get(spend_key)
    return float(value or 0)


# Registers a Bearer scheme in OpenAPI, so Swagger UI shows an "Authorize" button.
bearer = HTTPBearer(auto_error=False, scheme_name="GatewayKey", description="Your sk-mysite-... key from the dashboard")


async def authenticate(creds: HTTPAuthorizationCredentials | None = Depends(bearer)) -> dict:
    if not creds:
        raise HTTPException(401, "Missing 'Authorization: Bearer sk-mysite-...' header")
    raw = creds.credentials.strip()
    if not raw.startswith(KEY_PREFIX):
        raise HTTPException(401, "Invalid API key")

    info = await _load_key(hash_api_key(raw))
    if not info:
        raise HTTPException(401, "Invalid API key")
    if info["revoked"]:
        raise HTTPException(401, "API key revoked")
    if info["expires_at"] and datetime.fromisoformat(info["expires_at"]) < utcnow():
        raise HTTPException(401, "API key expired")

    window = f"rl:{info['id']}:{int(time.time() // 60)}"
    count = await redis.incr(window)
    if count == 1:
        await redis.expire(window, 60)
    if count > info["rpm_limit"]:
        raise HTTPException(429, f"Rate limit exceeded ({info['rpm_limit']} requests/minute)")

    if info["budget_usd"] is not None and await _spent(info) >= info["budget_usd"]:
        raise HTTPException(402, "Budget exhausted for this key")
    return info


# ---------- 6. accounting ----------


async def record_usage(
    info: dict,
    tier: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    cost: float,
    started: float,
    cached: bool,
    status: str = "ok",
    error: str | None = None,
) -> None:
    try:
        async with SessionLocal() as db:
            db.add(
                RequestLog(
                    user_id=info["user_id"],
                    key_id=info["id"],
                    tier=tier,
                    model=model,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    cost_usd=cost,
                    latency_ms=int((time.perf_counter() - started) * 1000),
                    cached=cached,
                    status=status,
                    error=error,
                )
            )
            await db.execute(
                update(ApiKey)
                .where(ApiKey.id == info["id"])
                .values(spent_usd=ApiKey.spent_usd + cost, last_used_at=utcnow())
            )
            await db.commit()
        if cost:
            spend_key = f"spend:{info['id']}"
            if await redis.exists(spend_key):
                await redis.incrbyfloat(spend_key, cost)
    except Exception:  # noqa: BLE001 - accounting must never break the user's response
        log.exception("failed to record usage")


def _in_background(coro) -> None:
    task = asyncio.create_task(coro)
    _background.add(task)
    task.add_done_callback(_background.discard)


# ---------- response helpers ----------


def _sse(obj) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


def _completion_json(content: str, model: str) -> dict:
    return {
        "id": f"chatcmpl-cache-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


async def _stream_cached(content: str, model: str):
    base = {"id": f"chatcmpl-cache-{uuid.uuid4().hex[:12]}", "object": "chat.completion.chunk", "created": int(time.time()), "model": model}
    yield _sse({**base, "choices": [{"index": 0, "delta": {"role": "assistant", "content": content}, "finish_reason": None}]})
    yield _sse({**base, "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]})
    yield "data: [DONE]\n\n"


async def _stream_live(chunks, info, tier, model, cache_key, messages, started):
    parts: list[str] = []
    prompt_tokens = completion_tokens = 0
    status, error = "ok", None
    try:
        async for chunk in chunks:
            if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                parts.append(chunk.choices[0].delta.content)
            usage = getattr(chunk, "usage", None)
            if usage:
                prompt_tokens = usage.prompt_tokens or prompt_tokens
                completion_tokens = usage.completion_tokens or completion_tokens
            yield f"data: {chunk.model_dump_json(exclude_none=True)}\n\n"
        yield "data: [DONE]\n\n"
    except Exception as e:  # noqa: BLE001 - provider broke mid-stream
        status, error = "error", f"{type(e).__name__}: {e}"
        log.warning("stream from %s failed: %s", model, e)
        yield _sse({"error": {"message": "Upstream provider failed mid-stream", "type": "upstream_error"}})
    finally:
        content = "".join(parts)
        if not completion_tokens and content:
            completion_tokens = count_tokens(model, content)
        if not prompt_tokens:
            prompt_tokens = count_tokens(model, json.dumps(messages, ensure_ascii=False))
        if status == "ok":
            _in_background(cache.put(cache_key, content, model))
        # Runs as a task so it still completes if the client disconnects.
        _in_background(
            record_usage(
                info, tier, model, prompt_tokens, completion_tokens,
                cost_usd(model, prompt_tokens, completion_tokens), started, False, status, error,
            )
        )


# ---------- the endpoint ----------


@router.get("/v1/models")
async def list_models(_: dict = Depends(authenticate)):
    return {
        "object": "list",
        "data": [{"id": name, "object": "model", "owned_by": "gateway"} for name in ("auto", *TIERS)],
    }


@router.post("/v1/chat/completions")
async def chat_completions(req: ChatRequest, info: dict = Depends(authenticate)):
    started = time.perf_counter()

    # 2. route
    if req.model == "auto":
        tier = pick_tier(req.messages)
    elif req.model in TIERS:
        tier = req.model
    else:
        raise HTTPException(400, f"Unknown model '{req.model}'. Use one of: auto, {', '.join(TIERS)}")
    if not CHAINS[tier]:
        raise HTTPException(503, "No LLM provider configured on the server")

    params = req.model_dump(include={"temperature", "max_tokens", "top_p", "stop"}, exclude_none=True)
    headers = {"X-Gateway-Tier": tier}

    # 3. cache
    cache_key = cache.make_key(tier, req.messages, params)
    hit = await cache.get(cache_key)
    if hit:
        _in_background(record_usage(info, tier, hit["model"], 0, 0, 0.0, started, cached=True))
        headers |= {"X-Gateway-Cache": "HIT", "X-Gateway-Model": hit["model"]}
        if req.stream:
            return StreamingResponse(_stream_cached(hit["content"], hit["model"]), media_type="text/event-stream", headers=headers)
        return JSONResponse(_completion_json(hit["content"], hit["model"]), headers=headers)

    # 4. provider call with fallback
    try:
        model, resp = await call_with_fallback(tier, req.messages, req.stream, params)
    except AllProvidersFailed as e:
        _in_background(record_usage(info, tier, "none", 0, 0, 0.0, started, False, "error", str(e)))
        raise HTTPException(502, f"All providers failed: {e}")
    headers |= {"X-Gateway-Cache": "MISS", "X-Gateway-Model": model}

    # 5. respond (+ cache) and 6. record
    if req.stream:
        return StreamingResponse(
            _stream_live(resp, info, tier, model, cache_key, req.messages, started),
            media_type="text/event-stream",
            headers=headers,
        )

    content = resp.choices[0].message.content or ""
    prompt_tokens = resp.usage.prompt_tokens if resp.usage else 0
    completion_tokens = resp.usage.completion_tokens if resp.usage else 0
    await cache.put(cache_key, content, model)
    _in_background(
        record_usage(info, tier, model, prompt_tokens, completion_tokens, cost_usd(model, prompt_tokens, completion_tokens), started, False)
    )
    return JSONResponse(resp.model_dump(exclude_none=True), headers=headers)
