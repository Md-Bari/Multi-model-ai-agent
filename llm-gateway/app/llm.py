"""Model routing (cheap vs strong) and provider calls through LiteLLM with fallback."""

import logging
import re

import litellm

from config import settings

log = logging.getLogger("gateway.llm")
litellm.drop_params = True  # silently drop params a provider doesn't support


def _deployments() -> dict[str, dict]:
    """Only providers whose real key is configured in .env are used."""
    d: dict[str, dict] = {}
    if settings.gemini_api_key:
        d["cheap-gemini"] = {"model": settings.cheap_model_gemini, "api_key": settings.gemini_api_key}
    if settings.openai_api_key:
        d["cheap-openai"] = {"model": settings.cheap_model_openai, "api_key": settings.openai_api_key}
        d["strong-openai"] = {"model": settings.strong_model_openai, "api_key": settings.openai_api_key}
    if settings.anthropic_api_key:
        d["strong-claude"] = {"model": settings.strong_model_claude, "api_key": settings.anthropic_api_key}
    return d


# Order to try for each tier: first is primary, the rest are fallbacks.
TIER_ORDER = {
    "cheap": ["cheap-gemini", "cheap-openai", "strong-claude", "strong-openai"],
    "strong": ["strong-claude", "strong-openai", "cheap-gemini", "cheap-openai"],
}
TIERS = tuple(TIER_ORDER)

DEPLOYMENTS = _deployments()
CHAINS = {tier: [n for n in order if n in DEPLOYMENTS] for tier, order in TIER_ORDER.items()}


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


# ---------- provider calls ----------


class AllProvidersFailed(Exception):
    pass


async def _prepend(first, rest):
    yield first
    async for chunk in rest:
        yield chunk


async def call_with_fallback(tier: str, messages: list[dict], stream: bool, params: dict):
    """Try each deployment of the tier in order. Returns (model, response_or_chunk_iterator).

    For streams, the first chunk is fetched inside the try, so a provider that fails
    before sending anything still falls through to the next one.
    """
    errors = []
    for name in CHAINS[tier]:
        dep = DEPLOYMENTS[name]
        try:
            extra = {"stream_options": {"include_usage": True}} if stream else {}
            resp = await litellm.acompletion(
                model=dep["model"],
                api_key=dep["api_key"],
                messages=messages,
                stream=stream,
                timeout=settings.llm_timeout,
                num_retries=settings.llm_num_retries,
                **extra,
                **params,
            )
            if stream:
                it = resp.__aiter__()
                first = await it.__anext__()
                return dep["model"], _prepend(first, it)
            return dep["model"], resp
        except Exception as e:  # noqa: BLE001 - any provider error means "try the next one"
            log.warning("provider %s (%s) failed: %s", name, dep["model"], e)
            errors.append(f"{name}: {type(e).__name__}")
    raise AllProvidersFailed("; ".join(errors) or "no providers configured")


def cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    try:
        p, c = litellm.cost_per_token(model=model, prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)
        return float(p + c)
    except Exception:  # noqa: BLE001 - unknown model in LiteLLM's price map
        log.warning("no price info for %s; cost recorded as 0", model)
        return 0.0


def count_tokens(model: str, text: str) -> int:
    try:
        return litellm.token_counter(model=model, text=text)
    except Exception:  # noqa: BLE001
        return len(text) // 4
