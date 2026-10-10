"""Fixed-window counters in Redis."""

import time

from app import clients


async def hit(bucket: str, window_seconds: int) -> int:
    """Count one hit in the current window and return the total so far."""
    key = f"rl:{bucket}:{int(time.time() // window_seconds)}"
    async with clients.redis.pipeline(transaction=True) as pipe:
        pipe.incr(key)
        pipe.expire(key, window_seconds)
        count, _ = await pipe.execute()
    return int(count)


async def peek(bucket: str, window_seconds: int) -> int:
    value = await clients.redis.get(f"rl:{bucket}:{int(time.time() // window_seconds)}")
    return int(value or 0)
