"""State Machine Graph orchestrating Supervisor, Coder, and Tester agents."""

from typing import Callable, Optional
from rich.console import Console
from rich.panel import Panel
from src.config import settings
from src.schema import AgentState
from src.agents.supervisor import SupervisorAgent
from src.agents.coder import CoderAgent
from src.agents.tester import TesterAgent

console = Console()


class MultiAgentGraph:
    """Orchestrates the multi-agent development workflow with test-driven self-healing."""

    def __init__(self, on_step_callback: Optional[Callable[[str, str], None]] = None):
        self.supervisor = SupervisorAgent()
        self.coder = CoderAgent()
        self.tester = TesterAgent()
        self.on_step_callback = on_step_callback

    def _notify(self, stage: str, message: str):
        """Dispatches progress updates to callback and terminal."""
        if self.on_step_callback:
            self.on_step_callback(stage, message)
        else:
            console.print(f"[bold cyan][{stage}][/bold cyan] {message}")

    def run(self, user_prompt: str) -> AgentState:
        """Executes the full multi-agent development lifecycle."""
        state = AgentState(user_prompt=user_prompt, status="planning")

        # ----------------------------------------------------
        # Stage 1: Planning (Supervisor Agent)
        # ----------------------------------------------------
        self._notify("Supervisor", "Analyzing requirements and creating architecture plan...")
        state.plan = self.supervisor.plan_task(user_prompt=user_prompt)
        state.status = "coding"

        plan_summary = (
            f"Goal: {state.plan.goal}\n"
            f"Architecture: {state.plan.architecture_notes}\n"
            f"Steps: {len(state.plan.steps)}"
        )
        self._notify("Supervisor", f"Plan formulated:\n{plan_summary}")

        # ----------------------------------------------------
        # Stage 2: Implementation (Coder Agent)
        # ----------------------------------------------------
        self._notify("Coder", "Generating Python source code according to plan...")
        plan_context = state.plan.model_dump_json(indent=2)
        code_instruction = (
            f"Implement the solution for this goal: '{state.plan.goal}'.\n"
            f"Follow these architectural steps carefully:\n{plan_context}\n"
            f"Write the implementation file(s) to the sandbox using write_file."
        )
        coder_response = self.coder.write_code(
            task_instruction=code_instruction,
            context=f"User original requirement: {user_prompt}",
        )
        self._notify("Coder", f"Implementation completed. Agent remarks: {coder_response[:200]}")
        state.status = "testing"

        # ----------------------------------------------------
        # Stage 3: Verification & Self-Healing Loop (Tester Agent)
        # ----------------------------------------------------
        while state.healing_cycle <= settings.max_healing_cycles:
            self._notify("Tester", f"Running test verification suite (Cycle {state.healing_cycle + 1})...")

            test_instruction = (
                f"Verify the implementation for: '{state.plan.goal}'.\n"
                f"1. Read the implemented files.\n"
                f"2. Write comprehensive pytest unit tests into 'tests/test_solution.py'.\n"
                f"3. Run pytest using run_pytest(test_path='tests/test_solution.py') and inspect the results."
            )
            test_result = self.tester.verify_and_test(
                task_instruction=test_instruction,
                context=f"Current Architecture Plan:\n{plan_context}",
            )
            state.latest_test_result = test_result

            if test_result.passed:
                state.status = "completed"
                self._notify("Tester", "✅ All automated unit tests PASSED successfully!")
                return state

            # Tests failed - Initiate Self-Healing if attempts remain
            state.healing_cycle += 1
            if state.healing_cycle > settings.max_healing_cycles:
                state.status = "failed"
                self._notify(
                    "Graph",
                    f"❌ Max self-healing cycles ({settings.max_healing_cycles}) reached. Tests still failing.",
                )
                return state

            state.status = "healing"
            self._notify(
                "Graph",
                f"⚠️ Tests failed! Activating Self-Healing Loop (Attempt {state.healing_cycle}/{settings.max_healing_cycles})...",
            )

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
