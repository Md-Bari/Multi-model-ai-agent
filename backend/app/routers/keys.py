"""Dashboard API: the user's own gateway keys, usage stats, and the playground."""

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app import clients
from app.config import settings
from app.db import DB, get_db
from app.models import ApiKey, RequestLog, User, utcnow
from app.routers.auth import current_user
from app.security import display_prefix, generate_api_key, hash_api_key
from app.services.accounting import Principal
from app.services.chat import ChatRequest, enforce_limits, run_chat
from app.services.llm import TIERS, chain_for

router = APIRouter(prefix="/api", tags=["dashboard"])


class NewKey(BaseModel):
    model_config = {"json_schema_extra": {"examples": [{"name": "my-app", "rpm_limit": 60, "budget_usd": 5}]}}

    name: str = Field(default="default", min_length=1, max_length=100)
    rpm_limit: int = Field(default=settings.default_rpm_limit, ge=1, le=10000)
    budget_usd: float | None = Field(default=None, gt=0)
    expires_days: int | None = Field(default=None, ge=1, le=3650)


class KeyOut(BaseModel):
    id: int
    name: str
    prefix: str
    revoked: bool
    expires_at: datetime | None
    rpm_limit: int
    budget_usd: float | None
    spent_usd: float
    last_used_at: datetime | None
    created_at: datetime


class CreatedKey(KeyOut):
    key: str = Field(description="The raw key. Shown only once.")


@router.get("/keys", response_model=list[KeyOut])
async def list_keys(user: User = Depends(current_user), db: DB = Depends(get_db)):
    return list(await db.scalars(select(ApiKey).where(ApiKey.user_id == user.id).order_by(ApiKey.id.desc())))


@router.post("/keys", response_model=CreatedKey, status_code=201)
async def create_key(body: NewKey, user: User = Depends(current_user), db: DB = Depends(get_db)):
    raw = generate_api_key()
    key = ApiKey(
        user_id=user.id,
        name=body.name,
        key_hash=hash_api_key(raw),
        prefix=display_prefix(raw),
        rpm_limit=body.rpm_limit,
        budget_usd=body.budget_usd,
        expires_at=utcnow() + timedelta(days=body.expires_days) if body.expires_days else None,
        spent_usd=0.0,
        revoked=False,
    )
    db.add(key)
    await db.commit()
    await db.refresh(key)
    # The raw key is returned only here; afterwards only its hash exists.
    return CreatedKey(**KeyOut.model_validate(key, from_attributes=True).model_dump(), key=raw)


@router.delete("/keys/{key_id}")
async def revoke_key(key_id: int, user: User = Depends(current_user), db: DB = Depends(get_db)):
    key = await db.get(ApiKey, key_id)
    if not key or key.user_id != user.id:
        raise HTTPException(404, "Key not found")
    key.revoked = True
    await db.commit()
    await clients.redis.delete(f"key:{key.key_hash}")
    return {"ok": True}


@router.get("/usage")
async def usage(user: User = Depends(current_user), db: DB = Depends(get_db)):
    mine = RequestLog.user_id == user.id
    totals = (
        await db.execute(
            select(
                func.count(RequestLog.id),
                func.coalesce(func.sum(RequestLog.prompt_tokens), 0),
                func.coalesce(func.sum(RequestLog.completion_tokens), 0),
                func.coalesce(func.sum(RequestLog.cost_usd), 0.0),
                func.count(RequestLog.id).filter(RequestLog.cached),
                func.count(RequestLog.id).filter(RequestLog.status != "ok"),
                func.coalesce(func.avg(RequestLog.latency_ms).filter(~RequestLog.cached), 0),
            ).where(mine)
        )
    ).one()

    by_model = await db.execute(
        select(
            RequestLog.model,
            func.count(RequestLog.id),
            func.coalesce(func.sum(RequestLog.prompt_tokens + RequestLog.completion_tokens), 0),
            func.coalesce(func.sum(RequestLog.cost_usd), 0.0),
        )
        .where(mine)
        .group_by(RequestLog.model)
        .order_by(func.count(RequestLog.id).desc())
    )

    recent = await db.scalars(select(RequestLog).where(mine).order_by(RequestLog.id.desc()).limit(50))
    return {
        "totals": {
            "requests": totals[0],
            "prompt_tokens": int(totals[1]),
            "completion_tokens": int(totals[2]),
            "cost_usd": round(float(totals[3]), 6),
            "cache_hits": totals[4],
            "errors": totals[5],
            "avg_latency_ms": int(totals[6] or 0),
        },
        "by_model": [{"model": m, "requests": n, "tokens": int(t), "cost_usd": round(float(c), 6)} for m, n, t, c in by_model],
        "recent": [
            {
                "id": r.id,
                "created_at": r.created_at,
                "key_id": r.key_id,
                "tier": r.tier,
                "model": r.model,
                "prompt_tokens": r.prompt_tokens,
                "completion_tokens": r.completion_tokens,
                "cost_usd": round(r.cost_usd, 6),
                "latency_ms": r.latency_ms,
                "cached": r.cached,
                "status": r.status,
            }
            for r in recent
        ],
    }


@router.get("/providers")
async def providers(_: User = Depends(current_user)):
    return {tier: [{"name": d.name, "provider": d.provider, "model": d.model} for d in chain_for(tier)] for tier in TIERS}


@router.post("/playground/chat")
async def playground_chat(req: ChatRequest, user: User = Depends(current_user)):
    """Same pipeline as /v1/chat/completions, authenticated by the dashboard session."""
    principal = Principal(user_id=user.id, key_id=None, rpm_limit=settings.playground_rpm_limit)
    await enforce_limits(principal)
    return await run_chat(principal, req)
