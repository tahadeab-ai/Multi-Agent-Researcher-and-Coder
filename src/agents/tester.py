"""Tester Agent responsible for writing tests, running pytest, and diagnosing failures."""

import json
from src.agents.base import BaseAgent
from src.schema import TestResult
from src.tools.file_tools import (
    FILE_TOOL_SCHEMAS,
    read_file,
    write_file,
    list_directory,
)
from src.tools.shell_tools import (
    SHELL_TOOL_SCHEMAS,
    run_pytest,
    execute_python,
)


TESTER_SYSTEM_PROMPT = """You are the Lead QA and Verification Engineer on the team.
Your mission is to ensure software quality through comprehensive automated testing.

Responsibilities:
1. Read the code written by the Coder Agent using read_file.
2. Write thorough unit tests using pytest via write_file (e.g. into 'tests/test_solution.py').
3. Run the test suite using run_pytest(test_path='tests/test_solution.py').
4. If tests fail, diagnose the failure clearly, pinpointing the failing assertion, file, and line number.
5. Do not stop until you have run the tests and verified their output.
"""


class TesterAgent(BaseAgent):
    """Tester Agent equipped with file and shell execution tools."""

    def __init__(self):
        super().__init__(
            name="Tester",
            role_prompt=TESTER_SYSTEM_PROMPT,
            tools=FILE_TOOL_SCHEMAS + SHELL_TOOL_SCHEMAS,
            tool_functions={
                "read_file": read_file,
                "write_file": write_file,
                "list_directory": list_directory,
                "run_pytest": run_pytest,
                "execute_python": execute_python,
            },
            temperature=0.1,
        )

    def verify_and_test(self, task_instruction: str, context: str) -> TestResult:
        """Runs testing turn and parses the outcome into a TestResult schema."""
        output = self.run(user_instruction=task_instruction, context=context)

        # Run automated pytest verification directly
        raw_test_run = run_pytest("tests")
        try:
            data = json.loads(raw_test_run)
            passed = data.get("passed", False)
            stdout = data.get("stdout", "")
            stderr = data.get("stderr", "")

            # If there's an error trace, extract the summary
            error_trace = None
            if not passed:
                error_trace = stdout or stderr or data.get("error", "Unknown test failure")

            return TestResult(
                passed=passed,
                summary=f"Pytest {'PASSED' if passed else 'FAILED'}. Agent remarks: {output[:300]}",
                stdout=stdout,
                stderr=stderr,
                error_trace=error_trace,
            )
        except Exception as err:
            return TestResult(
                passed=False,
                summary=f"Failed to parse test execution output: {str(err)}",
                error_trace=str(err),
            )
