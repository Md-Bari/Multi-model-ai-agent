"""Records tokens / cost / latency per request and keeps the per-key spend counter."""

import asyncio
import logging
from dataclasses import dataclass

from sqlalchemy import update

from app import clients
from app.db import SessionLocal
from app.models import ApiKey, RequestLog, utcnow

log = logging.getLogger(__name__)

# Keeps references to post-response tasks so they aren't garbage-collected mid-flight.
_background: set[asyncio.Task] = set()


@dataclass
class Principal:
    """Who is making the request: an API key, or a logged-in user in the playground."""

    user_id: int
    key_id: int | None
    rpm_limit: int
    budget_usd: float | None = None
    spent_usd: float = 0.0

    @property
    def bucket(self) -> str:
        return f"key:{self.key_id}" if self.key_id else f"user:{self.user_id}"


def spend_key(key_id: int) -> str:
    return f"spend:{key_id}"


async def current_spend(p: Principal) -> float:
    """Fast spend counter in Redis, seeded from Postgres (the source of truth)."""
    if p.key_id is None:
        return 0.0
    k = spend_key(p.key_id)
    value = await clients.redis.get(k)
    if value is None:
        await clients.redis.set(k, p.spent_usd, nx=True, ex=3600)
        value = await clients.redis.get(k)
    return float(value or 0)


async def record_usage(
    p: Principal,
    *,
    tier: str,
    model: str,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    cost: float = 0.0,
    latency_ms: int = 0,
    cached: bool = False,
    status: str = "ok",
    error: str | None = None,
) -> None:
    try:
        async with SessionLocal() as db:
            db.add(
                RequestLog(
                    user_id=p.user_id,
                    key_id=p.key_id,
                    tier=tier,
                    model=model,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    cost_usd=cost,
                    latency_ms=latency_ms,
                    cached=cached,
                    status=status,
                    error=error,
                )
            )
            if p.key_id is not None:
                await db.execute(
                    update(ApiKey).where(ApiKey.id == p.key_id).values(spent_usd=ApiKey.spent_usd + cost, last_used_at=utcnow())
                )
            await db.commit()
        if cost and p.key_id is not None and await clients.redis.exists(spend_key(p.key_id)):
            await clients.redis.incrbyfloat(spend_key(p.key_id), cost)
    except Exception:  # noqa: BLE001 - accounting must never break the user's response
        log.exception("failed to record usage")


def in_background(coro) -> None:
    task = asyncio.create_task(coro)
    _background.add(task)
    task.add_done_callback(_background.discard)


async def drain() -> None:
    """Wait for pending accounting tasks (used on shutdown and in tests)."""
    if _background:
        await asyncio.gather(*_background, return_exceptions=True)
