"""Feedback pipeline integration — samples from a real task's persisted trace."""

from __future__ import annotations

import asyncio

import pytest

from forgeflow.application.task_service import CreateTaskInput
from forgeflow.evaluation.feedback import TraceSampleBuilder
from forgeflow.evaluation.registry import FeedbackRegistry
from forgeflow.orchestration.state_machine import TaskState
from forgeflow.trace.repository import TraceRepository


async def _wait_completed(service, task_id: str) -> None:
    for _ in range(40):
        if service.get_task(task_id).status == TaskState.COMPLETED.value:
            return
        await asyncio.sleep(0.01)
    raise AssertionError("task did not complete")


@pytest.mark.asyncio
async def test_build_samples_from_real_trace(make_service) -> None:
    service = make_service()
    task = service.create_task(CreateTaskInput(repository="r", title="t"))
    service.start_task(task.id)
    await _wait_completed(service, task.id)

    events = TraceRepository(service._store).load_events(task.id)
    assert events

    dataset = TraceSampleBuilder().build(
        task_id=task.id,
        run_id=f"run_{task.id}",
        events=events,
        provenance={"dataset_version": "2026-08-05", "case_id": "demo", "repository": "r"},
    )
    assert dataset.samples
    assert all(sample.task_id == task.id for sample in dataset.samples)
    assert all(sample.provenance["case_id"] == "demo" for sample in dataset.samples)

    registry = FeedbackRegistry()
    registry.register(dataset)
    assert registry.get(dataset.id, dataset.version) is dataset
