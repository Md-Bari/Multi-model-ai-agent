import logging

from app.config import settings

log = logging.getLogger(__name__)


def cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    price = settings.model_prices.get(model)
    if not price:
        log.warning("no price configured for %s; cost recorded as 0", model)
        return 0.0
    return (prompt_tokens * price[0] + completion_tokens * price[1]) / 1_000_000


def estimate_tokens(text: str) -> int:
    """Rough fallback (~4 chars/token) when a provider doesn't report usage."""
    return max(1, len(text) // 4) if text else 0
