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
    budget_from_policy_and_env,
    command_results_from_eval,
    outcome_from_eval,
    stored_to_case,
)
from forgeflow.application.task_service import CreateTaskInput
from forgeflow.domain.policy import RepositoryPolicy
from forgeflow.evaluation.datasets import EvalCase, EvalResult
from forgeflow.infrastructure.store import StoredTask
from forgeflow.orchestration.budgets import Budget
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


@pytest.mark.asyncio
async def test_model_executor_returns_budget_exceeded_when_tool_calls_over() -> None:
    strategy = FakeEvalStrategy(
        EvalResult(
            case_id="t",
            strategy="fake",
            status="passed",
            tests_passed=True,
            token_usage=50,
            metadata={"tool_calls": 3},
        )
    )
    executor = ModelDrivenTaskExecutor(
        repo_path=Path("."),
        policy=POLICY,
        strategy=strategy,
        budget=Budget(max_tool_calls=1),
    )
    outcome = await executor.execute(_stored())
    assert outcome.status == "budget_exceeded"
    assert "tool_calls" in outcome.gate_summary["budget_exceeded"]
    assert outcome.error == "budget exceeded: tool_calls"


@pytest.mark.asyncio
async def test_model_executor_returns_budget_exceeded_when_tokens_over() -> None:
    strategy = FakeEvalStrategy(
        EvalResult(case_id="t", strategy="fake", status="passed", token_usage=200)
    )
    executor = ModelDrivenTaskExecutor(
        repo_path=Path("."),
        policy=POLICY,
        strategy=strategy,
        budget=Budget(max_tokens=100),
    )
    outcome = await executor.execute(_stored())
    assert outcome.status == "budget_exceeded"
    assert "tokens" in outcome.gate_summary["budget_exceeded"]


@pytest.mark.asyncio
async def test_model_executor_within_budget_maps_normal_outcome() -> None:
    strategy = FakeEvalStrategy(
        EvalResult(
            case_id="t",
            strategy="fake",
            status="passed",
            tests_passed=True,
            token_usage=50,
            duration_ms=100,
            metadata={"tool_calls": 3},
        )
    )
    executor = ModelDrivenTaskExecutor(
        repo_path=Path("."),
        policy=POLICY,
        strategy=strategy,
        budget=Budget(max_tool_calls=10, max_tokens=1000, max_execution_seconds=60.0),
    )
    outcome = await executor.execute(_stored())
    assert outcome.status == "completed"


def test_command_results_from_eval_passed() -> None:
    results = command_results_from_eval(
        EvalResult(case_id="t", strategy="fake", status="passed", tests_passed=True)
    )
    assert results["gates"].returncode == 0
    assert results["gates"].command == ["quality", "gates"]


def test_command_results_from_eval_failed_carries_error() -> None:
    results = command_results_from_eval(
        EvalResult(
            case_id="t",
            strategy="fake",
            status="failed",
            failure_class="agent_failed",
            error="hard gates failed: ['required_commands']",
        )
    )
    assert results["gates"].returncode == 1
    assert "required_commands" in results["gates"].stderr


@pytest.mark.asyncio
async def test_model_executor_attaches_command_results() -> None:
    strategy = FakeEvalStrategy(
        EvalResult(case_id="t", strategy="fake", status="passed", tests_passed=True)
    )
    executor = ModelDrivenTaskExecutor(repo_path=Path("."), policy=POLICY, strategy=strategy)
    outcome = await executor.execute(_stored())
    assert outcome.status == "completed"
    assert "gates" in outcome.command_results
    assert outcome.command_results["gates"].returncode == 0


@pytest.mark.asyncio
async def test_model_executor_command_results_land_in_trace(make_service) -> None:
    """B5: the orchestrator records the model executor's commands into /timeline."""
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
    timeline = service.trace_timeline(task.id)
    command_events = [item for item in timeline if item["event_type"] == "command_finished"]
    assert command_events, "expected command_finished events in the trace"
    assert "quality gates" in str(command_events[0]["summary"])


def test_budget_derived_from_policy_limits() -> None:
    policy = RepositoryPolicy(
        repository="billing-service", max_agent_steps=7, max_execution_minutes=5
    )
    budget = budget_from_policy_and_env(policy)
    assert budget.max_agent_steps == 7
    assert budget.max_execution_seconds == 300.0


@pytest.mark.asyncio
async def test_policy_budget_enforced_when_exceeded() -> None:
    strategy = FakeEvalStrategy(
        EvalResult(
            case_id="t",
            strategy="fake",
            status="passed",
            metadata={"tool_calls": 4},
        )
    )
    executor = ModelDrivenTaskExecutor(
        repo_path=Path("."),
        policy=RepositoryPolicy(repository="billing-service", max_agent_steps=2),
        strategy=strategy,
    )
    outcome = await executor.execute(_stored())
    assert outcome.status == "budget_exceeded"
    assert "agent_steps" in outcome.gate_summary["budget_exceeded"]


@pytest.mark.asyncio
async def test_budget_exceeded_through_service_lands_state(make_service) -> None:
    """An over-budget executor run persists the BUDGET_EXCEEDED terminal state."""
    strategy = FakeEvalStrategy(
        EvalResult(
            case_id="t",
            strategy="fake",
            status="passed",
            token_usage=500,
            metadata={"tool_calls": 3},
        )
    )
    executor = ModelDrivenTaskExecutor(
        repo_path=Path("."),
        policy=POLICY,
        strategy=strategy,
        budget=Budget(max_tokens=100),
    )
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
    await _wait_for(service, task.id, TaskState.BUDGET_EXCEEDED)


def _diff_result() -> EvalResult:
    return EvalResult(
        case_id="t",
        strategy="fake",
        status="passed",
        tests_passed=True,
        metadata={"diff": "diff --git a/payment.py b/payment.py\n+charge once\n"},
    )


@pytest.mark.asyncio
async def test_model_executor_builds_delivery_patch_from_diff() -> None:
    """B1: the executor maps the strategy's captured diff into an outcome Patch."""
    strategy = FakeEvalStrategy(_diff_result())
    executor = ModelDrivenTaskExecutor(repo_path=Path("."), policy=POLICY, strategy=strategy)
    outcome = await executor.execute(_stored())
    assert outcome.patch is not None
    assert outcome.patch.repository == "billing-service"
    assert outcome.patch.changed_files == ["payment.py"]
    assert "payment.py" in outcome.patch.diff


@pytest.mark.asyncio
async def test_model_executor_without_diff_has_no_patch() -> None:
    strategy = FakeEvalStrategy(
        EvalResult(case_id="t", strategy="fake", status="passed", tests_passed=True)
    )
    executor = ModelDrivenTaskExecutor(repo_path=Path("."), policy=POLICY, strategy=strategy)
    outcome = await executor.execute(_stored())
    assert outcome.patch is None


class _FakeDelivery:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def create_draft_pr(self, *, repository: str, patch, base: str = "main", head: str = ""):
        self.calls.append((repository, head))
        from forgeflow.orchestration.delivery import DraftPr

        return DraftPr(
            repository=repository,
            title=patch.changed_files[0] if patch.changed_files else "change",
            body="b",
            changed_files=patch.changed_files,
            url=f"https://github.com/x/repo/pull/{len(self.calls)}",
            number=str(len(self.calls)),
        )


def _service_with_delivery(delivery: _FakeDelivery, executor: object):
    from forgeflow.application.event_bus import EventBus
    from forgeflow.application.task_orchestrator import TaskOrchestrator
    from forgeflow.application.task_service import PolicyProvider, TaskService
    from forgeflow.domain.approval import ApprovalManager
    from forgeflow.infrastructure.database import (
        create_database_engine,
        create_session_factory,
        init_db,
    )
    from forgeflow.infrastructure.store import TaskStore

    engine = create_database_engine("sqlite:///:memory:")
    init_db(engine)
    session = create_session_factory(engine)()
    store = TaskStore(session)
    approvals = ApprovalManager()
    orchestrator = TaskOrchestrator(
        store=store,
        event_bus=EventBus(),
        executor=executor,
        approvals=approvals,
        delivery=delivery,
    )
    return TaskService(
        store=store,
        event_bus=EventBus(),
        orchestrator=orchestrator,
        approvals=approvals,
        policy_provider=PolicyProvider(),
    )


@pytest.mark.asyncio
async def test_delivery_invoked_after_completed_with_patch() -> None:
    """B1: a completed task with a real diff triggers create_draft_pr."""
    delivery = _FakeDelivery()
    executor = ModelDrivenTaskExecutor(
        repo_path=Path("."), policy=POLICY, strategy=FakeEvalStrategy(_diff_result())
    )
    service = _service_with_delivery(delivery, executor)
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
    assert delivery.calls, "create_draft_pr should have been called on completion"
    assert delivery.calls[0][0] == "billing-service"
    assert delivery.calls[0][1].startswith("forgeflow/")


@pytest.mark.asyncio
async def test_delivery_skipped_without_patch() -> None:
    delivery = _FakeDelivery()
    executor = ModelDrivenTaskExecutor(
        repo_path=Path("."),
        policy=POLICY,
        strategy=FakeEvalStrategy(EvalResult(case_id="t", strategy="fake", status="passed")),
    )
    service = _service_with_delivery(delivery, executor)
    task = service.create_task(
        CreateTaskInput(
            repository="billing-service",
            title="t",
            description="d",
            task_type="bugfix",
            acceptance_criteria=["c"],
            risk_tags=["r"],
        )
    )
    service.start_task(task.id)
    await _wait_for(service, task.id, TaskState.COMPLETED)
    assert delivery.calls == []


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
    assert outcome.status in ("completed", "failed", "budget_exceeded")
    assert outcome.gate_summary.get("failure_class") in ("pass", "agent_failed", None)
