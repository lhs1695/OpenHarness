"""B3 tests — multi-repository support: per-repo policies resolve at the right seams."""

from __future__ import annotations

import asyncio
import shlex
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from forgeflow.application.executors import (
    LocalTaskExecutor,
    ModelDrivenTaskExecutor,
)
from forgeflow.application.factory import _repositories_from_env
from forgeflow.application.task_service import PolicyProvider
from forgeflow.domain.policy import RepositoryPolicy
from forgeflow.evaluation.datasets import EvalCase, EvalResult
from forgeflow.evaluation.fixtures import materialize_git_repo
from forgeflow.infrastructure.store import StoredTask

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "repositories"


def _stored(repository: str, task_id: str = "task-1") -> StoredTask:
    return StoredTask(
        id=task_id,
        repository=repository,
        title="修复重复扣款",
        description="客户端超时重试时可能产生第二笔扣款",
        task_type="bugfix",
        priority="P2",
        acceptance_criteria=["相同幂等键只产生一笔支付记录"],
        risk_tags=["payment", "idempotency"],
        status="ready",
        initial_risk_score=20,
        final_risk_score=None,
        requested_by="tester",
        created_at=datetime(2026, 8, 5, tzinfo=UTC),
        updated_at=datetime(2026, 8, 5, tzinfo=UTC),
    )


def test_policy_provider_multi_registration() -> None:
    provider = PolicyProvider(
        {
            "billing-service": RepositoryPolicy(repository="billing-service", max_agent_steps=5),
            "cart-service": RepositoryPolicy(repository="cart-service", max_changed_files=3),
        }
    )
    assert provider.for_repository("billing-service").max_agent_steps == 5
    assert provider.for_repository("cart-service").max_changed_files == 3
    assert set(provider.repositories()) == {"billing-service", "cart-service"}
    # unknown repository falls back to a blank policy
    assert provider.for_repository("unknown").repository == "unknown"


def test_repositories_from_env_splits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FORGEFLOW_REPOSITORIES", "billing-service, cart-service")
    assert _repositories_from_env() == ["billing-service", "cart-service"]
    monkeypatch.delenv("FORGEFLOW_REPOSITORIES", raising=False)
    monkeypatch.setenv("FORGEFLOW_REPOSITORY", "single")
    assert _repositories_from_env() == ["single"]
    monkeypatch.delenv("FORGEFLOW_REPOSITORY", raising=False)
    assert _repositories_from_env() == ["default"]


class _FakeEvalStrategy:
    @property
    def name(self) -> str:
        return "fake"

    async def run(
        self,
        case: EvalCase,
        *,
        repo_path: Path,
        strategy_name: str,
        context: str = "",
    ) -> EvalResult:
        return EvalResult(case_id=case.case_id, strategy=strategy_name, status="passed")


def test_model_executor_resolves_strategy_policy_per_repo() -> None:
    resolver = PolicyProvider(
        {
            "a": RepositoryPolicy(repository="a"),
            "b": RepositoryPolicy(repository="b"),
        }
    ).for_repository
    executor = ModelDrivenTaskExecutor(
        repo_path=Path("."),
        policy=RepositoryPolicy(repository="default"),
        strategy=_FakeEvalStrategy(),
        policy_resolver=resolver,
    )
    from forgeflow.evaluation.strategies_online import PlanGatesStrategy

    strategy_a = executor._strategy_for(resolver("a"))
    strategy_b = executor._strategy_for(resolver("b"))
    assert isinstance(strategy_a, PlanGatesStrategy)
    assert strategy_a._policy.repository == "a"
    assert strategy_b._policy.repository == "b"


def test_model_executor_uses_injected_strategy_without_resolver() -> None:
    injected = _FakeEvalStrategy()
    executor = ModelDrivenTaskExecutor(
        repo_path=Path("."), policy=RepositoryPolicy(repository="a"), strategy=injected
    )
    assert executor._strategy_for(RepositoryPolicy(repository="b")) is injected


def test_local_executor_applies_per_repo_required_commands(tmp_path: Path) -> None:
    """Each repo's policy drives its own quality gates (fake backend semantics)."""
    repo = materialize_git_repo(FIXTURES / "billing-service", tmp_path)
    py = shlex.quote(sys.executable)
    resolver = PolicyProvider(
        {
            "passing-repo": RepositoryPolicy(
                repository="passing-repo", required_commands=[f"{py} -c \"print(1)\""]
            ),
            "failing-repo": RepositoryPolicy(
                repository="failing-repo", required_commands=[f"{py} -c \"raise SystemExit(1)\""]
            ),
        }
    ).for_repository
    executor = LocalTaskExecutor(
        repo_path=repo, policy=RepositoryPolicy(repository="default"), policy_resolver=resolver
    )

    async def _run(repository: str, task_id: str) -> str:
        outcome = await executor.execute(_stored(repository, task_id))
        return outcome.status

    assert asyncio.run(_run("passing-repo", "pass-1")) == "completed"
    assert asyncio.run(_run("failing-repo", "fail-1")) == "failed"
