"""OpenAI provider adapter.

Implements LLMProvider for the OpenAI API and OpenAI-compatible endpoints
(e.g. Ollama served via the OpenAI-compatible REST interface on /v1).

Retry logic lives in BaseAgent._call_provider() (T1.2). This module only
handles request construction, response normalization, and capability flags.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import openai

from src.llm.costs import estimate_cost_usd
from src.llm.protocol import LLMResponse, ModelCapabilities, TokenUsage, ToolCall

if TYPE_CHECKING:
    pass

# Models known to reject the temperature parameter (reasoning models).
_NO_TEMPERATURE_MODELS: frozenset[str] = frozenset({"o1", "o1-mini", "o1-preview"})

# Models known to support the OpenAI json_schema structured output format.
_JSON_SCHEMA_MODELS: frozenset[str] = frozenset(
    {
        "gpt-4o",
        "gpt-4o-mini",
        "gpt-4-turbo",
        "o1",
        "o1-mini",
    }
)


def _build_capabilities(model: str) -> ModelCapabilities:
    model_key = model.split(":")[0]  # strip tag for ollama models like llama3:8b
    return ModelCapabilities(
        supports_temperature=model_key not in _NO_TEMPERATURE_MODELS,
        supports_tools=True,
        supports_json_schema=any(model_key.startswith(m) for m in _JSON_SCHEMA_MODELS),
        default_context_window=128_000,
    )


def _normalize_response(
    response: Any,
    model: str,
) -> LLMResponse:
    """Convert an openai ChatCompletion into our normalized LLMResponse."""
    message = response.choices[0].message
    usage = (
        response.usage
        or type("u", (), {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})()
    )
    token_usage = TokenUsage(
        prompt_tokens=usage.prompt_tokens,
        completion_tokens=usage.completion_tokens,
        total_tokens=usage.total_tokens,
    )
    tool_calls: list[ToolCall] = []
    if message.tool_calls:
        for tc in message.tool_calls:
            tool_calls.append(
                ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=tc.function.arguments,
                )
            )
    return LLMResponse(
        content=message.content,
        tool_calls=tool_calls,
        usage=token_usage,
        cost_estimate_usd=estimate_cost_usd(
            model, token_usage.prompt_tokens, token_usage.completion_tokens
        ),
        raw_response=response,
    )


class OpenAIProvider:
    """LLM provider adapter for the OpenAI API."""

    def __init__(
        self,
        model: str,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 60.0,
    ) -> None:
        self._model = model
        self._capabilities = _build_capabilities(model)
        self._sync_client = openai.OpenAI(
            api_key=api_key or "ollama",
            base_url=base_url,
            timeout=timeout,
        )
        self._async_client = openai.AsyncOpenAI(
            api_key=api_key or "ollama",
            base_url=base_url,
            timeout=timeout,
        )

    @property
    def capabilities(self) -> ModelCapabilities:
        return self._capabilities

    def _build_kwargs(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        temperature: float | None,
        response_format: type | None,
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools
        if temperature is not None and self._capabilities.supports_temperature:
            kwargs["temperature"] = temperature
        if response_format is not None and self._capabilities.supports_json_schema:
            # Use SDK-managed strict conversion (openai>=1.40.0 required).
            # The SDK converts response_format=<BaseModel> into the correct
            # json_schema strict format automatically.
            kwargs["response_format"] = response_format
        return kwargs

    def generate(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        response_format: type | None = None,
    ) -> LLMResponse:
        kwargs = self._build_kwargs(messages, tools, temperature, response_format)
        if response_format is not None and self._capabilities.supports_json_schema:
            resp = self._sync_client.beta.chat.completions.parse(**kwargs)
        else:
            resp = self._sync_client.chat.completions.create(**kwargs)
        return _normalize_response(resp, self._model)

    async def agenerate(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        response_format: type | None = None,
    ) -> LLMResponse:
        kwargs = self._build_kwargs(messages, tools, temperature, response_format)
        if response_format is not None and self._capabilities.supports_json_schema:
            resp = await self._async_client.beta.chat.completions.parse(**kwargs)
        else:
            resp = await self._async_client.chat.completions.create(**kwargs)
        return _normalize_response(resp, self._model)

    def run_sync_in_thread(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        response_format: type | None = None,
    ) -> LLMResponse:
        """Convenience: run agenerate from a synchronous context."""
        return asyncio.run(self.agenerate(messages, tools, temperature, response_format))
