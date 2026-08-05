"""Task executors — the pluggable engine behind the orchestrator.

M6 ships a local executor that runs a task's required commands in an isolated
worktree and evaluates the deterministic quality gates (no model calls).  The
plan/review model-driven stages are wired in later milestones; the seam is the
``TaskExecutor`` protocol so tests inject a fake.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from forgeflow.domain.policy import RepositoryPolicy
from forgeflow.execution.base import ExecutionResult
from forgeflow.execution.worktree import WorktreeExecutionBackend
from forgeflow.infrastructure.store import StoredTask
from forgeflow.quality.reports import QualityGateRunner


@dataclass(frozen=True)
class ExecutionOutcome:
    status: str
    error: str | None = None
    gate_summary: dict[str, object] = field(default_factory=dict)
    command_results: dict[str, ExecutionResult] = field(default_factory=dict)


class TaskExecutor(Protocol):
    async def execute(self, task: StoredTask) -> ExecutionOutcome: ...


class LocalTaskExecutor:
    """Run required commands in a worktree and evaluate quality gates."""

    def __init__(self, *, repo_path: str | Path, policy: RepositoryPolicy) -> None:
        self._repo_path = Path(repo_path).resolve()
        self._policy = policy

    async def execute(self, task: StoredTask) -> ExecutionOutcome:
        backend = WorktreeExecutionBackend(self._repo_path)
        workspace = Path(await backend.prepare(task.id, task.repository))
        try:
            runner = QualityGateRunner(backend, self._policy)
            report = await runner.evaluate(
                task_id=task.id,
                task_type=task.task_type,
                workspace=workspace,
            )
            command_results = dict(report.command_results)
            if report.passed:
                return ExecutionOutcome(
                    status="completed",
                    gate_summary=report.summarize(),
                    command_results=command_results,
                )
            return ExecutionOutcome(
                status="failed",
                gate_summary=report.summarize(),
                error=f"quality gates failed: {report.summarize()['hard_failures']}",
                command_results=command_results,
            )
        finally:
            await backend.cleanup()
