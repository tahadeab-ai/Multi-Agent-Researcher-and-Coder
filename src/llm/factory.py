"""Provider factory: construct the right LLMProvider from Settings.

This is the single entry point for building a provider. BaseAgent and
MultiAgentGraph call build_provider(settings) exactly once.
"""

from __future__ import annotations

from src.errors import ConfigError


def build_provider(settings: object) -> object:  # returns LLMProvider
    """Construct and return an LLMProvider for the configured backend.

    Args:
        settings: A Settings instance (typed as object to avoid circular import;
                  accessed via attribute lookup).

    Returns:
        An LLMProvider implementation.

    Raises:
        ConfigError: When the provider is misconfigured or not yet implemented.
    """
    provider = getattr(settings, "llm_provider", "openai")
    model = getattr(settings, "llm_model", "gpt-4o-mini")
    timeout = float(getattr(settings, "llm_timeout_seconds", 60))

    if provider == "openai":
        api_key = getattr(settings, "openai_api_key", None)
        if not api_key:
            raise ConfigError("LLM_PROVIDER is 'openai' but OPENAI_API_KEY is not set.")
        from src.llm.openai import OpenAIProvider

        return OpenAIProvider(model=model, api_key=api_key, timeout=timeout)

    if provider == "ollama":
        base_url = getattr(settings, "ollama_base_url", "http://localhost:11434/v1")
        from src.llm.ollama import OllamaProvider

        return OllamaProvider(model=model, base_url=base_url, timeout=timeout)

    if provider == "anthropic":
        api_key = getattr(settings, "anthropic_api_key", None)
        if not api_key:
            raise ConfigError("LLM_PROVIDER is 'anthropic' but ANTHROPIC_API_KEY is not set.")
        from src.llm.anthropic import AnthropicProvider

        return AnthropicProvider(model=model, api_key=api_key, timeout=timeout)

    raise ConfigError(
        f"Unknown LLM_PROVIDER '{provider}'. Supported values: 'openai', 'ollama', 'anthropic'."
    )
