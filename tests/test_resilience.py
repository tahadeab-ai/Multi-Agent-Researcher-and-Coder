"""Tests for T1.2: Resilience, Retries, and Error Taxonomy.

Covers:
- Retry predicate on 429, timeout, and >=500 status codes
- Non-retryable on 400/401/403/404
- WaitRetryAfterOrExponential: Retry-After header honored and clamped
- WaitRetryAfterOrExponential: Exponential shape without header
- 4x429 then success via MockProvider (millisecond sleep)
- 6x429 bubbling to ProviderError (max retries exhausted)
- 500-recovery
- ToolError in ReAct loop: tool raises -> loop catches -> appends observation -> run completes (N1)
- MaxStepsExceededError raised when step limit reached
"""

from __future__ import annotations

import pytest

from src.agents.base import BaseAgent
from src.errors import (
    MaxStepsExceededError,
    ProviderError,
    ProviderTimeoutError,
    RateLimitError,
)
from src.llm.protocol import ToolCall
from src.llm.retry import (
    WaitRetryAfterOrExponential,
    is_retryable_exception,
)
from tests.mocks.mock_provider import MockProvider

# ---------------------------------------------------------------------------
# Retry taxonomy unit tests
# ---------------------------------------------------------------------------


def test_retryable_exceptions() -> None:
    assert is_retryable_exception(RateLimitError("rate limited"))
    assert is_retryable_exception(ProviderTimeoutError("timeout"))
    assert is_retryable_exception(ProviderError("server error", status_code=500))
    assert is_retryable_exception(ProviderError("gateway timeout", status_code=504))

    # Non-retryable
    assert not is_retryable_exception(ProviderError("bad request", status_code=400))
    assert not is_retryable_exception(ProviderError("unauthorized", status_code=401))
    assert not is_retryable_exception(ProviderError("forbidden", status_code=403))
    assert not is_retryable_exception(ProviderError("not found", status_code=404))
    assert not is_retryable_exception(ValueError("logic error"))


def test_wait_retry_after_honored() -> None:
    waiter = WaitRetryAfterOrExponential(max_wait=30.0)

    class DummyOutcome:
        def exception(self) -> Exception:
            return RateLimitError("too many requests", retry_after=12.5)

    class DummyState:
        attempt_number = 1
        outcome = DummyOutcome()

    delay = waiter(DummyState())  # type: ignore[arg-type]
    assert delay == 12.5


def test_wait_retry_after_clamped_to_max() -> None:
    waiter = WaitRetryAfterOrExponential(max_wait=10.0)

    class DummyOutcome:
        def exception(self) -> Exception:
            return RateLimitError("too many requests", retry_after=60.0)

    class DummyState:
        attempt_number = 1
        outcome = DummyOutcome()

    delay = waiter(DummyState())  # type: ignore[arg-type]
    assert delay == 10.0


def test_wait_exponential_shape() -> None:
    waiter = WaitRetryAfterOrExponential(initial=1.0, jitter=0.0, multiplier=2.0)

    class DummyOutcome:
        def exception(self) -> Exception:
            return ProviderTimeoutError()

    class DummyState:
        def __init__(self, attempt: int) -> None:
            self.attempt_number = attempt
            self.outcome = DummyOutcome()

    delays = [waiter(DummyState(i)) for i in range(1, 5)]  # type: ignore[arg-type]
    assert delays == [1.0, 2.0, 4.0, 8.0]


# ---------------------------------------------------------------------------
# BaseAgent retry integration with MockProvider (milliseconds sleep)
# ---------------------------------------------------------------------------


def test_4x429_then_success() -> None:
    mock = MockProvider()
    for _ in range(4):
        mock.enqueue_error(RateLimitError("429 rate limit", retry_after=0.001))
    mock.enqueue_response("Success after retries!")

    sleeps: list[float] = []

    def mock_sleep(s: float) -> None:
        sleeps.append(s)

    agent = BaseAgent(
        name="TestAgent",
        role_prompt="test",
        provider=mock,
        sleep_func=mock_sleep,
    )

    result = agent.run("hello")
    assert result == "Success after retries!"
    assert len(sleeps) == 4
    # All sleeps should be 0.001 due to retry_after
    assert all(s == 0.001 for s in sleeps)


def test_6x429_bubbles_to_error() -> None:
    mock = MockProvider()
    for _ in range(6):
        mock.enqueue_error(RateLimitError("429 rate limit", retry_after=0.001))

    agent = BaseAgent(
        name="TestAgent",
        role_prompt="test",
        provider=mock,
        sleep_func=lambda s: None,
    )

    with pytest.raises(RateLimitError):
        agent.run("hello")


def test_500_recovery() -> None:
    mock = MockProvider()
    mock.enqueue_error(ProviderError("Internal Server Error", status_code=500))
    mock.enqueue_response("Recovered from 500!")

    sleeps: list[float] = []
    agent = BaseAgent(
        name="TestAgent",
        role_prompt="test",
        provider=mock,
        sleep_func=lambda s: sleeps.append(s),
    )

    result = agent.run("hello")
    assert result == "Recovered from 500!"
    assert len(sleeps) == 1


# ---------------------------------------------------------------------------
# ToolError semantics (N1 requirement)
# ---------------------------------------------------------------------------


def test_tool_error_converted_to_observation_and_loop_continues() -> None:
    """N1: ToolError must NOT crash the loop; observation appended and model retries."""

    def failing_tool() -> str:
        raise OSError("Disk read failed")

    mock = MockProvider()
    # Turn 1: call failing_tool
    mock.enqueue_response(tool_calls=[ToolCall(id="tc1", name="failing_tool", arguments="{}")])
    # Turn 2: model sees tool error observation and responds with final text
    mock.enqueue_response(content="I handled the tool failure gracefully.")

    agent = BaseAgent(
        name="TestAgent",
        role_prompt="test",
        tools=[{"name": "failing_tool"}],
        tool_functions={"failing_tool": failing_tool},
        provider=mock,
    )

    output = agent.run("do work")
    assert output == "I handled the tool failure gracefully."

    # Verify messages in call 2 received the ToolError observation
    call2_messages = mock.calls[1].messages
    tool_msg = next((m for m in call2_messages if m.get("role") == "tool"), None)
    assert tool_msg is not None
    assert "Tool 'failing_tool' failed: Disk read failed" in tool_msg["content"]


def test_max_steps_exceeded_raises() -> None:
    mock = MockProvider()
    # Enqueue tool calls continuously exceeding max_agent_steps
    for i in range(10):
        mock.enqueue_response(tool_calls=[ToolCall(id=f"tc{i}", name="noop", arguments="{}")])

    agent = BaseAgent(
        name="TestAgent",
        role_prompt="test",
        tools=[{"name": "noop"}],
        tool_functions={"noop": lambda: "ok"},
        provider=mock,
    )

    with pytest.raises(MaxStepsExceededError):
        agent.run("loop forever")
