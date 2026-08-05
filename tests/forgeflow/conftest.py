"""Shared fixtures for ForgeFlow service tests."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from forgeflow.application.event_bus import EventBus
from forgeflow.application.executors import ExecutionOutcome
from forgeflow.application.task_orchestrator import TaskOrchestrator
from forgeflow.application.task_service import (
    PolicyProvider,
    TaskService,
    reload_approvals_from_store,
)
from forgeflow.domain.approval import ApprovalManager
from forgeflow.infrastructure.database import (
    create_database_engine,
    create_session_factory,
    init_db,
)
from forgeflow.infrastructure.store import TaskStore


class FakeTaskExecutor:
    """Completes immediately with the given (or a successful) outcome."""

    def __init__(self, outcome: ExecutionOutcome | None = None) -> None:
        self._outcome = outcome or ExecutionOutcome(status="completed")

    async def execute(self, task):
        return self._outcome


@pytest.fixture
def make_service(tmp_path) -> Callable[..., TaskService]:
    """Return a factory building a TaskService over a SQLite DB in tmp_path."""

    def _make(
        executor: object | None = None,
        db_name: str = "test.db",
    ) -> TaskService:
        engine = create_database_engine(f"sqlite:///{(tmp_path / db_name).as_posix()}")
        init_db(engine)
        session = create_session_factory(engine)()
        store = TaskStore(session)
        event_bus = EventBus()
        approvals = ApprovalManager()
        reload_approvals_from_store(approvals, store)
        orchestrator = TaskOrchestrator(
            store=store,
            event_bus=event_bus,
            executor=executor if executor is not None else FakeTaskExecutor(),
            approvals=approvals,
        )
        return TaskService(
            store=store,
            event_bus=event_bus,
            orchestrator=orchestrator,
            approvals=approvals,
            policy_provider=PolicyProvider(),
        )

    return _make
