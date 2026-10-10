"""Detailed usage analytics for the dashboard: requests and tokens over time with filters,
breakdowns by model and key, and live rate-limit usage per key."""

from datetime import datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func, literal, select, text

from app.config import settings
from app.db import DB, engine, get_db
from app.models import ApiKey, RequestLog, User, utcnow
from app.routers.auth import current_user
from app.services import ratelimit

router = APIRouter(prefix="/api/usage", tags=["dashboard"])

Range = Literal["24h", "7d", "28d", "90d"]
RANGES: dict[str, tuple[str, int]] = {"24h": ("hour", 24), "7d": ("day", 7), "28d": ("day", 28), "90d": ("day", 90)}
FORMATS = {"hour": "%Y-%m-%dT%H:00", "day": "%Y-%m-%d"}


def _bucket(unit: str, offset_minutes: int):
    """SQL expression for the start of each bucket in the viewer's local time, as text
    (Postgres in production, SQLite in tests)."""
    if engine.dialect.name == "postgresql":
        local = func.timezone("UTC", RequestLog.created_at) + timedelta(minutes=offset_minutes)
        return func.to_char(func.date_trunc(unit, local), 'YYYY-MM-DD"T"HH24:00' if unit == "hour" else "YYYY-MM-DD")
    return func.strftime(FORMATS[unit], RequestLog.created_at, f"{offset_minutes:+d} minutes")


def _window(unit: str, count: int, offset_minutes: int) -> tuple[list[str], datetime]:
    """Bucket labels (local time, oldest first) and the UTC instant the first bucket starts."""
    offset = timedelta(minutes=offset_minutes)
    now_local = utcnow() + offset
    if unit == "hour":
        current = now_local.replace(minute=0, second=0, microsecond=0)
        step = timedelta(hours=1)
    else:
        current = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        step = timedelta(days=1)
    first = current - step * (count - 1)
    labels = [(first + step * i).strftime(FORMATS[unit]) for i in range(count)]
    return labels, first - offset


def _metrics():
    """Aggregates shared by every breakdown."""
    return (
        func.count(RequestLog.id).label("requests"),
        func.coalesce(func.sum(case((RequestLog.cached, 1), else_=0)), 0).label("cached"),
        func.coalesce(func.sum(case((RequestLog.status != "ok", 1), else_=0)), 0).label("errors"),
        func.coalesce(func.sum(RequestLog.prompt_tokens), 0).label("input_tokens"),
        func.coalesce(func.sum(RequestLog.completion_tokens), 0).label("output_tokens"),
        func.coalesce(func.sum(RequestLog.cost_usd), 0.0).label("cost_usd"),
        func.coalesce(func.avg(case((~RequestLog.cached, RequestLog.latency_ms))), 0).label("avg_latency_ms"),
    )


def _row(r) -> dict:
    return {
        "requests": int(r.requests),
        "cached": int(r.cached),
        "errors": int(r.errors),
        "input_tokens": int(r.input_tokens),
        "output_tokens": int(r.output_tokens),
        "cost_usd": round(float(r.cost_usd), 6),
        "avg_latency_ms": int(r.avg_latency_ms or 0),
    }


@router.get("/timeseries")
async def timeseries(
    range: Range = "7d",  # noqa: A002 - matches the query parameter name
    model: str | None = Query(default=None, description="Filter by model name"),
    key: str | None = Query(default=None, description="Key id, or 'playground'"),
    tz_offset: int = Query(default=0, ge=-14 * 60, le=14 * 60, description="Viewer's UTC offset in minutes"),
    user: User = Depends(current_user),
    db: DB = Depends(get_db),
):
    unit, count = RANGES[range]
    labels, since = _window(unit, count, tz_offset)

    filters = [RequestLog.user_id == user.id, RequestLog.created_at >= since]
    if model:
        filters.append(RequestLog.model == model)
    if key == "playground":
        filters.append(RequestLog.key_id.is_(None))
    elif key and key.isdigit():
        filters.append(RequestLog.key_id == int(key))

    bucket = _bucket(unit, tz_offset).label("bucket")
    # Group by the alias: repeating the expression would bind its parameters twice,
    # which Postgres treats as a different expression.
    rows = await db.execute(select(bucket, *_metrics()).where(*filters).group_by(text("bucket")))
    by_bucket = {r.bucket: _row(r) for r in rows}
    empty = {"requests": 0, "cached": 0, "errors": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0, "avg_latency_ms": 0}
    buckets = [{"t": label, **by_bucket.get(label, empty)} for label in labels]

    totals = {
        field: sum(b[field] for b in buckets) for field in ("requests", "cached", "errors", "input_tokens", "output_tokens")
    }
    totals["cost_usd"] = round(sum(b["cost_usd"] for b in buckets), 6)

    by_model = await db.execute(
        select(RequestLog.model, *_metrics())
        .where(*filters)
        .group_by(RequestLog.model)
        .order_by(func.count(RequestLog.id).desc())
    )
    by_key = await db.execute(
        select(RequestLog.key_id, func.coalesce(ApiKey.name, literal("Playground")).label("name"), *_metrics())
        .outerjoin(ApiKey, ApiKey.id == RequestLog.key_id)
        .where(*filters)
        .group_by(RequestLog.key_id, ApiKey.name)
        .order_by(func.count(RequestLog.id).desc())
    )

    all_models = await db.scalars(
        select(RequestLog.model).where(RequestLog.user_id == user.id, RequestLog.model != "none").distinct()
    )
    all_keys = await db.execute(select(ApiKey.id, ApiKey.name).where(ApiKey.user_id == user.id).order_by(ApiKey.id.desc()))

    return {
        "range": range,
        "unit": unit,
        "buckets": buckets,
        "totals": totals,
        "by_model": [{"model": r.model, **_row(r)} for r in by_model],
        "by_key": [{"key_id": r.key_id, "name": r.name, **_row(r)} for r in by_key],
        "filters": {
            "models": sorted(all_models),
            "keys": [{"id": k.id, "name": k.name} for k in all_keys],
        },
    }


@router.get("/limits")
async def limits(user: User = Depends(current_user), db: DB = Depends(get_db)):
    """Each active key's live requests-per-minute against its limit, plus last-24h load."""
    day_ago = utcnow() - timedelta(hours=24)
    keys = list(
        await db.scalars(select(ApiKey).where(ApiKey.user_id == user.id, ApiKey.revoked.is_(False)).order_by(ApiKey.id.desc()))
    )
    load = {
        r.key_id: r
        for r in await db.execute(
            select(
                RequestLog.key_id,
                func.count(RequestLog.id).label("requests"),
                func.coalesce(func.sum(RequestLog.prompt_tokens + RequestLog.completion_tokens), 0).label("tokens"),
            )
            .where(RequestLog.user_id == user.id, RequestLog.created_at >= day_ago)
            .group_by(RequestLog.key_id)
        )
    }

    def entry(name: str, key_id: int | None, rpm_limit: int, current: int, extra: dict) -> dict:
        r = load.get(key_id)
        return {
            "key_id": key_id,
            "name": name,
            "rpm_limit": rpm_limit,
            "requests_this_minute": current,
            "requests_24h": int(r.requests) if r else 0,
            "tokens_24h": int(r.tokens) if r else 0,
            **extra,
        }

    now = utcnow()
    out = []
    for k in keys:
        # SQLite (tests) returns naive datetimes; Postgres returns aware ones.
        if k.expires_at and k.expires_at.replace(tzinfo=now.tzinfo) < now:
            continue
        current = await ratelimit.peek(f"key:{k.id}", 60)
        out.append(entry(k.name, k.id, k.rpm_limit, current, {"budget_usd": k.budget_usd, "spent_usd": round(k.spent_usd, 6)}))
    current = await ratelimit.peek(f"user:{user.id}", 60)
    out.append(entry("Playground", None, settings.playground_rpm_limit, current, {"budget_usd": None, "spent_usd": None}))
    return out
