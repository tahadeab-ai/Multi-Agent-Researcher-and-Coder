"""Tests for T1.3 (Structured Outputs) and T1.4 (Budgeting and Truncation).

Covers:
- T1.3: Supervisor uses response_format when capabilities.supports_json_schema is True
- T1.3: Degraded path when JSON parsing/repair fails sets plan_degraded=True
- T1.4: BudgetTracker token limit enforcement raises BudgetExceededError
- T1.4: BudgetTracker cost limit enforcement raises BudgetExceededError
- T1.4: truncate_tool_output preserves head and tail with marker
"""

from __future__ import annotations

import pytest

from src.agents.supervisor import SupervisorAgent
from src.errors import BudgetExceededError
from src.llm.budget import BudgetTracker, truncate_tool_output
from src.llm.protocol import LLMResponse, ModelCapabilities, TokenUsage
from src.schema import TaskPlan
from tests.mocks.mock_provider import MockProvider

# ---------------------------------------------------------------------------
# T1.3 Structured Output Tests
# ---------------------------------------------------------------------------


def test_supervisor_structured_output_success() -> None:
    """When provider supports json_schema, TaskPlan is parsed cleanly."""
    valid_plan = TaskPlan(
        goal="Test Goal",
        architecture_notes="Architecture design",
        steps=[],
    )
    mock = MockProvider(capabilities=ModelCapabilities(supports_json_schema=True))
    mock.enqueue_response(content=valid_plan.model_dump_json())

    supervisor = SupervisorAgent(provider=mock)
    plan, degraded = supervisor.plan_task("Test prompt")

    assert not degraded
    assert plan.goal == "Test Goal"
    assert mock.calls[0].response_format is TaskPlan


def test_supervisor_degraded_path_on_failure() -> None:
    """When parsing and repair both fail, supervisor activates degraded path."""
    mock = MockProvider(capabilities=ModelCapabilities(supports_json_schema=False))
    # Both initial response and repair response are invalid JSON
    mock.enqueue_response(content="Not valid json 1")
    mock.enqueue_response(content="Still invalid json 2")

    supervisor = SupervisorAgent(provider=mock)
    plan, degraded = supervisor.plan_task("Build something")

    assert degraded
    assert plan.goal == "Build something"
    assert "degraded plan" in plan.architecture_notes


# ---------------------------------------------------------------------------
# T1.4 Budgeting and Truncation Tests
# ---------------------------------------------------------------------------


def test_budget_token_limit_exceeded() -> None:
    tracker = BudgetTracker(max_tokens=100)
    resp = LLMResponse(
        content="hello",
        tool_calls=[],
        usage=TokenUsage(prompt_tokens=60, completion_tokens=50, total_tokens=110),
        cost_estimate_usd=0.001,
    )
    with pytest.raises(BudgetExceededError, match="total_tokens"):
        tracker.record_usage(resp)


def test_budget_cost_limit_exceeded() -> None:
    tracker = BudgetTracker(max_cost_usd=0.05)
    resp = LLMResponse(
        content="hello",
        tool_calls=[],
        usage=TokenUsage(prompt_tokens=10, completion_tokens=10, total_tokens=20),
        cost_estimate_usd=0.06,
    )
    with pytest.raises(BudgetExceededError, match="cost_usd"):
        tracker.record_usage(resp)


def test_truncation_preserves_head_and_tail() -> None:
    long_text = "HEAD_START" + ("A" * 1000) + "TAIL_END"
    truncated = truncate_tool_output(long_text, max_chars=100)

    assert len(truncated) < len(long_text)
    assert truncated.startswith("HEAD_START")
    assert truncated.endswith("TAIL_END")
    assert "[... Truncated" in truncated
