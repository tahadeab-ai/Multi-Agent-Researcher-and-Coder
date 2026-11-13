"""Role-scoped tool factories enforcing write policies at the tool layer.

Security hardening (Phase 0, F4 & F6):
- Coder may write only outside tests/ (cannot edit/delete tests to force PASS)
- Tester may write only under tests/ (cannot tamper with implementation)
- Policies are enforced IN THE TOOL LAYER against resolved, canonical paths
- Case-folding and alias normalization (NTFS bypass mitigation) applied
"""

import json
import os
from collections.abc import Callable
from pathlib import Path, PurePosixPath


class WritePolicy:
    """Defines which paths a role may write to within the sandbox.

    Args:
        allow_patterns: Glob patterns for allowed paths. If set, path must match
                        at least one pattern.
        deny_patterns: Glob patterns for denied paths. Checked before allow patterns.
    """

    def __init__(
        self,
        allow_patterns: list[str] | None = None,
        deny_patterns: list[str] | None = None,
    ):
        self.allow_patterns = allow_patterns
        self.deny_patterns = deny_patterns

    def is_allowed(self, filepath: str) -> bool:
        """Check if a filepath is allowed under this policy.

        Applies os.path.normcase to both paths and patterns to correctly handle
        case-folding and aliases on case-insensitive filesystems (e.g. Windows NTFS)
        while preserving POSIX semantics on Linux/macOS.
        """
        # Convert to POSIX format with system-appropriate case folding
        normalized = os.path.normcase(filepath).replace("\\", "/")
        path = PurePosixPath(normalized)

        # Deny patterns take precedence
        if self.deny_patterns:
            for pattern in self.deny_patterns:
                p_norm = os.path.normcase(pattern).replace("\\", "/")
                if path.match(p_norm) or self._match_prefix(normalized, p_norm):
                    return False

        # If allow patterns exist, path must match at least one
        if self.allow_patterns:
            return any(
                path.match(os.path.normcase(p).replace("\\", "/"))
                or self._match_prefix(normalized, os.path.normcase(p).replace("\\", "/"))
                for p in self.allow_patterns
            )

        return True  # No restrictions if no patterns defined

    @staticmethod
    def _match_prefix(filepath: str, pattern: str) -> bool:
        """Check if filepath starts with the directory prefix of the pattern."""
        # Extract directory prefix from pattern (e.g., "tests/**" -> "tests/")
        if "**" in pattern:
            prefix = pattern.split("**")[0]
            return filepath.startswith(prefix)
        if "*" in pattern:
            prefix = pattern.rsplit("/", 1)[0] + "/" if "/" in pattern else ""
            return bool(prefix) and filepath.startswith(prefix)
        return False


# Pre-defined role policies (includes 8.3 short name patterns)
CODER_POLICY = WritePolicy(deny_patterns=["tests/*", "tests/**", "tests~*/*", "tests~*/**"])
TESTER_POLICY = WritePolicy(allow_patterns=["tests/*", "tests/**", "tests~*/*", "tests~*/**"])


def make_scoped_write_file(policy: WritePolicy) -> Callable[[str, str], str]:
    """Factory: returns a write_file function restricted by the given policy.

    The returned function resolves the filepath against the sandbox first to prevent
    alias bypasses (e.g. 'Tests/...', 'tests ./...', 'TESTS~1/...', 'x/../tests/...'),
    verifies policy authorization against the relative resolved path, and then writes.
    """

    def scoped_write_file(filepath: str, content: str) -> str:
        from src.tools.file_tools import _resolve_safe_path, settings, write_file

        try:
            resolved = _resolve_safe_path(filepath)
        except PermissionError as e:
            return json.dumps({"error": f"Access denied: {e}"})

        # Strip extended-length prefix on Windows if present
        resolved_str = str(resolved)
        if resolved_str.startswith("\\\\?\\"):
            resolved = Path(resolved_str[4:])

        workspace = settings.get_resolved_workspace()
        workspace_str = str(workspace)
        if workspace_str.startswith("\\\\?\\"):
            workspace = Path(workspace_str[4:])

        try:
            rel = resolved.relative_to(workspace).as_posix()
        except ValueError:
            return json.dumps({"error": f"Access denied: Path '{filepath}' escapes sandbox."})

        # Check policy on both raw input and resolved relative path
        if not policy.is_allowed(rel) or not policy.is_allowed(filepath):
            return json.dumps(
                {
                    "error": (
                        f"Permission denied: role policy forbids writing to '{filepath}'. "
                        f"This file is outside your allowed write scope."
                    ),
                }
            )

        return write_file(filepath, content)

    scoped_write_file.__name__ = "write_file"
    scoped_write_file.__doc__ = "Writes content to an allowed file path within the sandbox."
    return scoped_write_file
