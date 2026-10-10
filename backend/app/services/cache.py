"""Response cache in Redis. Prompts are normalized (case, whitespace) so near-identical
questions share an answer."""

import hashlib
import json

from app import clients
from app.config import settings
from app.services.llm import message_text


def _normalize(messages: list[dict]) -> list[dict]:
    return [{"role": m.get("role"), "content": " ".join(message_text(m.get("content")).lower().split())} for m in messages]


def make_key(tier: str, messages: list[dict], params: dict) -> str:
    payload = json.dumps({"t": tier, "m": _normalize(messages), "p": params}, sort_keys=True, ensure_ascii=False)
    return "cache:" + hashlib.sha256(payload.encode()).hexdigest()


async def get(key: str) -> dict | None:
    if settings.cache_ttl_seconds <= 0:
        return None
    raw = await clients.redis.get(key)
    return json.loads(raw) if raw else None


async def put(key: str, content: str, model: str) -> None:
    if settings.cache_ttl_seconds <= 0 or not content:
        return
    await clients.redis.set(key, json.dumps({"content": content, "model": model}), ex=settings.cache_ttl_seconds)
