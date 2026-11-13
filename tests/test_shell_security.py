"""Security regression tests for shell execution tools.

Covers:
- F2: run_pytest must not accept paths escaping sandbox
- F3: subprocess must NOT inherit sensitive env vars (OPENAI_API_KEY)
- F3: process-group timeout kill
"""

import json
import os
import time

import psutil
import pytest

from src.config import Settings
from src.tools.shell_tools import _make_sandbox_env, execute_python, run_pytest


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """Create an isolated sandbox with monkeypatched settings."""
    sandbox_dir = tmp_path / "sandbox"
    sandbox_dir.mkdir()
    (sandbox_dir / "tests").mkdir()
    mock_settings = Settings(
        workspace_dir=sandbox_dir,
        isolate_runs=False,
        subprocess_timeout=10,
    )
    monkeypatch.setattr("src.tools.file_tools.settings", mock_settings)
    monkeypatch.setattr("src.tools.shell_tools.settings", mock_settings)
    return sandbox_dir


class TestRunPytestGuard:
    """F2 regression: run_pytest must not accept paths escaping sandbox."""

    def test_absolute_path_rejected(self, sandbox):
        """Absolute test_path must be rejected with access denied."""
        result = json.loads(run_pytest("/etc"))
        assert result["passed"] is False
        assert "denied" in str(result).lower() or "error" in result

    def test_traversal_path_rejected(self, sandbox):
        """Traversal test_path must be rejected."""
        result = json.loads(run_pytest("../../../etc"))
        assert result["passed"] is False

    def test_valid_test_path_accepted(self, sandbox):
        """Valid relative test path should be accepted (may fail if no tests exist)."""
        # Write a minimal test file
        test_file = sandbox / "tests" / "test_dummy.py"
        test_file.write_text("def test_pass(): assert True\n")
        result = json.loads(run_pytest("tests/test_dummy.py"))
        # May or may not pass depending on environment, but should not error on path
        assert "denied" not in str(result).lower()


class TestExecutePythonGuard:
    """execute_python must also respect sandbox guard."""

    def test_absolute_script_path_rejected(self, sandbox):
        """Absolute script_path must be rejected."""
        result = json.loads(execute_python("/etc/passwd"))
        assert "denied" in str(result).lower() or "error" in result


class TestEnvScrubbing:
    """F3 regression: subprocess must NOT inherit sensitive env vars."""

    def test_sandbox_env_excludes_api_keys(self, sandbox):
        """_make_sandbox_env must not include OPENAI_API_KEY."""
        os.environ["OPENAI_API_KEY"] = "sk-test-secret-key-12345"
        try:
            env = _make_sandbox_env(sandbox)
            assert "OPENAI_API_KEY" not in env
            assert "ANTHROPIC_API_KEY" not in env
        finally:
            del os.environ["OPENAI_API_KEY"]

    def test_sandbox_env_includes_path(self, sandbox):
        """_make_sandbox_env must include PATH for basic operation."""
        env = _make_sandbox_env(sandbox)
        assert "PATH" in env

    def test_sandbox_env_overrides_home(self, sandbox):
        """HOME/USERPROFILE must be set to the workspace, not the real home."""
        env = _make_sandbox_env(sandbox)
        assert env["HOME"] == str(sandbox)
        assert env["USERPROFILE"] == str(sandbox)

    def test_api_key_not_leaked_via_execute_python(self, sandbox, monkeypatch):
        """Generated code executed via execute_python must not see API keys."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret-key")
        # Write a script that checks for the key
        script = sandbox / "check_env.py"
        script.write_text(
            "import os, sys\nkey = os.environ.get('OPENAI_API_KEY', 'NOT_FOUND')\nprint(key)\n"
        )
        result = json.loads(execute_python("check_env.py"))
        assert "NOT_FOUND" in result.get("stdout", ""), (
            f"OPENAI_API_KEY leaked to subprocess! stdout={result.get('stdout')}"
        )


class TestProcessTermination:
    """F3 regression: process tree termination on timeout."""

    def test_grandchild_sleeper_terminated_on_timeout(self, sandbox, monkeypatch):
        """Spawns parent -> child -> grandchild sleeper; on timeout, grandchild is terminated."""
        mock_settings = Settings(
            workspace_dir=sandbox,
            isolate_runs=False,
            subprocess_timeout=2,
        )
        monkeypatch.setattr("src.tools.file_tools.settings", mock_settings)
        monkeypatch.setattr("src.tools.shell_tools.settings", mock_settings)

        pid_file = sandbox / "grandchild.pid"

        grandchild_script = sandbox / "grandchild.py"
        grandchild_script.write_text(
            "import os, time, sys\n"
            "pid_file = sys.argv[1]\n"
            "with open(pid_file, 'w') as f:\n"
            "    f.write(str(os.getpid()))\n"
            "time.sleep(60)\n"
        )

        child_script = sandbox / "child.py"
        child_script.write_text(
            "import subprocess, sys, time\n"
            "pid_file = sys.argv[1]\n"
            "proc = subprocess.Popen([sys.executable, 'grandchild.py', pid_file])\n"
            "time.sleep(60)\n"
        )

        parent_script = sandbox / "parent.py"
        parent_script.write_text(
            f"import subprocess, sys, time\n"
            f"proc = subprocess.Popen([sys.executable, 'child.py', r'{pid_file}'])\n"
            f"time.sleep(60)\n"
        )

        res = json.loads(execute_python("parent.py"))
        assert "timed out" in res.get("error", "")

        time.sleep(0.5)

        assert pid_file.exists(), "Grandchild did not create PID file in time"
        grandchild_pid = int(pid_file.read_text().strip())

        is_running = False
        if psutil.pid_exists(grandchild_pid):
            try:
                proc = psutil.Process(grandchild_pid)
                is_running = proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE
            except psutil.NoSuchProcess:
                is_running = False

        assert not is_running, f"Grandchild process {grandchild_pid} is still running!"
