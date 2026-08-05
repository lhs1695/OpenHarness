"""Celery handler idempotency — repeated delivery does not double-execute.

Runs the handler in eager mode (in-process, no broker needed).
"""

from __future__ import annotations

import asyncio

import pytest

from forgeflow.application.task_service import CreateTaskInput
from forgeflow.infrastructure import celery_app
from forgeflow.infrastructure.celery_app import execute_task_message
from forgeflow.orchestration.state_machine import TaskState


@pytest.mark.asyncio
async def test_execute_task_message_idempotent(make_service) -> None:
    service = make_service()
    celery_app.set_service(service)
    celery_app.app.conf.task_always_eager = True
    task = service.create_task(CreateTaskInput(repository="r", title="t"))

    try:
        execute_task_message.apply(args=(task.id, "start:1"))
        execute_task_message.apply(args=(task.id, "start:1"))  # redelivery → no-op
        await asyncio.sleep(0.2)
    finally:
        celery_app.app.conf.task_always_eager = False
        celery_app.set_service(None)

    assert service.get_task(task.id).status == TaskState.COMPLETED.value


@pytest.mark.asyncio
async def test_distinct_command_ids_both_start(make_service) -> None:
    """Different command ids are not deduped — but a completed task stays terminal."""
    service = make_service()
    celery_app.set_service(service)
    celery_app.app.conf.task_always_eager = True
    task = service.create_task(CreateTaskInput(repository="r", title="t"))

    try:
        execute_task_message.apply(args=(task.id, "start:1"))
        await asyncio.sleep(0.2)
        execute_task_message.apply(args=(task.id, "start:2"))
        await asyncio.sleep(0.1)
    finally:
        celery_app.app.conf.task_always_eager = False
        celery_app.set_service(None)

    assert service.get_task(task.id).status == TaskState.COMPLETED.value
