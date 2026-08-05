"""Execution backend abstraction (spec §7.3).

Backends isolate task execution into a workspace (Local Worktree in M3,
Docker sandbox in a later milestone).  Commands are always passed as
structured argument lists — never concatenated shell strings.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from forgeflow.errors import PathEscapeError


@dataclass(frozen=True)
class ExecutionResult:
    command: list[str]
    returncode: int
    stdout: str
    stderr: str
    duration_ms: int
    timed_out: bool = False


@dataclass(frozen=True)
class Artifact:
    artifact_type: str
    path: str
    metadata: dict[str, object] = field(default_factory=dict)


class ExecutionBackend(Protocol):
    """Minimal surface every ForgeFlow execution backend provides."""

    async def prepare(self, task_id: str, repository: str) -> str: ...

    async def execute(self, command: list[str], timeout_seconds: int) -> ExecutionResult: ...

    async def collect_artifacts(self) -> list[Artifact]: ...

    async def cancel(self) -> None: ...

    async def cleanup(self) -> None: ...


def resolve_workspace_path(path: str | Path, workspace: Path) -> Path:
    """Resolve ``path`` to an absolute path inside ``workspace`` or raise.

    Symlinks and ``..`` segments are resolved first, so a symlink pointing
    outside the workspace is rejected (spec §11.2).
    """
    root = workspace.resolve()
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve()
    if not resolved.is_relative_to(root):
        raise PathEscapeError(f"路径越界：{resolved} 不在工作区 {root}")
    return resolved
