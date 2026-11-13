"""Structured error types for the multi-agent system."""


class ConfigError(Exception):
    """Raised when application configuration is invalid or incomplete.

    Examples:
        - Missing required API key for the selected provider
        - Unsupported provider specified
    """
