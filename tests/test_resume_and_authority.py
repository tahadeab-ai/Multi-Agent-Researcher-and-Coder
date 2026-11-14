"""Tests for T1.5 (Persistence and Mid-Run Resume) and T1.6 (Pytest Authority & Exit Mapping)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.config import settings
from src.errors import ConfigError
from src.graph import MultiAgentGraph
from src.schema import CURRENT_SCHEMA_VERSION, AgentState, PlanStep, TaskPlan
from tests.mocks.mock_provider import MockProvider

# ---------------------------------------------------------------------------
# T1.5 Mid-Run Kill + Resume Tests
# ---------------------------------------------------------------------------


def test_schema_version_mismatch_refuses_resume(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When state.json schema_version mismatches, resume must raise ConfigError."""
    monkeypatch.setattr(settings, "workspace_dir", tmp_path)
    run_dir = tmp_path / "runs" / "test_run_ver"
    run_dir.mkdir(parents=True, exist_ok=True)
    bad_state = {
        "schema_version": 999,
        "user_prompt": "test",
    }
    (run_dir / "state.json").write_text(json.dumps(bad_state), encoding="utf-8")

    with pytest.raises(ConfigError, match="schema version 999 incompatible"):
        MultiAgentGraph.load_state("test_run_ver")


def test_mid_run_resume_skips_supervisor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mid-run kill immediately after Coder: resume re-enters at testing without Supervisor."""
    monkeypatch.setattr(settings, "workspace_dir", tmp_path)
    monkeypatch.setattr(settings, "isolate_runs", True)
    monkeypatch.setattr(settings, "run_id", "test_resume_run")

    existing_plan = TaskPlan(
        goal="Build calculator",
        architecture_notes="Simple math",
        steps=[PlanStep(step_number=1, description="calc", target_file="solution.py")],
    )
    run_dir = tmp_path / "runs" / "test_resume_run"
    run_dir.mkdir(parents=True, exist_ok=True)

    # Pre-populate code file as if Coder finished
    (run_dir / "solution.py").write_text("def add(a, b): return a + b\n", encoding="utf-8")

    # State halted at "testing"
    interrupted_state = AgentState(
        schema_version=CURRENT_SCHEMA_VERSION,
        user_prompt="Build calculator",
        plan=existing_plan,
        status="testing",
        run_dir=str(run_dir),
    )
    (run_dir / "state.json").write_text(interrupted_state.model_dump_json(), encoding="utf-8")

    # Setup mock provider:
    # Supervisor should NOT be called at all.
    # Tester writes tests turn.
    mock = MockProvider()
    mock.enqueue_response("I wrote tests/test_solution.py")

    loaded = MultiAgentGraph.load_state("test_resume_run")
    graph = MultiAgentGraph(provider=mock)

    # Monkeypatch _execute_pytest on graph to return passing TestResult
    from src.schema import TestResult

    graph._execute_pytest = lambda workspace: TestResult(  # type: ignore[method-assign]
        passed=True,
        summary="Pytest PASSED",
        stdout="1 passed",
    )

    final_state = graph.run(user_prompt=loaded.user_prompt, resume_state=loaded)

    assert final_state.status == "completed"
    # Verify Supervisor was never invoked (no plan calls on mock)
    # The only call was to Tester
    assert len(mock.calls) == 1
    # messages[0] = system role_prompt, messages[1] = context, messages[2] = user_instruction
    user_msg = next((m for m in mock.calls[0].messages if m["role"] == "user"), None)
    assert user_msg is not None
    assert "Verify the implementation" in user_msg["content"]


# ---------------------------------------------------------------------------
# T1.6 Test Execution Authority & Exit Code Mapping
# ---------------------------------------------------------------------------


def test_pytest_exit_code_5_maps_to_fail(tmp_path: Path) -> None:
    """Exit code 5 (no tests collected) must map to passed=False."""
    mock = MockProvider()
    graph = MultiAgentGraph(provider=mock)
    # Mock run_pytest returning exit code 5
    import src.graph as graph_mod

    def fake_run_pytest_fail(path: str) -> str:
        return json.dumps(
            {
                "passed": False,
                "exit_code": 5,
                "stdout": "collected 0 items",
                "stderr": "",
            }
        )

    graph_mod.run_pytest = fake_run_pytest_fail  # type: ignore[assignment]

    result = graph._execute_pytest(tmp_path)
    assert not result.passed
    assert result.exit_code == 5
    assert "No tests collected" in result.summary


def test_pytest_exit_code_0_maps_to_pass(tmp_path: Path) -> None:
    mock = MockProvider()
    graph = MultiAgentGraph(provider=mock)
    import src.graph as graph_mod

    def fake_run_pytest_pass(path: str) -> str:
        return json.dumps(
            {
                "passed": True,
                "exit_code": 0,
                "stdout": "1 passed",
                "stderr": "",
            }
        )

    graph_mod.run_pytest = fake_run_pytest_pass  # type: ignore[assignment]

    result = graph._execute_pytest(tmp_path)
    assert result.passed
    assert result.exit_code == 0
    assert "PASSED successfully" in result.summary
