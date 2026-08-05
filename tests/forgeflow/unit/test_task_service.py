"""Task service unit tests — lifecycle, idempotent commands."""

from __future__ import annotations

import asyncio

import pytest

from forgeflow.application.executors import ExecutionOutcome
from forgeflow.application.task_service import CreateTaskInput
from forgeflow.orchestration.state_machine import TaskState


async def _wait_for(service, task_id: str, status: TaskState, tries: int = 40) -> None:
    for _ in range(tries):
        if service.get_task(task_id).status == status.value:
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"task {task_id} did not reach {status.value}")


class _OutcomeExecutor:
    def __init__(self, outcome: ExecutionOutcome) -> None:
        self._outcome = outcome

    async def execute(self, task):
        return self._outcome


class _BlockingExecutor:
    def __init__(self) -> None:
        self.started = asyncio.Event()

    async def execute(self, task):
        self.started.set()
        await asyncio.Event().wait()
        return ExecutionOutcome(status="completed")


class _RecordingExecutor:
    def __init__(self, outcome: ExecutionOutcome | None = None) -> None:
        self.calls = 0
        self._outcome = outcome or ExecutionOutcome(status="completed")

    async def execute(self, task):
        self.calls += 1
        return self._outcome


def test_create_task_persists(make_service) -> None:
    service = make_service()
    task = service.create_task(
        CreateTaskInput(repository="billing-service", title="fix dup", task_type="bugfix")
    )
    assert task.status == TaskState.DRAFT.value
    assert service.get_task(task.id).repository == "billing-service"
    assert len(service.list_tasks()) == 1


@pytest.mark.asyncio
async def test_start_task_runs_to_completed(make_service) -> None:
    service = make_service()
    task = service.create_task(CreateTaskInput(repository="r", title="t"))
    service.start_task(task.id)
    await _wait_for(service, task.id, TaskState.COMPLETED)


@pytest.mark.asyncio
async def test_start_task_idempotent_with_command_id(make_service) -> None:
    service = make_service()
    task = service.create_task(CreateTaskInput(repository="r", title="t"))
    service.start_task(task.id, command_id="cmd-start-1")
    await _wait_for(service, task.id, TaskState.COMPLETED)
    service.start_task(task.id, command_id="cmd-start-1")  # repeated delivery → no-op
    assert service.get_task(task.id).status == TaskState.COMPLETED.value


@pytest.mark.asyncio
async def test_failed_executor_lands_on_failed(make_service) -> None:
    service = make_service(
        executor=_OutcomeExecutor(ExecutionOutcome(status="failed", error="boom"))
    )
    task = service.create_task(CreateTaskInput(repository="r", title="t"))
    service.start_task(task.id)
    await _wait_for(service, task.id, TaskState.FAILED)


@pytest.mark.asyncio
async def test_cancel_while_running_lands_on_cancelled(make_service) -> None:
    blocking = _BlockingExecutor()
    service = make_service(executor=blocking)
    task = service.create_task(CreateTaskInput(repository="r", title="t"))
    service.start_task(task.id)
    await blocking.started.wait()
    service.cancel_task(task.id)
    await _wait_for(service, task.id, TaskState.CANCELLED)


@pytest.mark.asyncio
async def test_pause_while_running(make_service) -> None:
    blocking = _BlockingExecutor()
    service = make_service(executor=blocking)
    task = service.create_task(CreateTaskInput(repository="r", title="t"))
    service.start_task(task.id)
    await blocking.started.wait()
    service.pause_task(task.id)
    assert service.get_task(task.id).status == TaskState.PAUSED.value


def test_cancel_from_draft_is_noop(make_service) -> None:
    service = make_service()
    task = service.create_task(CreateTaskInput(repository="r", title="t"))
    service.cancel_task(task.id)
    assert service.get_task(task.id).status == TaskState.DRAFT.value


@pytest.mark.asyncio
async def test_severe_risk_task_is_blocked_from_execution(make_service) -> None:
    """P0-1: SEVERE risk tasks produce a plan only — the executor never runs."""
    executor = _RecordingExecutor()
    service = make_service(executor=executor)
    task = service.create_task(
        CreateTaskInput(repository="r", title="severe", initial_risk_score=90)
    )
    service.start_task(task.id)
    await _wait_for(service, task.id, TaskState.FAILED)
    assert executor.calls == 0


@pytest.mark.asyncio
async def test_medium_risk_waits_for_final_approval_and_does_not_reexecute(
    make_service,
) -> None:
    """P1-5: final approval waits at WAITING_FINAL_APPROVAL; resume skips execution."""
    executor = _RecordingExecutor()
    service = make_service(executor=executor)
    task = service.create_task(
        CreateTaskInput(repository="r", title="medium", initial_risk_score=40)
    )
    service.start_task(task.id)
    await _wait_for(service, task.id, TaskState.WAITING_FINAL_APPROVAL)
    assert executor.calls == 1

    approvals = service.approvals_for(task.id)
    assert [a.approval_type for a in approvals] == ["final"]
    service.approve(approvals[0].id, approved=True, resolved_by="owner", reason="ok")
    await _wait_for(service, task.id, TaskState.COMPLETED)
    assert executor.calls == 1  # final-approval resume must not re-run execution


@pytest.mark.asyncio
async def test_approvals_survive_service_restart(make_service) -> None:
    """P0-2: a restarted service (fresh manager, same DB) continues the approval flow."""
    executor = _RecordingExecutor()
    first = make_service(executor=executor, db_name="shared.db")
    task = first.create_task(
        CreateTaskInput(repository="r", title="high", initial_risk_score=70)
    )
    first.start_task(task.id)
    await _wait_for(first, task.id, TaskState.WAITING_PLAN_APPROVAL)
    plan_approval = first.approvals_for(task.id)[0]
    first.approve(plan_approval.id, approved=True, resolved_by="owner", reason="ok")
    await _wait_for(first, task.id, TaskState.WAITING_FINAL_APPROVAL)
    assert executor.calls == 1

    # Second "process": a fresh service over the same DB hydrates persisted approvals.
    restarted = make_service(executor=executor, db_name="shared.db")
    approvals = restarted.approvals_for(task.id)
    assert len(approvals) == 2  # approved PLAN + pending FINAL restored
    pending = [a for a in approvals if a.status == "pending"]
    assert len(pending) == 1
    restarted.approve(pending[0].id, approved=True, resolved_by="owner", reason="ok")
    await _wait_for(restarted, task.id, TaskState.COMPLETED)
    assert executor.calls == 1  # restart must not re-run execution


def test_risk_inputs_derived_from_task_not_zero(make_service) -> None:
    """P0-3: creation-time risk comes from task data, not an empty RiskInputs."""
    service = make_service()
    default_task = service.create_task(
        CreateTaskInput(repository="r", title="fix", task_type="bugfix")
    )
    # missing-tests hint (+15) → non-zero
    assert default_task.initial_risk_score >= 15


def test_high_risk_tags_bump_risk_into_approval_path(make_service) -> None:
    service = make_service()
    task = service.create_task(
        CreateTaskInput(
            repository="r",
            title="add migration",
            task_type="bugfix",
            risk_tags=["migration", "db"],
            acceptance_criteria=["migration file added"],
        )
    )
    # migration (+25) → risk >= 25 (+ missing tests) → at least MEDIUM
    assert task.initial_risk_score >= 25
    from forgeflow.domain.risk import risk_level

    assert risk_level(task.initial_risk_score) in (
        "MEDIUM",
        "HIGH",
        "SEVERE",
    )
