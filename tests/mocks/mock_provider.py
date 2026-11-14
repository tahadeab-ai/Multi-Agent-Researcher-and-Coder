"""Mock LLM provider for deterministic unit testing.

Usage:
    mock = MockProvider()
    mock.enqueue_response("Hello!")
    mock.enqueue_error(openai.RateLimitError(...))
    response = mock.generate(messages=[...])  # returns "Hello!"
    response = mock.generate(messages=[...])  # raises RateLimitError

The mock records all calls so tests can assert on prompts, tools sent, etc.
"""

from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass
from typing import Any

from src.llm.protocol import LLMProvider, LLMResponse, ModelCapabilities, TokenUsage, ToolCall


@dataclass
class _Call:
    """Record of one generate() call."""

    messages: list[dict[str, Any]]
    tools: list[dict[str, Any]] | None
    temperature: float | None
    response_format: type | None


class MockProvider:
    """Deterministic LLM provider for unit tests.

    Thread-safe for single-threaded pytest; not for concurrent tests.
    """

    def __init__(
        self,
        capabilities: ModelCapabilities | None = None,
    ) -> None:
        self._queue: deque[LLMResponse | BaseException] = deque()
        self.calls: list[_Call] = []
        self._capabilities = capabilities or ModelCapabilities(
            supports_temperature=True,
            supports_tools=True,
            supports_json_schema=True,
        )

    # -- Configuration helpers -------------------------------------------------

    def enqueue_response(
        self,
        content: str | None = None,
        tool_calls: list[ToolCall] | None = None,
        prompt_tokens: int = 10,
        completion_tokens: int = 10,
        cost_usd: float | None = 0.0001,
    ) -> MockProvider:
        """Queue a successful response. Returns self for chaining."""
        self._queue.append(
            LLMResponse(
                content=content,
                tool_calls=tool_calls or [],
                usage=TokenUsage(
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=prompt_tokens + completion_tokens,
                ),
                cost_estimate_usd=cost_usd,
            )
        )
        return self

    def enqueue_error(self, error: BaseException) -> MockProvider:
        """Queue an exception to be raised on the next call. Returns self."""
        self._queue.append(error)
        return self

    def enqueue_responses(self, *contents: str) -> MockProvider:
        """Convenience: queue multiple text-only responses."""
        for c in contents:
            self.enqueue_response(content=c)
        return self

    # -- LLMProvider interface -------------------------------------------------

    @property
    def capabilities(self) -> ModelCapabilities:
        return self._capabilities

    def _dequeue(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        temperature: float | None,
        response_format: type | None,
    ) -> LLMResponse:
        self.calls.append(_Call(messages, tools, temperature, response_format))
        if not self._queue:
            raise RuntimeError("MockProvider queue is empty — enqueue a response or error first.")
        item = self._queue.popleft()
        if isinstance(item, BaseException):
            raise item
        return item

    def generate(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        response_format: type | None = None,
    ) -> LLMResponse:
        return self._dequeue(messages, tools, temperature, response_format)

    async def agenerate(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        response_format: type | None = None,
    ) -> LLMResponse:
        await asyncio.sleep(0)  # yield to event loop
        return self._dequeue(messages, tools, temperature, response_format)


# Confirm MockProvider satisfies the Protocol at import time.
def _check_protocol() -> None:
    _: LLMProvider = MockProvider()


_check_protocol()
