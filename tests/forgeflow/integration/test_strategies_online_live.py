"""Online strategies against the real model on a single billing case.

Each test drives a real OpenHarness agent inside an isolated worktree of the
billing-service fixture to repair the idempotency bug, then verifies with the
repo tests / quality gates / reviewer.  Marked ``online`` (skipped by default);
run with ``pytest -m online`` and API credentials configured.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from forgeflow.domain.policy import RepositoryPolicy
from forgeflow.evaluation.datasets import EvalCase
from forgeflow.evaluation.fixtures import materialize_git_repo
from forgeflow.evaluation.registry import FeedbackRegistry
from forgeflow.evaluation.strategies_online import (
    PlanGatesReviewerStrategy,
    PlanGatesStrategy,
    RawAgentStrategy,
)

pytestmark = pytest.mark.online

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "repositories"
POLICY = RepositoryPolicy(repository="billing-service")


def _has_api_credentials() -> bool:
    from openharness.config.settings import load_settings

    try:
        load_settings().resolve_auth()
        return True
    except Exception:  # noqa: BLE001 — capability probe: any failure means no creds
        return False


def _billing_case() -> EvalCase:
    return EvalCase(
        case_id="billing-001",
        repository="billing-service",
        title="修复重复扣款",
        description="客户端超时重试时可能产生第二笔扣款",
        acceptance_rules=("相同幂等键只产生一笔支付记录",),
        tags=("payment", "idempotency"),
    )


def _maybe_skip() -> None:
    if not _has_api_credentials():
        pytest.skip("no API credentials available")


@pytest.mark.asyncio
async def test_raw_agent_online(tmp_path: Path) -> None:
    _maybe_skip()
    repo = materialize_git_repo(FIXTURES / "billing-service", tmp_path)
    strategy = RawAgentStrategy(name="raw", policy=POLICY)
    result = await strategy.run(_billing_case(), repo_path=repo, strategy_name="raw")
    assert result.status in ("passed", "failed")
    assert result.failure_class in ("pass", "agent_failed")
    assert result.token_usage > 0
    assert result.duration_ms >= 0


@pytest.mark.asyncio
async def test_plan_gates_online(tmp_path: Path) -> None:
    _maybe_skip()
    repo = materialize_git_repo(FIXTURES / "billing-service", tmp_path)
    strategy = PlanGatesStrategy(name="plan_gates", policy=POLICY)
    result = await strategy.run(_billing_case(), repo_path=repo, strategy_name="plan_gates")
    assert result.status in ("passed", "failed")
    assert result.failure_class in ("pass", "agent_failed")
    assert result.token_usage > 0


@pytest.mark.asyncio
async def test_plan_gates_reviewer_online(tmp_path: Path) -> None:
    _maybe_skip()
    repo = materialize_git_repo(FIXTURES / "billing-service", tmp_path)
    strategy = PlanGatesReviewerStrategy(name="plan_gates_reviewer", policy=POLICY)
    result = await strategy.run(
        _billing_case(), repo_path=repo, strategy_name="plan_gates_reviewer"
    )
    assert result.status in ("passed", "failed")
    assert result.failure_class in ("pass", "agent_failed")
    assert result.token_usage > 0


@pytest.mark.asyncio
async def test_raw_agent_online_registers_feedback(tmp_path: Path) -> None:
    """A1 冒烟：真实运行后 FeedbackRegistry 应拿到带 provenance 的样本。"""
    _maybe_skip()
    repo = materialize_git_repo(FIXTURES / "billing-service", tmp_path)
    registry = FeedbackRegistry()
    strategy = RawAgentStrategy(
        name="raw",
        policy=POLICY,
        feedback_registry=registry,
        dataset_version="2026-08-05",
    )
    await strategy.run(_billing_case(), repo_path=repo, strategy_name="raw")
    datasets = registry.list()
    assert datasets, "expected a feedback dataset after a real online run"
    dataset = datasets[0]
    assert dataset.samples
    sample = dataset.samples[0]
    assert sample.provenance["case_id"] == "billing-001"
    assert sample.provenance["repository"] == "billing-service"
    assert sample.classification in ("success", "failure")
