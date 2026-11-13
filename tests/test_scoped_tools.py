"""Tests for role-scoped write tool enforcement.

Covers:
- F4: Coder cannot write to tests/ (reward hacking prevention)
- F4: Tester cannot write to implementation files
"""

import json

import pytest

from src.config import Settings
from src.tools.scoped_tools import (
    CODER_POLICY,
    TESTER_POLICY,
    WritePolicy,
    make_scoped_write_file,
)


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """Create an isolated sandbox with monkeypatched settings."""
    sandbox_dir = tmp_path / "sandbox"
    sandbox_dir.mkdir()
    (sandbox_dir / "tests").mkdir()
    mock_settings = Settings(workspace_dir=sandbox_dir)
    monkeypatch.setattr("src.tools.file_tools.settings", mock_settings)
    return sandbox_dir


class TestCoderPolicy:
    """Coder must be able to write implementation but NOT tests."""

    def test_coder_can_write_implementation(self, sandbox):
        write = make_scoped_write_file(CODER_POLICY)
        result = json.loads(write("solution.py", "print('hello')"))
        assert result.get("success") is True

    def test_coder_can_write_nested_src(self, sandbox):
        write = make_scoped_write_file(CODER_POLICY)
        result = json.loads(write("src/utils/helpers.py", "x = 1"))
        assert result.get("success") is True

    def test_coder_cannot_write_test_file(self, sandbox):
        write = make_scoped_write_file(CODER_POLICY)
        result = json.loads(write("tests/test_solution.py", "assert True"))
        assert "error" in result
        assert "denied" in result["error"].lower() or "permission" in result["error"].lower()

    def test_coder_cannot_write_nested_test(self, sandbox):
        write = make_scoped_write_file(CODER_POLICY)
        result = json.loads(write("tests/integration/test_api.py", "assert True"))
        assert "error" in result


class TestTesterPolicy:
    """Tester must be able to write tests but NOT implementation."""

    def test_tester_can_write_test_file(self, sandbox):
        write = make_scoped_write_file(TESTER_POLICY)
        result = json.loads(write("tests/test_solution.py", "def test_x(): assert True"))
        assert result.get("success") is True

    def test_tester_can_write_nested_test(self, sandbox):
        write = make_scoped_write_file(TESTER_POLICY)
        result = json.loads(write("tests/unit/test_math.py", "assert 1 == 1"))
        assert result.get("success") is True

    def test_tester_cannot_write_implementation(self, sandbox):
        write = make_scoped_write_file(TESTER_POLICY)
        result = json.loads(write("solution.py", "print('hacked')"))
        assert "error" in result

    def test_tester_cannot_write_src(self, sandbox):
        write = make_scoped_write_file(TESTER_POLICY)
        result = json.loads(write("src/main.py", "import os"))
        assert "error" in result


class TestCustomPolicy:
    """WritePolicy with custom patterns."""

    def test_unrestricted_policy_allows_all(self, sandbox):
        policy = WritePolicy()
        write = make_scoped_write_file(policy)
        result = json.loads(write("anywhere.py", "x = 1"))
        assert result.get("success") is True

    def test_deny_only_policy(self, sandbox):
        policy = WritePolicy(deny_patterns=["*.secret"])
        assert policy.is_allowed("data.json") is True
        assert policy.is_allowed("creds.secret") is False

    def test_allow_only_policy(self, sandbox):
        policy = WritePolicy(allow_patterns=["docs/*"])
        assert policy.is_allowed("docs/readme.md") is True
        assert policy.is_allowed("src/code.py") is False
