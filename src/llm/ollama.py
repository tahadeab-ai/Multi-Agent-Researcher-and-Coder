"""Ollama provider adapter.

Ollama exposes an OpenAI-compatible endpoint at /v1. We use OpenAIProvider
under the hood with lazy probing and caching per (base_url, model).
"""

from __future__ import annotations

from typing import Any

from src.llm.openai import OpenAIProvider
from src.llm.protocol import LLMResponse, ModelCapabilities

# Cache probe results per (base_url, model)
_OLLAMA_CAPABILITY_CACHE: dict[tuple[str, str], bool] = {}


class OllamaProvider:
    """LLM provider adapter for local Ollama instances."""

    def __init__(
        self,
        model: str,
        base_url: str = "http://localhost:11434/v1",
        timeout: float = 60.0,
        _json_schema_capable: bool | None = None,
    ) -> None:
        self._model = model
        self._base_url = base_url
        self._timeout = timeout
        self._override_capable = _json_schema_capable

        self._inner = OpenAIProvider(
            model=model,
            api_key="ollama",
            base_url=base_url,
            timeout=timeout,
        )

    def _is_json_schema_capable(self) -> bool:
        if self._override_capable is not None:
            return self._override_capable
        key = (self._base_url, self._model)
        if key in _OLLAMA_CAPABILITY_CACHE:
            return _OLLAMA_CAPABILITY_CACHE[key]

        # Lazy probe on first use
        try:
            import openai

            client = openai.OpenAI(
                api_key="ollama",
                base_url=self._base_url,
                timeout=min(self._timeout, 5.0),
            )
            client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": 'Reply with {"ok":true}'}],
                response_format={"type": "json_object"},
                max_tokens=20,
            )
            capable = True
        except Exception:  # noqa: BLE001 — probe: any failure = not capable
            capable = False

        _OLLAMA_CAPABILITY_CACHE[key] = capable
        return capable

    @property
    def capabilities(self) -> ModelCapabilities:
        capable = self._is_json_schema_capable()
        return ModelCapabilities(
            supports_temperature=True,
            supports_tools=True,
            supports_json_schema=capable,
            default_context_window=8_192,
        )

    def generate(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        response_format: type | None = None,
    ) -> LLMResponse:
        effective_rf = response_format if self._is_json_schema_capable() else None
        return self._inner.generate(messages, tools, temperature, effective_rf)

    async def agenerate(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        response_format: type | None = None,
    ) -> LLMResponse:
        effective_rf = response_format if self._is_json_schema_capable() else None
        return await self._inner.agenerate(messages, tools, temperature, effective_rf)
