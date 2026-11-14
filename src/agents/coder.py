"""Coder Agent responsible for writing and modifying Python implementation files."""

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
from src.tools.scoped_tools import CODER_POLICY, make_scoped_write_file

CODER_SYSTEM_PROMPT = """You are the Principal Python Engineer on the team.
Your responsibility is to write clean, idiomatic, robust, and fully-typed Python source code.

Standards to follow:
1. Always add type hints to function arguments and returns.
2. Handle potential edge cases (e.g. None values, empty lists, division by zero).
3. Do not leave placeholder comments like '# implement here' or 'pass'; write full implementations.
4. Use write_file to save your files to disk in the sandbox.
5. If fixing bugs from test failures, read the error traceback carefully and modify only what is broken.
"""


class CoderAgent(BaseAgent):
    """Coder Agent equipped with file manipulation tools."""

    def __init__(
        self,
        provider: LLMProvider | None = None,
        budget_tracker: BudgetTracker | None = None,
        sleep_func: Any = None,
    ) -> None:
        super().__init__(
            name="Coder",
            role_prompt=CODER_SYSTEM_PROMPT,
            tools=FILE_TOOL_SCHEMAS,
            tool_functions={
                "read_file": read_file,
                "write_file": make_scoped_write_file(CODER_POLICY),
                "list_directory": list_directory,
            },
            temperature=0.2,
            provider=provider,
            budget_tracker=budget_tracker,
            sleep_func=sleep_func,
        )

    def write_code(self, task_instruction: str, context: str) -> str:
        """Executes code creation turn."""
        return self.run(user_instruction=task_instruction, context=context)
