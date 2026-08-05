"""ModelDrivenTaskExecutor tests — StoredTask/EvalCase/ExecutionOutcome adapters.

The executor delegates the actual repair to an online strategy; here a fake
strategy is injected so the adaptation logic is exercised without any model
calls.  A real-model smoke test carries the ``online`` marker.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

import pytest

from forgeflow.application.executors import (
    ModelDrivenTaskExecutor,
    outcome_from_eval,
    stored_to_case,
)
from forgeflow.application.task_service import CreateTaskInput
from forgeflow.domain.policy import RepositoryPolicy
from forgeflow.evaluation.datasets import EvalCase, EvalResult
from forgeflow.infrastructure.store import StoredTask
from forgeflow.orchestration.state_machine import TaskState

POLICY = RepositoryPolicy(repository="billing-service")


def _stored(status: str = "ready") -> StoredTask:
    return StoredTask(
        id="task-1",
        repository="billing-service",
        title="修复重复扣款",
        description="客户端超时重试时可能产生第二笔扣款",
        task_type="bugfix",
        priority="P2",
        acceptance_criteria=["相同幂等键只产生一笔支付记录"],
        risk_tags=["payment", "idempotency"],
        status=status,
        initial_risk_score=20,
        final_risk_score=None,
        requested_by="tester",
        created_at=datetime(2026, 8, 5, tzinfo=UTC),
        updated_at=datetime(2026, 8, 5, tzinfo=UTC),
    )


def test_stored_to_case_maps_fields() -> None:
    case = stored_to_case(_stored())
    assert case.case_id == "task-1"
    assert case.repository == "billing-service"
    assert case.task_type == "bugfix"
    assert case.acceptance_rules == ("相同幂等键只产生一笔支付记录",)
    assert case.tags == ("payment", "idempotency")


def test_outcome_from_eval_passed() -> None:
    result = EvalResult(
        case_id="t", strategy="plan_gates", status="passed", tests_passed=True
    )
    outcome = outcome_from_eval(result)
    assert outcome.status == "completed"
    assert outcome.gate_summary["failure_class"] == "pass"


def test_outcome_from_eval_failed() -> None:
    result = EvalResult(
        case_id="t",
        strategy="plan_gates",
        status="failed",
        failure_class="agent_failed",
        error="hard gates failed",
    )
    outcome = outcome_from_eval(result)
    assert outcome.status == "failed"
    assert outcome.error == "hard gates failed"


class FakeEvalStrategy:
    def __init__(self, result: EvalResult) -> None:
        self._result = result
        self.last_context = ""

    @property
    def name(self) -> str:
        return "fake"

    async def run(
        self,
        case: EvalCase,
        *,
        repo_path: Path,
        strategy_name: str,
        context: str = "",
    ) -> EvalResult:
        self.last_context = context
        return self._result


@pytest.mark.asyncio
async def test_model_executor_delegates_and_maps_success() -> None:
    strategy = FakeEvalStrategy(
        EvalResult(case_id="t", strategy="fake", status="passed", tests_passed=True)
    )
    executor = ModelDrivenTaskExecutor(repo_path=Path("."), policy=POLICY, strategy=strategy)
    outcome = await executor.execute(_stored())
    assert outcome.status == "completed"
    assert outcome.gate_summary["failure_class"] == "pass"
    assert strategy.last_context == ""


@pytest.mark.asyncio
async def test_model_executor_reports_failure() -> None:
    strategy = FakeEvalStrategy(
        EvalResult(
            case_id="t",
            strategy="fake",
            status="failed",
            failure_class="agent_failed",
            error="gates failed",
        )
    )
    executor = ModelDrivenTaskExecutor(repo_path=Path("."), policy=POLICY, strategy=strategy)
    outcome = await executor.execute(_stored())
    assert outcome.status == "failed"
    assert outcome.error == "gates failed"


async def _wait_for(service, task_id: str, status: TaskState, tries: int = 40) -> None:
    for _ in range(tries):
        if service.get_task(task_id).status == status.value:
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"task {task_id} did not reach {status.value}")


@pytest.mark.asyncio
async def test_model_executor_through_service_lands_completed(make_service) -> None:
    """Model executor wired through the orchestrator persists a terminal state."""
    strategy = FakeEvalStrategy(
        EvalResult(case_id="t", strategy="fake", status="passed", tests_passed=True)
    )
    executor = ModelDrivenTaskExecutor(repo_path=Path("."), policy=POLICY, strategy=strategy)
    service = make_service(executor=executor)
    task = service.create_task(
        CreateTaskInput(
            repository="billing-service",
            title="修复重复扣款",
            description="客户端超时重试时可能产生第二笔扣款",
            task_type="bugfix",
            acceptance_criteria=["相同幂等键只产生一笔支付记录"],
            risk_tags=["payment", "idempotency"],
        )
    )
    service.start_task(task.id)
    await _wait_for(service, task.id, TaskState.COMPLETED)


@pytest.mark.online
@pytest.mark.asyncio
async def test_model_executor_online(tmp_path: Path) -> None:
    """Real model through the service executor path (skipped by default)."""
    from openharness.config.settings import load_settings

    try:
        load_settings().resolve_auth()
    except Exception:  # noqa: BLE001 — capability probe: no creds -> skip
        pytest.skip("no API credentials available")

    from forgeflow.application.executors import ModelDrivenTaskExecutor
    from forgeflow.evaluation.fixtures import materialize_git_repo

    fixtures = Path(__file__).resolve().parents[1] / "fixtures" / "repositories"
    repo = materialize_git_repo(fixtures / "billing-service", tmp_path)
    executor = ModelDrivenTaskExecutor(repo_path=repo, policy=POLICY)
    outcome = await executor.execute(_stored())
    assert outcome.status in ("completed", "failed")
    assert outcome.gate_summary["failure_class"] in ("pass", "agent_failed")
