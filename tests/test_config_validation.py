"""Tests for provider validation and configuration (F5).

Covers:
- OpenAI requires API key
- Anthropic raises ConfigError ("not implemented")
- Ollama works without key
- Dummy key removal verification
"""

import pytest

from src.config import Settings
from src.errors import ConfigError


class TestProviderValidation:
    """F5 regression: provider validation must catch misconfigurations."""

    def test_openai_requires_api_key(self):
        """OpenAI provider without API key must raise ConfigError."""
        s = Settings(llm_provider="openai", openai_api_key=None)
        with pytest.raises(ConfigError, match="OPENAI_API_KEY"):
            s.validate_provider()

    def test_anthropic_not_implemented(self):
        """Anthropic provider must raise ConfigError with 'not implemented'."""
        s = Settings(llm_provider="anthropic")
        with pytest.raises(ConfigError, match="not yet implemented"):
            s.validate_provider()

    def test_ollama_valid_without_key(self):
        """Ollama provider should not require any API key."""
        s = Settings(llm_provider="ollama")
        s.validate_provider()  # Should not raise

    def test_openai_valid_with_key(self):
        """OpenAI provider with valid key should not raise."""
        s = Settings(llm_provider="openai", openai_api_key="sk-real-key")
        s.validate_provider()  # Should not raise


class TestConfigSettings:
    """Settings fields added in Phase 0."""

    def test_subprocess_timeout_default(self):
        """Default subprocess timeout must be 30 seconds."""
        s = Settings()
        assert s.subprocess_timeout == 30

    def test_subprocess_timeout_configurable(self):
        """subprocess_timeout must be configurable."""
        s = Settings(subprocess_timeout=60)
        assert s.subprocess_timeout == 60

    def test_run_id_auto_generated(self):
        """run_id must be auto-generated and non-empty."""
        s = Settings()
        assert len(s.run_id) == 12
        assert s.run_id.isalnum()

    def test_run_id_unique(self):
        """Each Settings instance must get a different run_id."""
        s1 = Settings()
        s2 = Settings()
        assert s1.run_id != s2.run_id

    def test_isolate_runs_default(self):
        """isolate_runs must default to True."""
        s = Settings()
        assert s.isolate_runs is True

    def test_per_run_workspace_and_latest_pointer(self, tmp_path):
        """get_resolved_workspace must create runs/<uuid> and update LATEST pointer."""
        sandbox_base = tmp_path / "sandbox"
        s = Settings(workspace_dir=sandbox_base, isolate_runs=True)
        resolved = s.get_resolved_workspace()

        expected_run_dir = sandbox_base / "runs" / s.run_id
        assert resolved == expected_run_dir.resolve()
        assert resolved.exists()
        assert resolved.is_dir()

        latest_file = sandbox_base / "LATEST"
        assert latest_file.exists()
        assert latest_file.read_text(encoding="utf-8") == str(resolved)
