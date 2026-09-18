"""Configuration management for Multi-Agent Coder using Pydantic Settings."""

from pathlib import Path
from typing import Literal, Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings validated from environment variables or .env file."""

    llm_provider: Literal["openai", "ollama", "anthropic"] = Field(
        default="openai", description="LLM provider backend"
    )
    llm_model: str = Field(
        default="gpt-4o-mini", description="Model name to use for agent reasoning"
    )

    openai_api_key: Optional[str] = Field(
        default=None, description="OpenAI API key (required if provider is openai)"
    )
    anthropic_api_key: Optional[str] = Field(
        default=None, description="Anthropic API key (optional)"
    )
    ollama_base_url: str = Field(
        default="http://localhost:11434/v1",
        description="Base URL for local Ollama OpenAI-compatible endpoint",
    )

    max_agent_steps: int = Field(
        default=6, ge=1, le=20, description="Max tool execution turns per agent"
    )
    max_healing_cycles: int = Field(
        default=3, ge=1, le=10, description="Max test-driven self-healing debug cycles"
    )

    workspace_dir: Path = Field(
        default=Path("./sandbox"),
        description="Isolated directory where agents create and test code",
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


# Singleton configuration instance
settings = Settings()
