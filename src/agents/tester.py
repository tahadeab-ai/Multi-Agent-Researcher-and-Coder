"""Tester Agent responsible for authoring unit tests."""

from __future__ import annotations

from typing import Any

from src.agents.base import BaseAgent
from src.llm.budget import BudgetTracker
from src.llm.protocol import LLMProvider
from src.tools.file_tools import (
    FILE_TOOL_SCHEMAS,
    list_directory,
    read_file,
)
from src.tools.scoped_tools import TESTER_POLICY, make_scoped_write_file

TESTER_SYSTEM_PROMPT = """You are the Lead QA and Verification Engineer on the team.
Your mission is to ensure software quality through comprehensive automated testing.

Responsibilities:
1. Read the code written by the Coder Agent using read_file.
2. Write thorough unit tests using pytest via write_file (e.g. into 'tests/test_solution.py').
3. Focus purely on writing robust tests covering happy path, edge cases, and boundary conditions.
"""


class TesterAgent(BaseAgent):
    """Tester Agent equipped with file manipulation tools."""

    def __init__(
        self,
        provider: LLMProvider | None = None,
        budget_tracker: BudgetTracker | None = None,
        sleep_func: Any = None,
    ) -> None:
        super().__init__(
            name="Tester",
            role_prompt=TESTER_SYSTEM_PROMPT,
            tools=FILE_TOOL_SCHEMAS,
            tool_functions={
                "read_file": read_file,
                "write_file": make_scoped_write_file(TESTER_POLICY),
                "list_directory": list_directory,
            },
            temperature=0.1,
            provider=provider,
            budget_tracker=budget_tracker,
            sleep_func=sleep_func,
        )

    def write_tests(self, task_instruction: str, context: str) -> str:
        """Runs test authoring turn."""
        return self.run(user_instruction=task_instruction, context=context)
