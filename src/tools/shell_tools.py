"""Sandboxed shell and pytest execution tools for the Tester Agent."""

import json
import subprocess
import sys
from typing import Dict, Any, List
from src.config import settings
from src.tools.file_tools import _resolve_safe_path


def run_pytest(test_path: str = "tests") -> str:
    """Executes pytest in the workspace sandbox and captures structured test outcomes."""
    try:
        workspace = settings.get_resolved_workspace()
        target = (workspace / test_path).resolve()

        if not target.exists():
            return json.dumps({
                "passed": False,
                "error": f"Test target '{test_path}' does not exist inside sandbox.",
                "output": "",
            })

        # Execute pytest in a subprocess isolated to workspace directory
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-v", str(target)],
            cwd=str(workspace),
            capture_output=True,
            text=True,
            timeout=30,
        )

        passed = (result.returncode == 0)
        return json.dumps({
            "passed": passed,
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        })
    except subprocess.TimeoutExpired:
        return json.dumps({
            "passed": False,
            "error": "Pytest execution timed out after 30 seconds.",
            "output": "",
        })
    except Exception as e:
        return json.dumps({"passed": False, "error": f"Execution failed: {str(e)}"})


def execute_python(script_path: str) -> str:
    """Runs a standalone Python script in the workspace sandbox."""
    try:
        workspace = settings.get_resolved_workspace()
        path = _resolve_safe_path(script_path)

        if not path.exists():
            return json.dumps({"error": f"Script '{script_path}' not found."})

        result = subprocess.run(
            [sys.executable, str(path)],
            cwd=str(workspace),
            capture_output=True,
            text=True,
            timeout=20,
        )

        return json.dumps({
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        })
    except subprocess.TimeoutExpired:
        return json.dumps({"error": "Script execution timed out after 20 seconds."})
    except Exception as e:
        return json.dumps({"error": f"Failed to execute script: {str(e)}"})


SHELL_TOOL_SCHEMAS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "run_pytest",
            "description": "Runs pytest on test files in the sandbox to verify code correctness.",
            "parameters": {
                "type": "object",
                "properties": {
                    "test_path": {
                        "type": "string",
                        "description": "Relative path to test file or directory (e.g. 'tests/test_solution.py').",
                        "default": "tests",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "execute_python",
            "description": "Executes a Python script in the sandbox and returns its terminal output.",
            "parameters": {
                "type": "object",
                "properties": {
                    "script_path": {
                        "type": "string",
                        "description": "Relative path to python script to run.",
                    }
                },
                "required": ["script_path"],
            },
        },
    },
]
