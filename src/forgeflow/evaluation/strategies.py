"""Evaluation strategies — injectable per-strategy task runners.

M8 ships a deterministic local strategy (worktree + required commands +
quality gates, no model calls).  The model-driven variants (raw agent, plan +
gates, plan + gates + reviewer) plug the same seam and are exercised in the
online/demo phase.
"""

from __future__ import annotations

import shlex
import sys
import time
from pathlib import Path
from typing import Protocol

from forgeflow.domain.policy import RepositoryPolicy
from forgeflow.evaluation.datasets import EvalCase, EvalResult
from forgeflow.execution.worktree import WorktreeExecutionBackend
from forgeflow.quality.reports import QualityGateRunner


class EvalStrategy(Protocol):
    @property
    def name(self) -> str: ...

    async def run(self, case: EvalCase, *, repo_path: Path, strategy_name: str) -> EvalResult: ...


def _resolved_test_command(command: str) -> str:
    """Resolve a bare ``pytest`` command to this interpreter's python -m pytest."""
    parts = shlex.split(command)
    if parts and parts[0] == "pytest":
        parts = [sys.executable, "-m", "pytest", *parts[1:]]
    return shlex.join(parts)


def _policy_for_case(base: RepositoryPolicy, case: EvalCase) -> RepositoryPolicy:
    return RepositoryPolicy(
        repository=case.repository,
        sensitive_paths=base.sensitive_paths,
        forbidden_paths=base.forbidden_paths,
        required_commands=[_resolved_test_command(case.test_command)],
        forbidden_commands=base.forbidden_commands,
        max_changed_files=base.max_changed_files,
        max_execution_minutes=base.max_execution_minutes,
        max_agent_steps=base.max_agent_steps,
        approval_rules=base.approval_rules,
    )


class PipelineStrategy:
    """Deterministic local strategy: isolated worktree + required commands + gates."""

    def __init__(self, *, name: str, policy: RepositoryPolicy) -> None:
        self._name = name
        self._policy = policy

    @property
    def name(self) -> str:
        return self._name

    async def run(self, case: EvalCase, *, repo_path: Path, strategy_name: str) -> EvalResult:
        started = time.monotonic()
        backend = WorktreeExecutionBackend(repo_path)
        try:
            workspace = Path(await backend.prepare(case.case_id, case.repository))
            runner = QualityGateRunner(backend, _policy_for_case(self._policy, case))
            report = await runner.evaluate(
                task_id=case.case_id,
                task_type=case.task_type,
                workspace=workspace,
            )
            duration_ms = int((time.monotonic() - started) * 1000)
            hard_failed = [gate.gate_name for gate in report.hard_failures]
            return EvalResult(
                case_id=case.case_id,
                strategy=strategy_name,
                status="passed" if report.passed else "failed",
                tests_passed="required_commands" not in hard_failed,
                hard_gates_passed=report.passed,
                forbidden_paths_touched="forbidden_paths" in hard_failed,
                duration_ms=duration_ms,
                error=None if report.passed else f"hard gates failed: {hard_failed}",
            )
        except Exception as exc:  # noqa: BLE001 — any strategy failure becomes an error result
            duration_ms = int((time.monotonic() - started) * 1000)
            return EvalResult(
                case_id=case.case_id,
                strategy=strategy_name,
                status="error",
                error=str(exc),
                duration_ms=duration_ms,
            )
        finally:
            await backend.cleanup()


_BASE_POLICY = RepositoryPolicy(
    repository="default",
    sensitive_paths=[],
    forbidden_paths=[],
    required_commands=[],
    forbidden_commands=[],
    max_changed_files=12,
    max_execution_minutes=45,
    max_agent_steps=40,
)


def default_strategies() -> dict[str, EvalStrategy]:
    """The initial strategy set (spec §13 M8): raw / plan_gates / plan_gates_reviewer."""
    strategies: dict[str, EvalStrategy] = {}
    for name in ("raw", "plan_gates", "plan_gates_reviewer"):
        strategies[name] = PipelineStrategy(name=name, policy=_BASE_POLICY)
    return strategies
