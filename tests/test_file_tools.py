"""Security regression tests for sandboxed file tools.

Covers:
- F1: Path prefix collision bypass (startswith → is_relative_to)
- Absolute path injection
- Symlink escape
- Path traversal (../)
"""

import json

import pytest

from src.config import Settings
from src.tools.file_tools import (
    _resolve_safe_path,
    list_directory,
    read_file,
    write_file,
)


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """Create an isolated sandbox with monkeypatched settings."""
    sandbox_dir = tmp_path / "sandbox"
    sandbox_dir.mkdir()
    mock_settings = Settings(workspace_dir=sandbox_dir, isolate_runs=False)
    monkeypatch.setattr("src.tools.file_tools.settings", mock_settings)
    return sandbox_dir


class TestPathGuardSecurity:
    """F1 regression: _resolve_safe_path must block all escape vectors."""

    def test_prefix_collision_blocked(self, sandbox):
        """PoC for F1: sandbox vs sandbox_evil prefix bypass."""
        evil_dir = sandbox.parent / (sandbox.name + "_evil")
        evil_dir.mkdir()
        with pytest.raises(PermissionError):
            _resolve_safe_path(f"../{sandbox.name}_evil/payload.txt")

    def test_dotdot_traversal_blocked(self, sandbox):
        """Path traversal with ../ must be rejected."""
        with pytest.raises(PermissionError):
            _resolve_safe_path("../../../etc/passwd")

    def test_absolute_posix_path_blocked(self, sandbox):
        """Absolute POSIX path must be rejected."""
        with pytest.raises(PermissionError):
            _resolve_safe_path("/etc/passwd")

    def test_absolute_windows_path_blocked(self, sandbox):
        """Absolute Windows path must be rejected."""
        with pytest.raises(PermissionError):
            _resolve_safe_path("C:\\Windows\\System32\\cmd.exe")

    def test_symlink_escape_blocked(self, sandbox):
        """Symlink inside sandbox pointing outside must be rejected."""
        target_outside = sandbox.parent / "secret.txt"
        target_outside.write_text("secret data")
        link = sandbox / "sneaky_link"
        try:
            link.symlink_to(target_outside)
        except OSError:
            pytest.skip("Symlinks not supported (requires elevated privileges on Windows)")
        with pytest.raises(PermissionError):
            _resolve_safe_path("sneaky_link")

    def test_dot_only_stays_in_sandbox(self, sandbox):
        """Resolving '.' must stay within the sandbox."""
        result = _resolve_safe_path(".")
        assert result.is_relative_to(sandbox)

    def test_valid_nested_path_allowed(self, sandbox):
        """Normal nested paths within sandbox must work."""
        result = _resolve_safe_path("src/module.py")
        assert result.is_relative_to(sandbox)
        assert result == sandbox / "src" / "module.py"

    def test_valid_root_path_allowed(self, sandbox):
        """Simple filename in sandbox root must work."""
        result = _resolve_safe_path("file.txt")
        assert result == sandbox / "file.txt"


class TestFileToolsIsolated:
    """File tool functions using isolated sandbox via tmp_path."""

    def test_write_and_read_roundtrip(self, sandbox):
        """Write then read must return identical content."""
        code = "print('Hello from AI sandbox!')\n"
        write_res = json.loads(write_file("test_sample.py", code))
        assert write_res.get("success") is True

        read_res = json.loads(read_file("test_sample.py"))
        assert read_res.get("content") == code

    def test_list_directory(self, sandbox):
        """list_directory must work on sandbox root."""
        # Create a file so directory isn't empty
        (sandbox / "example.py").write_text("x = 1\n")
        result = json.loads(list_directory("."))
        assert "entries" in result
        assert isinstance(result["entries"], list)
        names = [e["name"] for e in result["entries"]]
        assert "example.py" in names

    def test_write_to_traversal_path_blocked(self, sandbox):
        """write_file with traversal path must fail."""
        result = json.loads(write_file("../../escape.txt", "pwned"))
        assert "error" in result

    def test_read_nonexistent_returns_error(self, sandbox):
        """Reading a missing file must return a JSON error, not raise."""
        result = json.loads(read_file("does_not_exist.py"))
        assert "error" in result
