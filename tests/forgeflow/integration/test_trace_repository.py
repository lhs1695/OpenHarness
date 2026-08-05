"""Trace repository integration — a task run produces a persistent, exportable trace."""

from __future__ import annotations

import asyncio
import json

import pytest

from forgeflow.application.task_service import CreateTaskInput
from forgeflow.orchestration.state_machine import TaskState


async def _wait_completed(service, task_id: str) -> None:
    for _ in range(40):
        if service.get_task(task_id).status == TaskState.COMPLETED.value:
            return
        await asyncio.sleep(0.01)
    raise AssertionError("task did not complete")


@pytest.mark.asyncio
async def test_task_produces_exportable_trace(make_service) -> None:
    service = make_service()
    task = service.create_task(CreateTaskInput(repository="r", title="t"))
    service.start_task(task.id)
    await _wait_completed(service, task.id)

    timeline = service.trace_timeline(task.id)
    assert timeline
    assert any(item["event_type"] == "task_state_changed" for item in timeline)
    # timeline is ordered by occurrence
    timestamps = [item["timestamp"] for item in timeline]
    assert timestamps == sorted(timestamps)

    jsonl = service.export_trace_jsonl(task.id)
    lines = [line for line in jsonl.splitlines() if line.strip()]
    assert lines
    first = json.loads(lines[0])
    assert "event_id" in first
    assert "span_id" in first
    assert "parent_event_id" in first


@pytest.mark.asyncio
async def test_trace_restored_after_restart(make_service) -> None:
    service1 = make_service(db_name="shared.db")
    task = service1.create_task(CreateTaskInput(repository="r", title="t"))
    service1.start_task(task.id)
    await _wait_completed(service1, task.id)

    service2 = make_service(db_name="shared.db")
    jsonl = service2.export_trace_jsonl(task.id)
    assert "task_state_changed" in jsonl
