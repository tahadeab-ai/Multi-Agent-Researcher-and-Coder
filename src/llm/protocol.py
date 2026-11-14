"""LLM provider protocol, response types, and capability flags.

All providers in src/llm/ implement the LLMProvider Protocol so that
BaseAgent and MultiAgentGraph are decoupled from any specific SDK.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class TokenUsage:
    """Token accounting for a single LLM call."""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass(frozen=True)
class ToolCall:
    """A single tool call requested by the model."""

    id: str
    name: str
    arguments: str  # raw JSON string, as returned by the model


@dataclass(frozen=True)
class LLMResponse:
    """Normalized response from any LLM provider."""

    content: str | None
    tool_calls: list[ToolCall]
    usage: TokenUsage
    cost_estimate_usd: float | None  # None when model rate is unknown
    raw_response: Any = field(repr=False, default=None)


@dataclass(frozen=True)
class ModelCapabilities:
    """Describes what a particular model/provider combination supports."""

    supports_temperature: bool = True
    supports_tools: bool = True
    supports_json_schema: bool = False
    default_context_window: int = 128_000


@runtime_checkable
class LLMProvider(Protocol):
    """Interface that every provider adapter must satisfy."""

    @property
    def capabilities(self) -> ModelCapabilities:
        """Return static capability flags for this provider/model combo."""
        ...

    def generate(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        response_format: type | None = None,
    ) -> LLMResponse:
        """Synchronous (blocking) generation call."""
        ...

    async def agenerate(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        response_format: type | None = None,
    ) -> LLMResponse:
        """Asynchronous generation call."""
        ...
