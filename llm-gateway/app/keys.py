"""Dashboard API: create / list / revoke the user's own gateway keys, and show usage."""

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from auth import current_user
from config import settings
from db import DB, ApiKey, RequestLog, User, get_db, utcnow
from security import display_prefix, generate_api_key, hash_api_key, redis

router = APIRouter(prefix="/api", tags=["dashboard"])


class NewKey(BaseModel):
    model_config = {"json_schema_extra": {"examples": [{"name": "my-app", "rpm_limit": 60, "budget_usd": 5}]}}

    name: str = Field(default="default", min_length=1, max_length=100)
    rpm_limit: int = Field(default=settings.default_rpm_limit, ge=1, le=10000)
    budget_usd: float | None = Field(default=None, gt=0)
    expires_days: int | None = Field(default=None, ge=1, le=3650)


def _key_out(k: ApiKey) -> dict:
    return {
        "id": k.id,
        "name": k.name,
        "prefix": k.prefix,
        "revoked": k.revoked,
        "expires_at": k.expires_at,
        "rpm_limit": k.rpm_limit,
        "budget_usd": k.budget_usd,
        "spent_usd": round(k.spent_usd, 6),
        "last_used_at": k.last_used_at,
        "created_at": k.created_at,
    }


@router.get("/keys")
async def list_keys(user: User = Depends(current_user), db: DB = Depends(get_db)):
    rows = await db.scalars(select(ApiKey).where(ApiKey.user_id == user.id).order_by(ApiKey.id.desc()))
    return [_key_out(k) for k in rows]


@router.post("/keys")
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
    )
    db.add(key)
    await db.commit()
    # The raw key is returned only here; afterwards only its hash exists.
    return {**_key_out(key), "key": raw}


@router.delete("/keys/{key_id}")
async def revoke_key(key_id: int, user: User = Depends(current_user), db: DB = Depends(get_db)):
    key = await db.get(ApiKey, key_id)
    if not key or key.user_id != user.id:
        raise HTTPException(404, "Key not found")
    key.revoked = True
    await db.commit()
    await redis.delete(f"key:{key.key_hash}")
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
                func.coalesce(func.avg(RequestLog.latency_ms), 0),
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
            "avg_latency_ms": int(totals[5]),
        },
        "by_model": [
            {"model": m, "requests": n, "tokens": int(t), "cost_usd": round(float(c), 6)} for m, n, t, c in by_model
        ],
        "recent": [
            {
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
