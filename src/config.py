"""Configuration management for Multi-Agent Coder using Pydantic Settings."""

import uuid
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings validated from environment variables or .env file."""

    llm_provider: Literal["openai", "ollama", "anthropic"] = Field(default="openai", description="LLM provider backend")
    llm_model: str = Field(default="gpt-4o-mini", description="Model name to use for agent reasoning")

    openai_api_key: str | None = Field(default=None, description="OpenAI API key (required if provider is openai)")
    anthropic_api_key: str | None = Field(default=None, description="Anthropic API key (optional)")
    ollama_base_url: str = Field(
        default="http://localhost:11434/v1",
        description="Base URL for local Ollama OpenAI-compatible endpoint",
    )

    max_agent_steps: int = Field(default=6, ge=1, le=20, description="Max tool execution turns per agent")
    max_healing_cycles: int = Field(default=3, ge=1, le=10, description="Max test-driven self-healing debug cycles")

    workspace_dir: Path = Field(
        default=Path("./sandbox"),
        description="Isolated directory where agents create and test code",
    )
    subprocess_timeout: int = Field(
        default=30,
        ge=5,
        le=300,
        description="Timeout in seconds for sandboxed subprocess execution",
    )
    run_id: str = Field(
        default_factory=lambda: uuid.uuid4().hex[:12],
        description="Unique run identifier for workspace isolation",
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def get_resolved_workspace(self) -> Path:
        """Returns the absolute, resolved path to the workspace directory."""
        path = self.workspace_dir.resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path

    def get_run_workspace(self) -> Path:
        """Returns the isolated workspace for the current run."""
        base = self.get_resolved_workspace()
        run_dir = base / "runs" / self.run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        return run_dir

    def validate_provider(self) -> None:
        """Validate that the configured provider has all required credentials.

        Raises:
            ConfigError: If the provider is misconfigured.
        """
        from src.errors import ConfigError

        if self.llm_provider == "openai" and not self.openai_api_key:
            raise ConfigError(
                "LLM_PROVIDER is 'openai' but OPENAI_API_KEY is not set. "
                "Set it in your .env file or as an environment variable."
            )
        if self.llm_provider == "anthropic":
            raise ConfigError(
                "LLM_PROVIDER 'anthropic' is not yet implemented. "
                "Use 'openai' or 'ollama' instead. "
                "See https://github.com/tahadeab-ai/Multi-Agent-Researcher-and-Coder/issues "
                "for updates on Anthropic support."
            )


# Singleton configuration instance
settings = Settings()
