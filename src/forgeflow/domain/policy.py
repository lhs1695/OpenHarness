"""Repository policy model (spec §4.2)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class RepositoryPolicy(BaseModel):
    """Per-repository execution and approval policy."""

    repository: str
    sensitive_paths: list[str] = Field(default_factory=list)
    forbidden_paths: list[str] = Field(default_factory=list)
    required_commands: list[str] = Field(default_factory=list)
    forbidden_commands: list[str] = Field(default_factory=list)
    max_changed_files: int = 12
    max_execution_minutes: int = 45
    max_agent_steps: int = 40
    approval_rules: dict[str, list[str]] = Field(default_factory=dict)
    model_strategy: str = "default"
