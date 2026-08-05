"""Service factory — builds the default TaskService from environment config."""

from __future__ import annotations

import os

from forgeflow.api.auth import ApiKeyAuthenticator
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
from forgeflow.infrastructure.github import GitHubPrClient
from forgeflow.infrastructure.store import TaskStore
from forgeflow.orchestration.delivery import DeliveryService


def github_client_from_env() -> GitHubPrClient | None:
    """Build a GitHubPrClient from ``GITHUB_TOKEN`` (or ``GH_TOKEN``), else None (B1)."""
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        return None
    return GitHubPrClient(token=token)


def api_key_auth_from_env() -> ApiKeyAuthenticator | None:
    """Build an ApiKeyAuthenticator from ``FORGEFLOW_API_KEYS`` / ``FORGEFLOW_API_KEY`` (B4).

    ``FORGEFLOW_API_KEYS`` is ``key:subject`` pairs separated by commas; a bare
    ``FORGEFLOW_API_KEY`` maps to ``FORGEFLOW_API_SUBJECT`` (default ``api-user``).
    """
    raw_keys = os.environ.get("FORGEFLOW_API_KEYS")
    if raw_keys:
        keys: dict[str, str] = {}
        for pair in raw_keys.split(","):
            if not pair.strip():
                continue
            if ":" in pair:
                key, subject = pair.split(":", 1)
                keys[key.strip()] = subject.strip()
            else:
                keys[pair.strip()] = "api-user"
        return ApiKeyAuthenticator(keys)
    single = os.environ.get("FORGEFLOW_API_KEY")
    if single:
        return ApiKeyAuthenticator(
            {single: os.environ.get("FORGEFLOW_API_SUBJECT", "api-user")}
        )
    return None


def delivery_service_from_env() -> DeliveryService:
    """Build the delivery service from env: test repos + optional GitHub client."""
    test_repositories = [
        item.strip()
        for item in os.environ.get("FORGEFLOW_TEST_REPOSITORIES", "").split(",")
        if item.strip()
    ]
    return DeliveryService(test_repositories=test_repositories, github=github_client_from_env())


def _repositories_from_env() -> list[str]:
    """Read the configured repositories (``FORGEFLOW_REPOSITORIES`` or singular)."""
    raw = os.environ.get("FORGEFLOW_REPOSITORIES") or os.environ.get("FORGEFLOW_REPOSITORY")
    if not raw:
        return ["default"]
    return [item.strip() for item in raw.split(",") if item.strip()]


def create_service_from_env() -> TaskService:
    """Build the default service. Requires FORGEFLOW_REPO_PATH (local repo to execute against)."""
    repo_path = os.environ.get("FORGEFLOW_REPO_PATH")
    if not repo_path:
        raise RuntimeError("FORGEFLOW_REPO_PATH is required to build the local task executor")

    engine = create_database_engine()
    init_db(engine)
    session = create_session_factory(engine)()
    store = TaskStore(session)
    event_bus = EventBus()
    approvals = ApprovalManager()

    required_commands = [
        command.strip()
        for command in os.environ.get("FORGEFLOW_REQUIRED_COMMANDS", "").split(",")
        if command.strip()
    ]
    # B3 多仓库：每个仓库一份策略，executor/风险评分按任务仓库解析。
    policies = {
        repository: RepositoryPolicy(repository=repository, required_commands=required_commands)
        for repository in _repositories_from_env()
    }
    provider = PolicyProvider(policies)
    executor: TaskExecutor
    executor_mode = os.environ.get("FORGEFLOW_EXECUTOR", "local")
    default_policy = next(iter(policies.values()))
    if executor_mode == "model":
        from forgeflow.application.executors import ModelDrivenTaskExecutor

        executor = ModelDrivenTaskExecutor(
            repo_path=repo_path, policy=default_policy, policy_resolver=provider.get
        )
    else:
        executor = LocalTaskExecutor(
            repo_path=repo_path, policy=default_policy, policy_resolver=provider.get
        )
    orchestrator = TaskOrchestrator(
        store=store,
        event_bus=event_bus,
        executor=executor,
        approvals=approvals,
        delivery=delivery_service_from_env(),
    )
    return TaskService(
        store=store,
        event_bus=event_bus,
        orchestrator=orchestrator,
        approvals=approvals,
        policy_provider=provider,
    )
