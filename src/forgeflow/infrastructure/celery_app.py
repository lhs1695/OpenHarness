"""Celery integration for queue-based task execution (idempotent handler)."""

from __future__ import annotations

import os

from celery import Celery  # type: ignore[import-untyped]

from forgeflow.application.factory import create_service_from_env
from forgeflow.application.task_service import TaskService

app = Celery(
    "forgeflow",
    broker=os.environ.get("FORGEFLOW_CELERY_BROKER", "redis://localhost:6379/0"),
)
app.conf.task_serializer = "json"
app.conf.result_serializer = "json"

_service: TaskService | None = None


def _get_service() -> TaskService:
    global _service
    if _service is None:
        _service = create_service_from_env()
    return _service


def set_service(service: TaskService) -> None:
    """Inject a service instance (used by tests; avoids env-based construction)."""
    global _service
    _service = service


@app.task(name="forgeflow.execute_task")  # type: ignore[untyped-decorator]
def execute_task_message(task_id: str, command_id: str | None = None) -> None:
    """Queue a task start. Idempotent under broker re-delivery via command_id."""
    _get_service().start_task(task_id, command_id=command_id or f"start:{task_id}")
