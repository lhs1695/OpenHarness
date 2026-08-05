"""Persistence — service restart preserves tasks and trace events."""

from __future__ import annotations

import asyncio

import pytest

from forgeflow.application.task_service import CreateTaskInput
from forgeflow.orchestration.state_machine import TaskState


async def _wait_completed(service, task_id: str) -> None:
    for _ in range(40):
        if service.get_task(task_id).status == TaskState.COMPLETED.value:
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"task {task_id} did not complete")


@pytest.mark.asyncio
async def test_restart_preserves_task_and_trace(make_service) -> None:
    service1 = make_service(db_name="shared.db")
    task = service1.create_task(CreateTaskInput(repository="billing-service", title="fix dup"))
    service1.start_task(task.id)
    await _wait_completed(service1, task.id)

    # "Restart": a new service instance over the same database file.
    service2 = make_service(db_name="shared.db")
    restored = service2.get_task(task.id)
    assert restored.status == TaskState.COMPLETED.value
    assert restored.repository == "billing-service"
    assert restored.title == "fix dup"

    events = service2.list_events(task.id)
    assert any(event["event_type"] == "task_created" for event in events)
    assert any(event["event_type"] == "task_state_changed" for event in events)


def test_create_and_list_after_restart(make_service) -> None:
    service1 = make_service(db_name="shared.db")
    service1.create_task(CreateTaskInput(repository="r", title="one"))
    service1.create_task(CreateTaskInput(repository="r", title="two"))

    service2 = make_service(db_name="shared.db")
    titles = {task.title for task in service2.list_tasks()}
    assert titles == {"one", "two"}
