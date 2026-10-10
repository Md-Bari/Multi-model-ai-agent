"""Shared Redis client. Modules use `clients.redis` (attribute access) so tests can swap it."""

import redis.asyncio as aioredis

from app.config import settings

redis: aioredis.Redis = aioredis.from_url(
    settings.redis_url,
    decode_responses=True,
    health_check_interval=30,  # hosted Redis (Upstash) drops idle connections
    socket_keepalive=True,
)
