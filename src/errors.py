"""Structured error types for the multi-agent system.

Hierarchy:
    PhoenixError
    ├── ConfigError          — misconfiguration at startup
    ├── ProviderError        — LLM API failures
    │   ├── RateLimitError   — HTTP 429 (retryable)
    │   └── ProviderTimeoutError — request timeout (retryable)
    ├── ToolError            — tool execution failures (trust boundary)
    │   ├── FileToolError    — file_tools specific
    │   └── ShellToolError   — shell_tools specific
    ├── BudgetExceededError  — token or cost cap reached
    └── MaxStepsExceededError — agent loop cap reached
"""

from __future__ import annotations


class PhoenixError(Exception):
    """Base class for all PHOENIX system errors."""


class ConfigError(PhoenixError):
    """Raised when application configuration is invalid or incomplete.

    Examples:
        - Missing required API key for the selected provider
        - Unsupported provider specified
        - state.json schema version mismatch on resume
    """


# Canonical alias for ConfigError per ADR & design documentation
ConfigurationError = ConfigError


class ProviderError(PhoenixError):
    """Raised when an LLM provider call fails unrecoverably.

    Retryable subclasses (RateLimitError, ProviderTimeoutError) are
    automatically retried by the tenacity decorator in BaseAgent.
    """

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class RateLimitError(ProviderError):
    """HTTP 429 — rate limit exceeded. Retryable with backoff.

    Args:
        retry_after: Seconds to wait if the server sent a Retry-After header.
    """

    def __init__(
        self,
        message: str,
        status_code: int = 429,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message, status_code)
        self.retry_after = retry_after


class ProviderTimeoutError(ProviderError):
    """Request timed out. Retryable."""

    def __init__(self, message: str = "LLM request timed out") -> None:
        super().__init__(message, status_code=None)


class ToolError(PhoenixError):
    """Raised at the tool-dispatch trust boundary.

    Wraps any lower-level exception so the agent loop always receives a
    structured PhoenixError rather than arbitrary exception types.
    """

    def __init__(self, tool: str, cause: BaseException) -> None:
        super().__init__(f"Tool '{tool}' failed: {cause!s}")
        self.tool = tool
        self.cause = cause


class FileToolError(ToolError):
    """Tool error originating from file_tools."""


class ShellToolError(ToolError):
    """Tool error originating from shell_tools."""


class BudgetExceededError(PhoenixError):
    """Raised when a per-run token or cost budget is exhausted."""

    def __init__(
        self,
        limit_type: str,
        limit_value: float,
        current_value: float,
    ) -> None:
        super().__init__(
            f"Budget exceeded: {limit_type}={current_value:.2f} > limit={limit_value:.2f}"
        )
        self.limit_type = limit_type
        self.limit_value = limit_value
        self.current_value = current_value


class MaxStepsExceededError(PhoenixError):
    """Raised when the agent ReAct loop hits the max_agent_steps cap."""

    def __init__(self, agent: str, steps: int) -> None:
        super().__init__(
            f"Agent '{agent}' reached max_agent_steps={steps} without producing a final response."
        )
        self.agent = agent
        self.steps = steps
