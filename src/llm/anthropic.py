"""Anthropic provider adapter (optional extra: pip install .[anthropic]).

Lazy-imports the anthropic SDK so the core package does not require it.
If anthropic is not installed, instantiating this class raises ImportError
with a clear install instruction.
"""

from __future__ import annotations

from typing import Any

from src.llm.costs import estimate_cost_usd
from src.llm.protocol import LLMResponse, ModelCapabilities, TokenUsage, ToolCall


def _require_anthropic() -> Any:
    try:
        import anthropic

        return anthropic
    except ImportError as exc:
        raise ImportError(
            "The 'anthropic' package is required for the Anthropic provider. "
            "Install it with: pip install '.[anthropic]'"
        ) from exc


_ANTHROPIC_CAPABILITIES = ModelCapabilities(
    supports_temperature=True,
    supports_tools=True,
    supports_json_schema=False,  # Anthropic uses tool_choice for structured outputs
    default_context_window=200_000,
)


def _convert_messages_to_anthropic(
    messages: list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:
    """Split OpenAI-style messages into system prompt + user/assistant turns."""
    system_parts: list[str] = []
    turns: list[dict[str, Any]] = []
    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if role == "system":
            system_parts.append(str(content))
        elif role in ("user", "assistant"):
            turns.append({"role": role, "content": str(content)})
        elif role == "tool":
            # Tool results as user messages
            turns.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": msg.get("tool_call_id", ""),
                            "content": str(content),
                        }
                    ],
                }
            )
    return "\n\n".join(system_parts), turns


class AnthropicProvider:
    """LLM provider adapter for the Anthropic Claude API."""

    def __init__(
        self,
        model: str,
        api_key: str | None = None,
        timeout: float = 60.0,
    ) -> None:
        anthropic = _require_anthropic()
        self._model = model
        self._capabilities = _ANTHROPIC_CAPABILITIES
        self._client = anthropic.Anthropic(api_key=api_key, timeout=timeout)
        self._async_client = anthropic.AsyncAnthropic(api_key=api_key, timeout=timeout)

    @property
    def capabilities(self) -> ModelCapabilities:
        return self._capabilities

    def _convert_tools(self, tools: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
        """Convert OpenAI-style tool schemas to Anthropic format."""
        if not tools:
            return []
        result = []
        for t in tools:
            fn = t.get("function", t)
            result.append(
                {
                    "name": fn.get("name", ""),
                    "description": fn.get("description", ""),
                    "input_schema": fn.get("parameters", {}),
                }
            )
        return result

    def _normalize(self, response: Any) -> LLMResponse:
        content_text: str | None = None
        tool_calls: list[ToolCall] = []
        for block in response.content:
            if block.type == "text":
                content_text = block.text
            elif block.type == "tool_use":
                import json

                tool_calls.append(
                    ToolCall(
                        id=block.id,
                        name=block.name,
                        arguments=json.dumps(block.input),
                    )
                )
        usage = response.usage
        token_usage = TokenUsage(
            prompt_tokens=usage.input_tokens,
            completion_tokens=usage.output_tokens,
            total_tokens=usage.input_tokens + usage.output_tokens,
        )
        return LLMResponse(
            content=content_text,
            tool_calls=tool_calls,
            usage=token_usage,
            cost_estimate_usd=estimate_cost_usd(
                self._model, token_usage.prompt_tokens, token_usage.completion_tokens
            ),
            raw_response=response,
        )

    def generate(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        response_format: type | None = None,
    ) -> LLMResponse:
        system, turns = _convert_messages_to_anthropic(messages)
        kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": 8096,
            "messages": turns,
        }
        if system:
            kwargs["system"] = system
        if temperature is not None:
            kwargs["temperature"] = temperature
        ant_tools = self._convert_tools(tools)
        if ant_tools:
            kwargs["tools"] = ant_tools
        resp = self._client.messages.create(**kwargs)
        return self._normalize(resp)

    async def agenerate(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        response_format: type | None = None,
    ) -> LLMResponse:
        system, turns = _convert_messages_to_anthropic(messages)
        kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": 8096,
            "messages": turns,
        }
        if system:
            kwargs["system"] = system
        if temperature is not None:
            kwargs["temperature"] = temperature
        ant_tools = self._convert_tools(tools)
        if ant_tools:
            kwargs["tools"] = ant_tools
        resp = await self._async_client.messages.create(**kwargs)
        return self._normalize(resp)
