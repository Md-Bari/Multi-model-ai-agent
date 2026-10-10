"""The request pipeline shared by the public API (/v1) and the dashboard playground:
rate limit -> budget -> route -> cache -> LangChain provider (with fallback)
-> stream back + cache -> record tokens / cost / latency."""

import json
import logging
import time
import uuid
from collections.abc import AsyncIterator
from typing import Literal

from fastapi import HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from langchain_core.messages import AIMessageChunk, convert_to_messages
from pydantic import BaseModel, Field

from app.services import cache, ratelimit
from app.services.accounting import Principal, current_spend, in_background, record_usage
from app.services.llm import TIERS, AllProvidersFailed, Deployment, chain_for, pick_tier, stream_with_fallback
from app.services.pricing import cost_usd, estimate_tokens

log = logging.getLogger(__name__)


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str | list[dict]


class ChatRequest(BaseModel):
    model_config = {
        "json_schema_extra": {
            "examples": [
                {"model": "auto", "stream": False, "messages": [{"role": "user", "content": "What is the capital of France?"}]}
            ]
        }
    }

    model: str = Field(default="auto", description="auto (gateway picks), cheap or strong")
    messages: list[ChatMessage] = Field(min_length=1, max_length=200)
    stream: bool = False
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1, le=32000)
    stop: str | list[str] | None = None


async def enforce_limits(p: Principal) -> None:
    if await ratelimit.hit(p.bucket, 60) > p.rpm_limit:
        raise HTTPException(429, f"Rate limit exceeded ({p.rpm_limit} requests/minute)", headers={"Retry-After": "60"})
    if p.budget_usd is not None and await current_spend(p) >= p.budget_usd:
        raise HTTPException(402, "Budget exhausted for this key")


def _chunk_text(chunk: AIMessageChunk) -> str:
    return chunk.text if isinstance(chunk.text, str) else ""


def _completion(content: str, model: str, prompt_tokens: int, completion_tokens: int, finish: str = "stop") -> dict:
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": finish}],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }


def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


def _chunk_event(cid: str, model: str, delta: dict, finish: str | None = None, usage: dict | None = None) -> str:
    event = {
        "id": cid,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
    }
    if usage:
        event["usage"] = usage
    return _sse(event)


async def _stream_cached(content: str, model: str) -> AsyncIterator[str]:
    cid = f"chatcmpl-{uuid.uuid4().hex[:24]}"
    yield _chunk_event(cid, model, {"role": "assistant", "content": content})
    yield _chunk_event(cid, model, {}, "stop")
    yield "data: [DONE]\n\n"


class _Collector:
    """Merges LangChain chunks (which also sums usage_metadata) as they pass through."""

    def __init__(self, prompt_text: str):
        self.merged: AIMessageChunk | None = None
        self.prompt_text = prompt_text

    def add(self, chunk: AIMessageChunk) -> str:
        self.merged = chunk if self.merged is None else self.merged + chunk
        return _chunk_text(chunk)

    @property
    def content(self) -> str:
        return _chunk_text(self.merged) if self.merged else ""

    def usage(self) -> tuple[int, int]:
        meta = self.merged.usage_metadata if self.merged else None
        if meta and meta.get("output_tokens"):
            return meta.get("input_tokens", 0), meta["output_tokens"]
        return estimate_tokens(self.prompt_text), estimate_tokens(self.content)


async def run_chat(p: Principal, req: ChatRequest) -> JSONResponse | StreamingResponse:
    started = time.perf_counter()

    def elapsed_ms() -> int:
        return int((time.perf_counter() - started) * 1000)

    raw_messages = [m.model_dump() for m in req.messages]

    # route
    if req.model == "auto":
        tier = pick_tier(raw_messages)
    elif req.model in TIERS:
        tier = req.model
    else:
        raise HTTPException(400, f"Unknown model '{req.model}'. Use one of: auto, {', '.join(TIERS)}")
    if not chain_for(tier):
        raise HTTPException(503, "No LLM provider configured on the server")

    stop = [req.stop] if isinstance(req.stop, str) else req.stop
    params = {
        k: v for k, v in {"temperature": req.temperature, "max_tokens": req.max_tokens, "stop": stop}.items() if v is not None
    }
    headers = {"X-Gateway-Tier": tier}

    # cache
    cache_key = cache.make_key(tier, raw_messages, params)
    hit = await cache.get(cache_key)
    if hit:
        in_background(record_usage(p, tier=tier, model=hit["model"], latency_ms=elapsed_ms(), cached=True))
        headers |= {"X-Gateway-Cache": "HIT", "X-Gateway-Model": hit["model"]}
        if req.stream:
            return StreamingResponse(
                _stream_cached(hit["content"], hit["model"]), media_type="text/event-stream", headers=headers
            )
        return JSONResponse(_completion(hit["content"], hit["model"], 0, 0), headers=headers)

    # provider call (LangChain) with fallback
    try:
        dep, chunks = await stream_with_fallback(tier, convert_to_messages(raw_messages), **params)
    except AllProvidersFailed as e:
        in_background(record_usage(p, tier=tier, model="none", latency_ms=elapsed_ms(), status="error", error=str(e)))
        raise HTTPException(502, f"All providers failed: {e}") from e
    headers |= {"X-Gateway-Cache": "MISS", "X-Gateway-Model": dep.model, "X-Gateway-Provider": dep.provider}

    collector = _Collector(json.dumps(raw_messages, ensure_ascii=False))

    def finish(status: str = "ok", error: str | None = None) -> tuple[int, int]:
        pt, ct = collector.usage()
        if status == "ok":
            in_background(cache.put(cache_key, collector.content, dep.model))
        # Runs as a task so it still completes if the client disconnects.
        in_background(
            record_usage(
                p,
                tier=tier,
                model=dep.model,
                prompt_tokens=pt,
                completion_tokens=ct,
                cost=cost_usd(dep.model, pt, ct),
                latency_ms=elapsed_ms(),
                status=status,
                error=error,
            )
        )
        return pt, ct

    if not req.stream:
        try:
            async for chunk in chunks:
                collector.add(chunk)
        except Exception as e:  # noqa: BLE001 - provider broke mid-response
            finish("error", f"{type(e).__name__}: {e}")
            raise HTTPException(502, "Upstream provider failed mid-response") from e
        pt, ct = finish()
        return JSONResponse(_completion(collector.content, dep.model, pt, ct), headers=headers)

    return StreamingResponse(_stream_live(chunks, collector, dep, finish), media_type="text/event-stream", headers=headers)


async def _stream_live(
    chunks: AsyncIterator[AIMessageChunk], collector: _Collector, dep: Deployment, finish
) -> AsyncIterator[str]:
    cid = f"chatcmpl-{uuid.uuid4().hex[:24]}"
    done = False
    try:
        yield _chunk_event(cid, dep.model, {"role": "assistant", "content": ""})
        async for chunk in chunks:
            text = collector.add(chunk)
            if text:
                yield _chunk_event(cid, dep.model, {"content": text})
        pt, ct = finish()
        done = True
        usage = {"prompt_tokens": pt, "completion_tokens": ct, "total_tokens": pt + ct}
        yield _chunk_event(cid, dep.model, {}, "stop", usage)
        yield "data: [DONE]\n\n"
    except Exception as e:  # noqa: BLE001 - provider broke mid-stream
        log.warning("stream from %s failed: %s", dep.model, e)
        if not done:
            finish("error", f"{type(e).__name__}: {e}")
            done = True
        yield _sse({"error": {"message": "Upstream provider failed mid-stream", "type": "upstream_error"}})
    finally:
        if not done:  # client disconnected
            finish("error", "client disconnected")
