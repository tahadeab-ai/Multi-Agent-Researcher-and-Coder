"""LLM cost table with clearly stated source and date.

All rates are USD per 1 million tokens (input / output).
Rates are INFORMATIONAL only — they can be stale. When a model is
not in this table, cost_estimate_usd is returned as None; token counts
are always tracked regardless.
"""

from __future__ import annotations

# When these rates were last verified and where.
LAST_UPDATED: str = "2025-07-01"
SOURCE: str = (
    "https://openai.com/api/pricing (OpenAI) / "
    "https://www.anthropic.com/pricing (Anthropic)"
)

# Cost per 1 million tokens: (input_usd_per_1M, output_usd_per_1M)
_COST_TABLE: dict[str, tuple[float, float]] = {
    # OpenAI
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4-turbo": (10.00, 30.00),
    "gpt-4": (30.00, 60.00),
    "gpt-3.5-turbo": (0.50, 1.50),
    "o1": (15.00, 60.00),
    "o1-mini": (3.00, 12.00),
    # Anthropic
    "claude-3-5-sonnet-20241022": (3.00, 15.00),
    "claude-3-5-haiku-20241022": (0.80, 4.00),
    "claude-3-opus-20240229": (15.00, 75.00),
    "claude-3-sonnet-20240229": (3.00, 15.00),
    "claude-3-haiku-20240307": (0.25, 1.25),
}


def estimate_cost_usd(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> float | None:
    """Return estimated cost in USD, or None if the model rate is unknown.

    Uses exact match first, then prefix match from longest key to shortest,
    so 'gpt-4o' does not shadow 'gpt-4o-mini'.
    Rates may be stale; always check SOURCE for current pricing.
    """
    # Exact match takes priority
    if model in _COST_TABLE:
        in_rate, out_rate = _COST_TABLE[model]
        return (prompt_tokens * in_rate + completion_tokens * out_rate) / 1_000_000

    # Prefix match: longer keys first to avoid false matches (e.g. gpt-4o vs gpt-4o-mini)
    for key in sorted(_COST_TABLE, key=len, reverse=True):
        if model.startswith(key):
            in_rate, out_rate = _COST_TABLE[key]
            return (prompt_tokens * in_rate + completion_tokens * out_rate) / 1_000_000

    return None
