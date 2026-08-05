"""Real PipelineStrategy against materialized git-repo fixtures (deterministic)."""

from __future__ import annotations

from pathlib import Path

import pytest

from forgeflow.domain.policy import RepositoryPolicy
from forgeflow.evaluation.datasets import EvalCase
from forgeflow.evaluation.fixtures import materialize_git_repo
from forgeflow.evaluation.strategies import PipelineStrategy

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "repositories"


@pytest.fixture
def git_repos(tmp_path) -> dict[str, Path]:
    return {
        "cart-service": materialize_git_repo(FIXTURES / "cart-service", tmp_path),
        "billing-service": materialize_git_repo(FIXTURES / "billing-service", tmp_path),
    }


@pytest.mark.asyncio
async def test_clean_repo_case_passes(git_repos) -> None:
    strategy = PipelineStrategy(
        name="plan_gates", policy=RepositoryPolicy(repository="cart-service")
    )
    case = EvalCase(
        case_id="cart-001", repository="cart-service", title="verify", task_type="verify"
    )
    result = await strategy.run(
        case, repo_path=git_repos["cart-service"], strategy_name="plan_gates"
    )
    assert result.status == "passed"
    assert result.failure_class == "pass"
    assert result.tests_passed
    assert result.hard_gates_passed


@pytest.mark.asyncio
async def test_buggy_repo_case_fails(git_repos) -> None:
    strategy = PipelineStrategy(
        name="plan_gates", policy=RepositoryPolicy(repository="billing-service")
    )
    case = EvalCase(
        case_id="billing-001", repository="billing-service", title="fix dup", task_type="bugfix"
    )
    result = await strategy.run(
        case, repo_path=git_repos["billing-service"], strategy_name="plan_gates"
    )
    assert result.status == "failed"
    assert result.failure_class == "baseline"  # repo tests fail; no fix applied yet
    assert not result.tests_passed
    assert result.error is not None


@pytest.mark.asyncio
async def test_strategy_is_repeatable(git_repos) -> None:
    strategy = PipelineStrategy(
        name="plan_gates", policy=RepositoryPolicy(repository="cart-service")
    )
    case = EvalCase(
        case_id="cart-001", repository="cart-service", title="verify", task_type="verify"
    )
    first = await strategy.run(
        case, repo_path=git_repos["cart-service"], strategy_name="plan_gates"
    )
    second = await strategy.run(
        case, repo_path=git_repos["cart-service"], strategy_name="plan_gates"
    )
    assert first.status == second.status == "passed"
