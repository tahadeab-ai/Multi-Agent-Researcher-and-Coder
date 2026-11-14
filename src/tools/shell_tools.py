"""Sandboxed shell and pytest execution tools for the Tester Agent.

Security hardening (Phase 0):
- F2: All paths routed through _resolve_safe_path (hardened guard)
- F3: Subprocess environment scrubbed to explicit allowlist;
      process-group kill on timeout; configurable timeouts
"""

import contextlib
import json
import os
import platform
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any

import psutil

from src.config import settings
from src.tools.file_tools import _resolve_safe_path

# Environment variables safe to pass to sandboxed subprocesses.
# Secrets (OPENAI_API_KEY, ANTHROPIC_API_KEY, etc.) are explicitly excluded.
_ENV_ALLOWLIST = frozenset(
    {
        "PATH",
        "PYTHONHASHSEED",
        "LANG",
        # Windows-specific essentials
        "SYSTEMROOT",
        "TEMP",
        "TMP",
        "COMSPEC",
    }
)


def _make_sandbox_env(workspace: Path) -> dict[str, str]:
    """Build a scrubbed environment for sandboxed subprocess execution.

    Only variables in _ENV_ALLOWLIST are forwarded from the parent process.
    HOME/USERPROFILE are overridden to point at the workspace directory.
    TEMP/TMP are redirected to an isolated workspace/.tmp directory.
    """
    env: dict[str, str] = {}
    for key in _ENV_ALLOWLIST:
        val = os.environ.get(key)
        if val is not None:
            env[key] = val
    # Override HOME to workspace so generated code can't find dotfiles
    env["HOME"] = str(workspace)
    env["USERPROFILE"] = str(workspace)

    # Redirect TEMP/TMP to workspace/.tmp to avoid host temporary directory leakage
    sandbox_tmp = workspace / ".tmp"
    sandbox_tmp.mkdir(parents=True, exist_ok=True)
    env["TEMP"] = str(sandbox_tmp)
    env["TMP"] = str(sandbox_tmp)
    return env


def _terminate_process_tree(pid: int) -> None:
    """Terminate a process and all its descendants using a hybrid kill sequence.

    Steps:
    1. On POSIX: try process-group kill os.killpg with SIGKILL first.
    2. Fallback / Windows: suspend parent to halt spawning, collect descendants
       recursively, kill children, kill parent, and wait via psutil.
    """
    if platform.system() != "Windows" and hasattr(os, "killpg") and hasattr(os, "getpgid"):
        sig = getattr(signal, "SIGKILL", getattr(signal, "SIGTERM", 9))
        with contextlib.suppress(ProcessLookupError, PermissionError, OSError):
            getpgid_fn = getattr(os, "getpgid")  # noqa: B009
            os.killpg(getpgid_fn(pid), sig)

    try:
        parent = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return

    # 1. Suspend parent immediately to halt new spawns
    with contextlib.suppress(psutil.NoSuchProcess, psutil.AccessDenied):
        parent.suspend()

    # 2. Collect children recursively
    try:
        descendants = parent.children(recursive=True)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        descendants = []

    # 3. Kill children
    for child in descendants:
        with contextlib.suppress(psutil.NoSuchProcess, psutil.AccessDenied):
            child.kill()

    # 4. Kill parent
    with contextlib.suppress(psutil.NoSuchProcess, psutil.AccessDenied):
        parent.kill()

    # 5. Wait on all processes
    psutil.wait_procs(descendants + [parent], timeout=3.0)


def _run_sandboxed(
    cmd: list[str],
    workspace: Path,
    timeout: int,
) -> subprocess.CompletedProcess[str]:
    """Execute a command in a sandboxed subprocess with env scrubbing
    and process-group-aware timeout kill.

    Args:
        cmd: Command and arguments to execute.
        workspace: Working directory for the subprocess.
        timeout: Maximum execution time in seconds.

    Returns:
        CompletedProcess with captured stdout/stderr.

    Raises:
        subprocess.TimeoutExpired: If execution exceeds timeout.
    """
    is_windows = platform.system() == "Windows"

    popen_kwargs: dict[str, Any] = {
        "cwd": str(workspace),
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "text": True,
        "env": _make_sandbox_env(workspace),
    }

    if is_windows:
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        popen_kwargs["start_new_session"] = True

    proc = subprocess.Popen(cmd, **popen_kwargs)
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _terminate_process_tree(proc.pid)
        proc.wait()
        raise

    return subprocess.CompletedProcess(
        args=cmd,
        returncode=proc.returncode,
        stdout=stdout,
        stderr=stderr,
    )


def run_pytest(test_path: str = "tests") -> str:
    """Executes pytest in the workspace sandbox and captures structured test outcomes."""
    try:
        # Use hardened path guard to prevent sandbox escape (F2 fix)
        target = _resolve_safe_path(test_path)
        workspace = settings.get_resolved_workspace()

        if not target.exists():
            return json.dumps(
                {
                    "passed": False,
                    "error": f"Test target '{test_path}' does not exist inside sandbox.",
                    "output": "",
                }
            )

        # Execute pytest in a sandboxed subprocess (F3 fix: scrubbed env)
        result = _run_sandboxed(
            cmd=[sys.executable, "-m", "pytest", "-v", str(target)],
            workspace=workspace,
            timeout=settings.subprocess_timeout,
        )

        passed = result.returncode == 0
        return json.dumps(
            {
                "passed": passed,
                "exit_code": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        )
    except subprocess.TimeoutExpired:
        return json.dumps(
            {
                "passed": False,
                "error": f"Pytest execution timed out after {settings.subprocess_timeout} seconds.",
                "output": "",
            }
        )
    except PermissionError as e:
        return json.dumps(
            {
                "passed": False,
                "error": f"Access denied: {e!s}",
            }
        )
    except (subprocess.SubprocessError, OSError) as e:
        return json.dumps({"passed": False, "error": f"Execution failed: {e!s}"})


def execute_python(script_path: str) -> str:
    """Runs a standalone Python script in the workspace sandbox."""
    try:
        path = _resolve_safe_path(script_path)
        workspace = settings.get_resolved_workspace()

        if not path.exists():
            return json.dumps({"error": f"Script '{script_path}' not found."})

        # Execute in sandboxed subprocess (F3 fix: scrubbed env)
        result = _run_sandboxed(
            cmd=[sys.executable, str(path)],
            workspace=workspace,
            timeout=settings.subprocess_timeout,
        )

        return json.dumps(
            {
                "exit_code": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        )
    except subprocess.TimeoutExpired:
        return json.dumps(
            {
                "error": f"Script execution timed out after {settings.subprocess_timeout} seconds.",
            }
        )
    except PermissionError as e:
        return json.dumps({"error": f"Access denied: {e!s}"})
    except (subprocess.SubprocessError, OSError) as e:
        return json.dumps({"error": f"Failed to execute script: {e!s}"})


SHELL_TOOL_SCHEMAS: list[dict[str, Any]] = [
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
                        "description": (
                            "Relative path to test file or directory "
                            "(e.g. 'tests/test_solution.py')."
                        ),
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
            "description": (
                "Executes a Python script in the sandbox and returns its terminal output."
            ),
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
