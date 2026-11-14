"""State Machine Graph orchestrating Supervisor, Coder, and Tester agents."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

from rich.console import Console

from src.agents.coder import CoderAgent
from src.agents.supervisor import SupervisorAgent
from src.agents.tester import TesterAgent
from src.config import settings
from src.errors import ConfigError
from src.llm.budget import BudgetTracker
from src.llm.protocol import LLMProvider
from src.logging_config import get_logger
from src.schema import CURRENT_SCHEMA_VERSION, AgentState, TestResult
from src.tools.shell_tools import run_pytest

console = Console()
logger = get_logger(__name__)


def _persist_state_atomically(run_dir: Path, state: AgentState) -> None:
    """Write AgentState to state.json using atomic temp file replacement."""
    run_dir.mkdir(parents=True, exist_ok=True)
    temp_state = run_dir / f"state.json.tmp.{uuid4().hex}"
    temp_state.write_text(state.model_dump_json(indent=2), encoding="utf-8")
    temp_state.replace(run_dir / "state.json")


def _update_step_completion(workspace: Path, state: AgentState, tests_passed: bool) -> None:
    """PlanStep.completed is True iff target_file exists AND tests passed."""
    if not state.plan:
        return
    for step in state.plan.steps:
        if step.target_file:
            target_path = workspace / step.target_file
            if target_path.exists() and tests_passed:
                step.completed = True


class MultiAgentGraph:
    """Orchestrates multi-agent development with atomic state and deterministic testing."""

    def __init__(
        self,
        on_step_callback: Callable[[str, str], None] | None = None,
        provider: LLMProvider | None = None,
    ) -> None:
        self.budget_tracker = BudgetTracker()
        self.supervisor = SupervisorAgent(provider=provider)
        self.coder = CoderAgent(provider=provider, budget_tracker=self.budget_tracker)
        self.tester = TesterAgent(provider=provider, budget_tracker=self.budget_tracker)
        self.on_step_callback = on_step_callback

    def _notify(self, stage: str, message: str) -> None:
        """Dispatches progress updates to callback and terminal."""
        if self.on_step_callback:
            self.on_step_callback(stage, message)
        else:
            console.print(f"[bold cyan][{stage}][/bold cyan] {message}")

    @classmethod
    def load_state(cls, run_id: str) -> AgentState:
        """Load and validate state.json from a prior run for resumption."""
        base = settings.workspace_dir.resolve()
        state_file = base / "runs" / run_id / "state.json"
        if not state_file.exists():
            raise ConfigError(f"Cannot resume run '{run_id}': state file not found at {state_file}")

        try:
            raw_data = json.loads(state_file.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            raise ConfigError(f"Corrupted state file at {state_file}: {exc}") from exc

        schema_version = raw_data.get("schema_version")
        if schema_version != CURRENT_SCHEMA_VERSION:
            raise ConfigError(
                f"state.json schema version {schema_version} incompatible with current "
                f"{CURRENT_SCHEMA_VERSION}; cannot resume."
            )

        return AgentState.model_validate(raw_data)

    def _execute_pytest(self, workspace: Path) -> TestResult:
        """Run pytest once deterministically and build TestResult (A4, T1.6)."""
        raw_test_run = run_pytest("tests")
        try:
            data = json.loads(raw_test_run)
            exit_code = data.get("exit_code", 1)
            stdout = data.get("stdout", "")
            stderr = data.get("stderr", "")

            # Pytest exit code mapping:
            # 0: PASS
            # 5: NO TESTS COLLECTED -> FAIL
            # 1, 2, 3, 4: FAIL / ERROR
            passed = exit_code == 0
            if exit_code == 5:
                passed = False
                summary = "Pytest FAILED: No tests collected (exit code 5)."
            elif passed:
                summary = "Pytest PASSED successfully."
            else:
                summary = f"Pytest FAILED with exit code {exit_code}."

            error_trace = None
            if not passed:
                error_trace = stdout or stderr or data.get("error", "Unknown test failure")

            return TestResult(
                passed=passed,
                summary=summary,
                stdout=stdout,
                stderr=stderr,
                error_trace=error_trace,
                exit_code=exit_code,
            )
        except Exception as err:  # noqa: BLE001
            return TestResult(
                passed=False,
                summary=f"Failed to parse test execution output: {err!s}",
                error_trace=str(err),
                exit_code=3,
            )

    def run(self, user_prompt: str, resume_state: AgentState | None = None) -> AgentState:
        """Executes or resumes the multi-agent development lifecycle."""
        if resume_state is not None:
            state = resume_state
            # Single writer rule: graph sets run_id from resumed state
            if state.run_dir:
                run_id_cand = Path(state.run_dir).name
                settings.run_id = run_id_cand
            workspace = settings.get_resolved_workspace()
            self._notify("Graph", f"Resuming execution from existing run at {workspace}")
        else:
            # Single writer rule: graph owns run_id
            workspace = settings.get_resolved_workspace()
            state = AgentState(
                user_prompt=user_prompt,
                status="planning",
                run_dir=str(workspace),
            )
            _persist_state_atomically(workspace, state)

        # ----------------------------------------------------
        # Stage 1: Planning (Supervisor Agent)
        # ----------------------------------------------------
        if state.plan is None:
            self._notify("Supervisor", "Analyzing requirements and creating architecture plan...")
            plan, degraded = self.supervisor.plan_task(user_prompt=user_prompt)
            state.plan = plan
            state.plan_degraded = degraded
            state.status = "coding"
            _persist_state_atomically(workspace, state)

            plan_summary = (
                f"Goal: {state.plan.goal}\n"
                f"Architecture: {state.plan.architecture_notes}\n"
                f"Steps: {len(state.plan.steps)}"
            )
            self._notify("Supervisor", f"Plan formulated:\n{plan_summary}")
        else:
            self._notify("Supervisor", "Plan already exists in state, skipping planning.")

        # ----------------------------------------------------
        # Stage 2: Implementation (Coder Agent)
        # ----------------------------------------------------
        plan_context = state.plan.model_dump_json(indent=2)
        if state.status == "coding":
            self._notify("Coder", "Generating Python source code according to plan...")
            code_instruction = (
                f"Implement the solution for this goal: '{state.plan.goal}'.\n"
                f"Follow these architectural steps carefully:\n{plan_context}\n"
                f"Write the implementation file(s) to the sandbox using write_file."
            )
            coder_response = self.coder.write_code(
                task_instruction=code_instruction,
                context=f"User original requirement: {user_prompt}",
            )
            self._notify(
                "Coder", f"Implementation completed. Agent remarks: {coder_response[:200]}"
            )
            state.status = "testing"
            _persist_state_atomically(workspace, state)

        # ----------------------------------------------------
        # Stage 3: Verification & Self-Healing Loop (Tester + Graph)
        # ----------------------------------------------------
        while state.healing_cycle <= settings.max_healing_cycles:
            self._notify(
                "Tester",
                f"Authoring/running test suite (Cycle {state.healing_cycle + 1})...",
            )

            # 1. Tester Agent writes tests
            test_instruction = (
                f"Verify the implementation for: '{state.plan.goal}'.\n"
                f"1. Read the implemented files.\n"
                f"2. Write comprehensive pytest unit tests into 'tests/test_solution.py'."
            )
            tester_remarks = self.tester.write_tests(
                task_instruction=test_instruction,
                context=f"Current Architecture Plan:\n{plan_context}",
            )
            self._notify("Tester", f"Tests authored. Agent remarks: {tester_remarks[:150]}")

            # 2. Graph executes run_pytest once deterministically (A4, T1.6)
            test_result = self._execute_pytest(workspace)
            state.latest_test_result = test_result
            _update_step_completion(workspace, state, test_result.passed)

            state.total_tokens = self.budget_tracker.total_tokens
            state.total_cost_usd = self.budget_tracker.total_cost_usd
            _persist_state_atomically(workspace, state)

            if test_result.passed:
                state.status = "completed"
                self._notify("Graph", "✅ Automated unit tests PASSED successfully!")
                _persist_state_atomically(workspace, state)
                return state

            # Tests failed - Initiate Self-Healing if attempts remain
            state.healing_cycle += 1
            if state.healing_cycle > settings.max_healing_cycles:
                state.status = "failed"
                self._notify(
                    "Graph",
                    f"❌ Max self-healing cycles ({settings.max_healing_cycles}) reached.",
                )
                _persist_state_atomically(workspace, state)
                return state

            state.status = "healing"
            self._notify(
                "Graph",
                f"⚠️ Tests failed! Self-Healing Loop (Attempt {state.healing_cycle}/{settings.max_healing_cycles})...",
            )
            _persist_state_atomically(workspace, state)

            # Feed error trace back to Coder Agent
            heal_instruction = (
                f"Unit tests FAILED with the following error trace:\n"
                f"{test_result.error_trace}\n\n"
                f"Diagnose the bug, read the existing source code, and use write_file to patch the broken code."
            )
            coder_patch_response = self.coder.write_code(
                task_instruction=heal_instruction,
                context=f"Pytest Output:\n{test_result.stdout}\n{test_result.stderr}",
            )
            self._notify("Coder", f"Bug patch applied. Remarks: {coder_patch_response[:200]}")

        return state
