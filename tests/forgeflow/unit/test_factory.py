"""Service factory tests — required-command gate wiring from environment."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from forgeflow.application.factory import create_service_from_env
from forgeflow.application.task_service import CreateTaskInput
from forgeflow.evaluation.fixtures import materialize_git_repo
from forgeflow.orchestration.state_machine import TaskState

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "repositories"


async def _wait_for(service, task_id: str, status: TaskState, tries: int = 600) -> None:
    for _ in range(tries):
        if service.get_task(task_id).status == status.value:
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"task {task_id} did not reach {status.value}")


@pytest.mark.asyncio
async def test_service_runs_required_command_and_fails_on_buggy_repo(monkeypatch, tmp_path: Path) -> None:
    """With FORGEFLOW_REQUIRED_COMMANDS set, the service actually runs the repo
    tests: the billing fixture's failing pytest makes the gate fail the task."""
    repo = materialize_git_repo(FIXTURES / "billing-service", tmp_path)
    monkeypatch.setenv("FORGEFLOW_REPO_PATH", str(repo))
    monkeypatch.setenv("FORGEFLOW_REPOSITORY", "billing-service")
    monkeypatch.setenv("FORGEFLOW_REQUIRED_COMMANDS", "python -m pytest -q")
    monkeypatch.setenv("FORGEFLOW_DATABASE_URL", f"sqlite:///{(tmp_path / 't.db').as_posix()}")

    service = create_service_from_env()
    task = service.create_task(
        CreateTaskInput(
            repository="billing-service",
            title="verify gates",
            description="service path should run repo tests",
            task_type="verify",
        )
    )
    service.start_task(task.id)
    await _wait_for(service, task.id, TaskState.FAILED)
