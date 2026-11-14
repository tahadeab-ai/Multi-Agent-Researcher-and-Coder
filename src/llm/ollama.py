"""Ollama provider adapter.

Ollama exposes an OpenAI-compatible endpoint at /v1. We use OpenAIProvider
under the hood but add a JSON-schema capability probe at startup.

The probe fires one minimal chat-completion call with response_format={"type":"json_object"}
to determine whether this Ollama instance supports structured output.
"""

from __future__ import annotations

from typing import Any

from src.llm.openai import OpenAIProvider
from src.llm.protocol import LLMResponse, ModelCapabilities


class OllamaProvider:
    """LLM provider adapter for local Ollama instances.

    Wraps OpenAIProvider with an Ollama-specific capability probe for
    JSON-schema structured output support.
    """

    def __init__(
        self,
        model: str,
        base_url: str = "http://localhost:11434/v1",
        timeout: float = 60.0,
        _json_schema_capable: bool | None = None,
    ) -> None:
        """Create an Ollama provider.

        Args:
            model: Ollama model tag (e.g. 'llama3:8b', 'mistral').
            base_url: Ollama REST endpoint base URL.
            timeout: Request timeout in seconds.
            _json_schema_capable: Override probe result (used in tests).
        """
        self._inner = OpenAIProvider(
            model=model,
            api_key="ollama",
            base_url=base_url,
            timeout=timeout,
        )
        # Probe unless overridden (e.g. in tests)
        if _json_schema_capable is not None:
            self._json_schema_capable = _json_schema_capable
        else:
            self._json_schema_capable = self._probe_json_schema(base_url, model, timeout)

        self._capabilities = ModelCapabilities(
            supports_temperature=True,
            supports_tools=True,
            supports_json_schema=self._json_schema_capable,
            default_context_window=8_192,
        )

    @staticmethod
    def _probe_json_schema(base_url: str, model: str, timeout: float) -> bool:
        """Send a minimal structured-output probe to detect capability."""
        try:
            import openai  # already a core dep

            client = openai.OpenAI(api_key="ollama", base_url=base_url, timeout=timeout)
            client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": 'Reply with {"ok":true}'}],
                response_format={"type": "json_object"},
                max_tokens=20,
            )
            return True
        except Exception:  # noqa: BLE001 — probe: any failure = not capable
            return False

    @property
    def capabilities(self) -> ModelCapabilities:
        return self._capabilities

    def generate(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        response_format: type | None = None,
    ) -> LLMResponse:
        # Strip response_format if this Ollama instance can't handle it
        effective_rf = response_format if self._json_schema_capable else None
        return self._inner.generate(messages, tools, temperature, effective_rf)

    async def agenerate(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        response_format: type | None = None,
    ) -> LLMResponse:
        effective_rf = response_format if self._json_schema_capable else None
        return await self._inner.agenerate(messages, tools, temperature, effective_rf)
