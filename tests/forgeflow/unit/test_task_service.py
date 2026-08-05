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
