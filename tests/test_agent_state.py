"""Unit tests for agent state and schemas."""

from src.schema import AgentState, PlanStep, TaskPlan, TestResult


def test_agent_state_initialization():
    plan = TaskPlan(
        goal="Build an LRU cache",
        architecture_notes="Use OrderedDict or Doubly-Linked List",
        steps=[
            PlanStep(
                step_number=1,
                description="Implement LRU cache class",
                target_file="lru.py",
            ),
            PlanStep(
                step_number=2,
                description="Write tests",
                target_file="tests/test_lru.py",
            ),
        ],
    )

    state = AgentState(
        user_prompt="Build an LRU Cache",
        plan=plan,
        generated_files=["lru.py"],
        status="coding",
    )

    assert state.plan.goal == "Build an LRU cache"
    assert len(state.plan.steps) == 2
    assert state.status == "coding"
    assert state.healing_cycle == 0


def test_test_result_parsing():
    result = TestResult(
        passed=True,
        summary="All 5 tests passed",
        stdout="5 passed in 0.12s",
    )
    assert result.passed is True
    assert result.error_trace is None
