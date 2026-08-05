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
from forgeflow.evaluation.datasets import EvalCase, EvalResult
from forgeflow.evaluation.strategies import EvalStrategy
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


def stored_to_case(task: StoredTask) -> EvalCase:
    """Adapt a persisted StoredTask into the evaluation EvalCase surface."""
    return EvalCase(
        case_id=task.id,
        repository=task.repository,
        title=task.title,
        description=task.description,
        task_type=task.task_type,
        priority=task.priority,
        acceptance_rules=tuple(task.acceptance_criteria),
        tags=tuple(task.risk_tags),
    )


def outcome_from_eval(result: EvalResult) -> ExecutionOutcome:
    """Map an online-strategy EvalResult onto the orchestrator's ExecutionOutcome."""
    gate_summary: dict[str, object] = {
        "status": result.status,
        "failure_class": result.failure_class,
        "tests_passed": result.tests_passed,
        "token_usage": result.token_usage,
        "cost": result.cost,
        "duration_ms": result.duration_ms,
    }
    if result.status == "passed":
        return ExecutionOutcome(status="completed", gate_summary=gate_summary)
    return ExecutionOutcome(
        status="failed",
        error=result.error,
        gate_summary=gate_summary,
    )


class ModelDrivenTaskExecutor:
    """Execute a task with a real OpenHarness agent in an isolated worktree.

    Reuses the online plan_gates strategy (adapter plan -> agent repair ->
    quality gates) and adapts StoredTask -> EvalCase -> ExecutionOutcome.  This
    wires the service path (``FORGEFLOW_EXECUTOR=model``) to the model-driven
    evaluation engine; requires API credentials.  Wall-clock/turn budgets come
    from the strategy's bounds.
    """

    def __init__(
        self,
        *,
        repo_path: str | Path,
        policy: RepositoryPolicy,
        strategy: EvalStrategy | None = None,
    ) -> None:
        from forgeflow.evaluation.strategies_online import PlanGatesStrategy

        self._repo_path = Path(repo_path).resolve()
        self._policy = policy
        self._strategy = strategy or PlanGatesStrategy(name="plan_gates", policy=policy)

    @property
    def strategy(self) -> EvalStrategy:
        return self._strategy

    async def execute(self, task: StoredTask) -> ExecutionOutcome:
        result = await self._strategy.run(
            stored_to_case(task),
            repo_path=self._repo_path,
            strategy_name=self._strategy.name,
        )
        return outcome_from_eval(result)
