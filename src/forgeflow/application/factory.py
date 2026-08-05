"""Service factory — builds the default TaskService from environment config."""

from __future__ import annotations

import os

from forgeflow.application.event_bus import EventBus
from forgeflow.application.executors import LocalTaskExecutor, TaskExecutor
from forgeflow.application.task_orchestrator import TaskOrchestrator
from forgeflow.application.task_service import PolicyProvider, TaskService
from forgeflow.domain.approval import ApprovalManager
from forgeflow.domain.policy import RepositoryPolicy
from forgeflow.infrastructure.database import (
    create_database_engine,
    create_session_factory,
    init_db,
)
from forgeflow.infrastructure.store import TaskStore


def create_service_from_env() -> TaskService:
    """Build the default service. Requires FORGEFLOW_REPO_PATH (local repo to execute against)."""
    repo_path = os.environ.get("FORGEFLOW_REPO_PATH")
    if not repo_path:
        raise RuntimeError("FORGEFLOW_REPO_PATH is required to build the local task executor")
    repository = os.environ.get("FORGEFLOW_REPOSITORY", "default")

    engine = create_database_engine()
    init_db(engine)
    session = create_session_factory(engine)()
    store = TaskStore(session)
    event_bus = EventBus()
    approvals = ApprovalManager()

    policy = RepositoryPolicy(repository=repository)
    executor: TaskExecutor
    executor_mode = os.environ.get("FORGEFLOW_EXECUTOR", "local")
    if executor_mode == "model":
        from forgeflow.application.executors import ModelDrivenTaskExecutor

        executor = ModelDrivenTaskExecutor(repo_path=repo_path, policy=policy)
    else:
        executor = LocalTaskExecutor(repo_path=repo_path, policy=policy)
    orchestrator = TaskOrchestrator(
        store=store, event_bus=event_bus, executor=executor, approvals=approvals
    )
    return TaskService(
        store=store,
        event_bus=event_bus,
        orchestrator=orchestrator,
        approvals=approvals,
        policy_provider=PolicyProvider({repository: policy}),
    )
