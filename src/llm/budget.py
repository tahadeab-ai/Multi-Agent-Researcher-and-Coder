"""Token and cost budgeting tracker (T1.4)."""

from __future__ import annotations

from typing import Any

from src.config import settings
from src.errors import BudgetExceededError
from src.llm.protocol import LLMResponse


class BudgetTracker:
    """Tracks token consumption and USD costs across agent calls."""

    def __init__(
        self,
        max_tokens: int | None = None,
        max_cost_usd: float | None = None,
    ) -> None:
        self.max_tokens = max_tokens if max_tokens is not None else settings.max_tokens_per_run
        self.max_cost_usd = (
            max_cost_usd if max_cost_usd is not None else settings.max_cost_per_run_usd
        )
        self.total_prompt_tokens: int = 0
        self.total_completion_tokens: int = 0
        self.total_tokens: int = 0
        self.total_cost_usd: float = 0.0

    def record_usage(self, response: LLMResponse) -> dict[str, Any]:
        """Record token and cost usage from an LLMResponse.

        Raises:
            BudgetExceededError: If configured budget thresholds are crossed.
        """
        usage = response.usage
        self.total_prompt_tokens += usage.prompt_tokens
        self.total_completion_tokens += usage.completion_tokens
        self.total_tokens += usage.total_tokens

        if response.cost_estimate_usd is not None:
            self.total_cost_usd += response.cost_estimate_usd

        # Enforce token limit
        if self.max_tokens is not None and self.total_tokens > self.max_tokens:
            raise BudgetExceededError(
                limit_type="total_tokens",
                limit_value=float(self.max_tokens),
                current_value=float(self.total_tokens),
            )

        # Enforce cost limit
        if self.max_cost_usd is not None and self.total_cost_usd > self.max_cost_usd:
            raise BudgetExceededError(
                limit_type="cost_usd",
                limit_value=self.max_cost_usd,
                current_value=self.total_cost_usd,
            )

        return {
            "prompt_tokens": usage.prompt_tokens,
            "completion_tokens": usage.completion_tokens,
            "total_tokens": usage.total_tokens,
            "turn_cost_usd": response.cost_estimate_usd,
            "cumulative_tokens": self.total_tokens,
            "cumulative_cost_usd": self.total_cost_usd,
        }


def truncate_tool_output(output: str, max_chars: int | None = None) -> str:
    """Truncate oversized tool outputs preserving head and tail (T1.4).

    First 40% chars and last 40% chars are preserved.
    """
    limit = max_chars if max_chars is not None else settings.tool_output_max_chars
    if len(output) <= limit:
        return output

    keep = int(limit * 0.4)
    head = output[:keep]
    tail = output[-keep:]
    truncated_count = len(output) - (keep * 2)
    return f"{head}\n[... Truncated {truncated_count} characters by PHOENIX sandbox ...]\n{tail}"
