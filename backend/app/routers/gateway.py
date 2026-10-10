"""The OpenAI-compatible API that apps call with their sk-mysite-... key."""

import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select

from app import clients
from app.config import settings
from app.db import SessionLocal
from app.models import ApiKey, User, utcnow
from app.security import KEY_PREFIX, hash_api_key
from app.services.accounting import Principal
from app.services.chat import ChatRequest, enforce_limits, run_chat
from app.services.llm import TIERS

router = APIRouter(prefix="/v1", tags=["gateway"])

# Registers a Bearer scheme in OpenAPI, so Swagger UI shows an "Authorize" button.
bearer = HTTPBearer(auto_error=False, scheme_name="GatewayKey", description="Your sk-mysite-... key from the dashboard")


async def _load_key(key_hash: str) -> dict | None:
    cached = await clients.redis.get(f"key:{key_hash}")
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
    await clients.redis.set(f"key:{key_hash}", json.dumps(info), ex=settings.key_cache_ttl_seconds)
    return info


async def authenticate(creds: HTTPAuthorizationCredentials | None = Depends(bearer)) -> Principal:
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

    principal = Principal(
        user_id=info["user_id"],
        key_id=info["id"],
        rpm_limit=info["rpm_limit"],
        budget_usd=info["budget_usd"],
        spent_usd=info["spent_usd"],
    )
    await enforce_limits(principal)
    return principal


@router.get("/models")
async def list_models(_: Principal = Depends(authenticate)):
    return {"object": "list", "data": [{"id": name, "object": "model", "owned_by": "gateway"} for name in ("auto", *TIERS)]}


@router.post("/chat/completions")
async def chat_completions(req: ChatRequest, principal: Principal = Depends(authenticate)):
    return await run_chat(principal, req)
