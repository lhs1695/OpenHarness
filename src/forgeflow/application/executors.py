"""Task executors — the pluggable engine behind the orchestrator.

M6 ships a local executor that runs a task's required commands in an isolated
worktree and evaluates the deterministic quality gates (no model calls).  The
plan/review model-driven stages are wired in later milestones; the seam is the
``TaskExecutor`` protocol so tests inject a fake.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, cast

from forgeflow.domain.policy import RepositoryPolicy
from forgeflow.evaluation.datasets import EvalCase, EvalResult
from forgeflow.evaluation.strategies import EvalStrategy
from forgeflow.execution.base import ExecutionResult
from forgeflow.execution.worktree import WorktreeExecutionBackend
from forgeflow.infrastructure.store import StoredTask
from forgeflow.orchestration.budgets import Budget, BudgetTracker
from forgeflow.orchestration.delivery import Patch, make_patch
from forgeflow.quality.reports import QualityGateRunner


@dataclass(frozen=True)
class ExecutionOutcome:
    status: str
    error: str | None = None
    gate_summary: dict[str, object] = field(default_factory=dict)
    command_results: dict[str, ExecutionResult] = field(default_factory=dict)
    patch: Patch | None = None


class TaskExecutor(Protocol):
    async def execute(self, task: StoredTask) -> ExecutionOutcome: ...


async def _git_diff_workspace(workspace: Path) -> str:
    proc = await asyncio.create_subprocess_exec(
        "git",
        "diff",
        "HEAD",
        cwd=str(workspace),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
    )
    stdout, _ = await proc.communicate()
    return stdout.decode(errors="replace")


def _changed_files_from_diff(diff: str) -> list[str]:
    files: list[str] = []
    for line in diff.splitlines():
        if line.startswith("diff --git "):
            parts = line.split(" b/", 1)
            if len(parts) == 2:
                files.append(parts[1].strip())
    return files


def _patch_from_diff(task: StoredTask, diff: str) -> Patch | None:
    if not diff.strip():
        return None
    return make_patch(
        repository=task.repository,
        diff=diff,
        changed_files=_changed_files_from_diff(diff),
    )


async def _patch_from_workspace(
    task: StoredTask, workspace: Path, changed_files: list[str]
) -> Patch | None:
    diff = await _git_diff_workspace(workspace)
    return _patch_from_diff(task, diff) if changed_files or diff.strip() else None


def patch_from_eval(task: StoredTask, result: EvalResult) -> Patch | None:
    """Build a delivery Patch from the strategy's captured diff (B1 wiring)."""
    diff = result.metadata.get("diff")
    if not isinstance(diff, str) or not diff.strip():
        return None
    return _patch_from_diff(task, diff)


class LocalTaskExecutor:
    """Run required commands in a worktree and evaluate quality gates."""

    def __init__(
        self,
        *,
        repo_path: str | Path,
        policy: RepositoryPolicy,
        policy_resolver: Callable[[str], RepositoryPolicy] | None = None,
    ) -> None:
        self._repo_path = Path(repo_path).resolve()
        self._policy = policy
        self._policy_resolver = policy_resolver or (lambda _: policy)

    async def execute(self, task: StoredTask) -> ExecutionOutcome:
        policy = self._policy_resolver(task.repository)
        backend = WorktreeExecutionBackend(self._repo_path)
        workspace = Path(await backend.prepare(task.id, task.repository))
        try:
            runner = QualityGateRunner(backend, policy)
            report = await runner.evaluate(
                task_id=task.id,
                task_type=task.task_type,
                workspace=workspace,
            )
            command_results = dict(report.command_results)
            patch = await _patch_from_workspace(task, workspace, report.changed_files)
            if report.passed:
                return ExecutionOutcome(
                    status="completed",
                    gate_summary=report.summarize(),
                    command_results=command_results,
                    patch=patch,
                )
            return ExecutionOutcome(
                status="failed",
                gate_summary=report.summarize(),
                error=f"quality gates failed: {report.summarize()['hard_failures']}",
                command_results=command_results,
                patch=patch,
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


def command_results_from_eval(result: EvalResult) -> dict[str, ExecutionResult]:
    """Surface the strategy's aggregated test/gate outcome as command results (B5).

    The online strategy runs quality gates/tests internally and only reports the
    aggregate in ``EvalResult``; mapping that outcome onto an ``ExecutionResult``
    lets the orchestrator's ``_record_commands`` write them into the trace.
    """
    if result.status == "passed":
        return {
            "gates": ExecutionResult(
                command=["quality", "gates"],
                returncode=0,
                stdout="all quality gates passed",
                stderr="",
                duration_ms=result.duration_ms,
            )
        }
    if result.error:
        return {
            "gates": ExecutionResult(
                command=["quality", "gates"],
                returncode=1,
                stdout="",
                stderr=result.error,
                duration_ms=result.duration_ms,
            )
        }
    return {}


def _env_int(name: str) -> int | None:
    value = os.environ.get(name)
    if value is None or not value.strip():
        return None
    return int(value)


def _env_float(name: str) -> float | None:
    value = os.environ.get(name)
    if value is None or not value.strip():
        return None
    return float(value)


def budget_from_policy_and_env(policy: RepositoryPolicy) -> Budget:
    """Derive a task budget from the repository policy with env overrides (B2).

    Policy provides agent-step and execution-time bounds; env knobs
    (``FORGEFLOW_BUDGET_MAX_*``) override or add token / tool-call / model-call
    limits.  Unset dimensions stay unlimited.
    """
    max_steps = _env_int("FORGEFLOW_BUDGET_MAX_STEPS")
    if max_steps is None:
        max_steps = policy.max_agent_steps
    max_seconds = _env_float("FORGEFLOW_BUDGET_MAX_SECONDS")
    if max_seconds is None and policy.max_execution_minutes is not None:
        max_seconds = float(policy.max_execution_minutes * 60)
    return Budget(
        max_agent_steps=max_steps,
        max_model_calls=_env_int("FORGEFLOW_BUDGET_MAX_MODEL_CALLS"),
        max_tool_calls=_env_int("FORGEFLOW_BUDGET_MAX_TOOL_CALLS"),
        max_tokens=_env_int("FORGEFLOW_BUDGET_MAX_TOKENS"),
        max_execution_seconds=max_seconds,
    )


class ModelDrivenTaskExecutor:
    """Execute a task with a real OpenHarness agent in an isolated worktree.

    Reuses the online plan_gates strategy (adapter plan -> agent repair ->
    quality gates) and adapts StoredTask -> EvalCase -> ExecutionOutcome.  This
    wires the service path (``FORGEFLOW_EXECUTOR=model``) to the model-driven
    evaluation engine; requires API credentials.  The task budget comes from
    ``budget_from_policy_and_env`` (or an explicit ``budget``); over-budget
    runs surface as ``budget_exceeded`` (B2 预算治理).
    """

    def __init__(
        self,
        *,
        repo_path: str | Path,
        policy: RepositoryPolicy,
        strategy: EvalStrategy | None = None,
        budget: Budget | None = None,
        policy_resolver: Callable[[str], RepositoryPolicy] | None = None,
    ) -> None:
        from forgeflow.evaluation.strategies_online import PlanGatesStrategy

        self._repo_path = Path(repo_path).resolve()
        self._policy = policy
        self._policy_resolver = policy_resolver or (lambda _: policy)
        self._uses_policy_resolver = policy_resolver is not None
        self._strategy = strategy or PlanGatesStrategy(name="plan_gates", policy=policy)
        self._explicit_budget = budget is not None
        self._budget = budget if budget is not None else budget_from_policy_and_env(policy)

    @property
    def strategy(self) -> EvalStrategy:
        return self._strategy

    @property
    def budget(self) -> Budget:
        return self._budget

    def _strategy_for(self, policy: RepositoryPolicy) -> EvalStrategy:
        """Per-repository strategy when a resolver is configured (B3); else the injected one."""
        if not self._uses_policy_resolver:
            return self._strategy
        from forgeflow.evaluation.strategies_online import PlanGatesStrategy

        return PlanGatesStrategy(name=self._strategy.name, policy=policy)

    async def execute(self, task: StoredTask) -> ExecutionOutcome:
        policy = self._policy_resolver(task.repository)
        strategy = self._strategy_for(policy)
        budget = self._budget if self._explicit_budget else budget_from_policy_and_env(policy)
        tracker = BudgetTracker(budget)
        result = await strategy.run(
            stored_to_case(task),
            repo_path=self._repo_path,
            strategy_name=strategy.name,
        )
        tracker.record_model_call(result.token_usage)
        tool_calls = int(cast(int, result.metadata.get("tool_calls", 0) or 0))
        for _ in range(max(tool_calls, 0)):
            tracker.record_agent_step()
            tracker.record_tool_call()
        tracker.set_elapsed(result.duration_ms / 1000.0)
        check = tracker.check()
        if not check.ok:
            return ExecutionOutcome(
                status="budget_exceeded",
                error=f"budget exceeded: {', '.join(check.exceeded)}",
                gate_summary={
                    "status": result.status,
                    "budget_exceeded": check.exceeded,
                    "token_usage": result.token_usage,
                    "duration_ms": result.duration_ms,
                },
            )
        outcome = outcome_from_eval(result)
        command_results = command_results_from_eval(result)
        patch = patch_from_eval(task, result)
        if command_results or patch is not None:
            outcome = ExecutionOutcome(
                status=outcome.status,
                error=outcome.error,
                gate_summary=outcome.gate_summary,
                command_results={**outcome.command_results, **command_results},
                patch=patch,
            )
        return outcome
