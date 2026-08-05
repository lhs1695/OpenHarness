"""Repository policy model (spec §4.2)."""

from __future__ import annotations

import fnmatch

from pydantic import BaseModel, Field


def path_matches(path: str, patterns: list[str]) -> bool:
    """Whether ``path`` matches any policy glob pattern (''/''-normalized, dir prefix aware).

    Shared by risk scoring and quality gates so the matching semantics stay in one place.
    """
    normalized = path.replace("\\", "/")
    for pattern in patterns:
        pat = pattern.replace("\\", "/").rstrip("/")
        if fnmatch.fnmatch(normalized, pat):
            return True
        if fnmatch.fnmatch(normalized, pat + "/**"):
            return True
        if normalized.startswith(pat + "/"):
            return True
    return False


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
