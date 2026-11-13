"""Role-scoped tool factories enforcing write policies at the tool layer.

Security hardening (Phase 0, F4):
- Coder may write only outside tests/ (cannot edit/delete tests to force PASS)
- Tester may write only under tests/ (cannot tamper with implementation)
- Policies are enforced IN THE TOOL LAYER, not via prompt instructions
"""

import json
from collections.abc import Callable
from pathlib import PurePosixPath


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

        Uses PurePosixPath.match for cross-platform glob matching.
        """
        # Normalize to forward slashes for consistent matching
        normalized = filepath.replace("\\", "/")
        path = PurePosixPath(normalized)

        # Deny patterns take precedence
        if self.deny_patterns:
            for pattern in self.deny_patterns:
                if path.match(pattern) or self._match_prefix(normalized, pattern):
                    return False

        # If allow patterns exist, path must match at least one
        if self.allow_patterns:
            return any(path.match(p) or self._match_prefix(normalized, p) for p in self.allow_patterns)

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


# Pre-defined role policies
CODER_POLICY = WritePolicy(deny_patterns=["tests/*", "tests/**"])
TESTER_POLICY = WritePolicy(allow_patterns=["tests/*", "tests/**"])


def make_scoped_write_file(policy: WritePolicy) -> Callable[[str, str], str]:
    """Factory: returns a write_file function restricted by the given policy.

    The returned function has the same signature as file_tools.write_file
    but rejects writes that violate the policy with a JSON error response.
    """

    def scoped_write_file(filepath: str, content: str) -> str:
        if not policy.is_allowed(filepath):
            return json.dumps(
                {
                    "error": (
                        f"Permission denied: role policy forbids writing to '{filepath}'. "
                        f"This file is outside your allowed write scope."
                    ),
                }
            )
        # Delegate to the real write_file (which also applies sandbox guard)
        from src.tools.file_tools import write_file

        return write_file(filepath, content)

    scoped_write_file.__name__ = "write_file"
    scoped_write_file.__doc__ = "Writes content to an allowed file path within the sandbox."
    return scoped_write_file
