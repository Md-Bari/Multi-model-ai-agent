"""LLM access through LangChain: provider registry, cheap/strong routing, fallback and a
Redis-backed circuit breaker that skips a provider for a while after it fails."""

import logging
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessageChunk, BaseMessage

from app import clients
from app.config import settings

log = logging.getLogger(__name__)

TIERS = ("cheap", "strong")


@dataclass(frozen=True)
class Deployment:
    name: str  # e.g. "groq-fast"
    provider: str  # "groq" | "gemini"
    model: str  # provider model name, used for pricing and logs


def deployments() -> dict[str, Deployment]:
    """Only providers whose real key is configured are available."""
    d: dict[str, Deployment] = {}
    if settings.groq_api_key:
        d["groq-fast"] = Deployment("groq-fast", "groq", settings.groq_fast_model)
        d["groq-large"] = Deployment("groq-large", "groq", settings.groq_large_model)
    if settings.gemini_api_key:
        d["gemini"] = Deployment("gemini", "gemini", settings.gemini_model)
    return d


def chain_for(tier: str) -> list[Deployment]:
    """Deployments to try for a tier, in order. Any configured deployment not named in the
    tier's order is appended, so a single configured provider still serves every tier."""
    available = deployments()
    order = getattr(settings, f"tier_{tier}").split(",")
    names = [n.strip() for n in order if n.strip() in available]
    names += [n for n in available if n not in names]
    return [available[n] for n in names]


def build_chat_model(dep: Deployment, temperature: float | None, max_tokens: int | None) -> BaseChatModel:
    common = {
        "temperature": temperature,
        "max_tokens": max_tokens,
        "timeout": settings.llm_timeout_seconds,
        "max_retries": settings.llm_max_retries,
    }
    common = {k: v for k, v in common.items() if v is not None}
    if dep.provider == "groq":
        from langchain_groq import ChatGroq

        return ChatGroq(model=dep.model, api_key=settings.groq_api_key, **common)
    if dep.provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(model=dep.model, api_key=settings.gemini_api_key, **common)
    raise ValueError(f"unknown provider {dep.provider}")


# ---------- routing ----------

_CODE_HINTS = re.compile(
    r"```|\bdef |\bclass |\bfunction\b|\bimport |\breturn\b|traceback|exception|stack trace|"
    r"\bsql\b|\bregex\b|\bapi\b|\bbug\b|debug|refactor|compile|\bcode\b|python|javascript|typescript|"
    r"কোড|বাগ|প্রোগ্রাম",
    re.IGNORECASE,
)
_HARD_HINTS = re.compile(
    r"step by step|prove|proof|analy[sz]e|architecture|design a|optimi[sz]e|trade-?off|"
    r"explain why|compare|algorithm|mathemat|বিশ্লেষণ|প্রমাণ|ধাপে ধাপে|তুলনা",
    re.IGNORECASE,
)


def message_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):  # OpenAI multi-part content
        return " ".join(p.get("text", "") for p in content if isinstance(p, dict))
    return ""


def pick_tier(messages: list[dict]) -> str:
    last_user = next((message_text(m.get("content")) for m in reversed(messages) if m.get("role") == "user"), "")
    total = sum(len(message_text(m.get("content"))) for m in messages)
    if _CODE_HINTS.search(last_user) or _HARD_HINTS.search(last_user):
        return "strong"
    if len(last_user) > 1500 or total > 6000:
        return "strong"
    return "cheap"


# ---------- circuit breaker ----------


async def _is_open(dep: Deployment) -> bool:
    return bool(await clients.redis.exists(f"cb:{dep.name}"))


async def _trip(dep: Deployment) -> None:
    await clients.redis.set(f"cb:{dep.name}", 1, ex=settings.circuit_breaker_seconds)


# ---------- calls ----------


class AllProvidersFailed(Exception):
    pass


async def _prepend(first: AIMessageChunk, rest: AsyncIterator[AIMessageChunk]) -> AsyncIterator[AIMessageChunk]:
    yield first
    async for chunk in rest:
        yield chunk


async def stream_with_fallback(
    tier: str,
    messages: list[BaseMessage],
    temperature: float | None = None,
    max_tokens: int | None = None,
    stop: list[str] | None = None,
) -> tuple[Deployment, AsyncIterator[AIMessageChunk]]:
    """Return the deployment that answered and its chunk stream.

    The first chunk is awaited inside the try, so a provider that fails before sending
    anything falls through to the next one. Providers with an open circuit are skipped,
    unless every provider is open (then all are tried anyway).
    """
    chain = chain_for(tier)
    if not chain:
        raise AllProvidersFailed("no providers configured")

    open_flags = [await _is_open(dep) for dep in chain]
    candidates = [dep for dep, is_open in zip(chain, open_flags, strict=True) if not is_open] or chain

    errors: list[str] = []
    for dep in candidates:
        try:
            model = build_chat_model(dep, temperature, max_tokens)
            stream = model.astream(messages, stop=stop).__aiter__()
            first = await stream.__anext__()
            return dep, _prepend(first, stream)
        except Exception as e:  # noqa: BLE001 - any provider error means "try the next one"
            log.warning("provider %s (%s) failed: %s: %s", dep.name, dep.model, type(e).__name__, str(e)[:300])
            errors.append(f"{dep.name}: {type(e).__name__}")
            await _trip(dep)
    raise AllProvidersFailed("; ".join(errors))
