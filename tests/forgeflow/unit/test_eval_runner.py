"""Evaluation runner unit tests — aggregation, repeatability, versioned config."""

from __future__ import annotations

from pathlib import Path

import pytest

from forgeflow.evaluation.datasets import Dataset, EvalCase, EvalResult
from forgeflow.evaluation.experiment import new_experiment_config
from forgeflow.evaluation.feedback import ExperienceSample, FeedbackDataset
from forgeflow.evaluation.runner import EvalRunner
from forgeflow.evaluation.strategies import EvalStrategy


def _feedback_dataset() -> FeedbackDataset:
    sample = ExperienceSample(
        id="s1",
        task_id="billing-001",
        run_id="r1",
        source_type="turn",
        classification="success",
        content="fix duplicate charge: charge() must return the existing "
        "PaymentRecord when order_id already has a charge.",
        tags=("payment", "idempotency"),
    )
    return FeedbackDataset(id="seed", version="1.0", samples=(sample,))


class FakeStrategy:
    def __init__(self, name: str, status: str) -> None:
        self._name = name
        self._status = status
        self.contexts: dict[str, str] = {}

    @property
    def name(self) -> str:
        return self._name

    async def run(
        self,
        case: EvalCase,
        *,
        repo_path: Path,
        strategy_name: str,
        context: str = "",
    ) -> EvalResult:
        self.contexts[case.case_id] = context
        return EvalResult(
            case_id=case.case_id,
            strategy=strategy_name,
            status=self._status,
            tests_passed=self._status == "passed",
            duration_ms=10,
        )


def _dataset() -> Dataset:
    return Dataset(
        id="d",
        version="1.0",
        cases=(
            EvalCase(case_id="c1", repository="r", title="one"),
            EvalCase(case_id="c2", repository="r", title="two"),
        ),
    )


def _strategies() -> dict[str, EvalStrategy]:
    return {
        "passing": FakeStrategy("passing", "passed"),
        "failing": FakeStrategy("failing", "failed"),
    }


@pytest.mark.asyncio
async def test_runner_aggregates_by_strategy(tmp_path: Path) -> None:
    config = new_experiment_config(
        name="exp", strategies=["passing", "failing"], dataset_id="d", dataset_version="1.0"
    )
    result = await EvalRunner(_strategies()).run(dataset=_dataset(), config=config, repo_root=tmp_path)
    assert len(result.results) == 4  # 2 strategies × 2 cases
    assert result.metrics_by_strategy["passing"]["completion_rate"] == 1.0
    assert result.metrics_by_strategy["failing"]["completion_rate"] == 0.0
    assert len(result.failures) == 2
    assert all(failure.strategy == "failing" for failure in result.failures)


@pytest.mark.asyncio
async def test_runner_is_repeatable(tmp_path: Path) -> None:
    config = new_experiment_config(
        name="exp", strategies=["passing"], dataset_id="d", dataset_version="1.0"
    )
    first = await EvalRunner(_strategies()).run(dataset=_dataset(), config=config, repo_root=tmp_path)
    second = await EvalRunner(_strategies()).run(dataset=_dataset(), config=config, repo_root=tmp_path)
    assert first.metrics_by_strategy == second.metrics_by_strategy
    assert [r.status for r in first.results] == [r.status for r in second.results]


def test_experiment_config_is_versioned() -> None:
    config = new_experiment_config(
        name="exp", strategies=["plan_gates"], dataset_id="billing-smoke", dataset_version="2026-08-05"
    )
    assert config.dataset_version == "2026-08-05"
    assert config.config_version == "1.0"
    assert config.strategy_names == ("plan_gates",)


@pytest.mark.asyncio
async def test_runner_injects_retrieval_context(tmp_path: Path) -> None:
    config = new_experiment_config(
        name="exp", strategies=["passing"], dataset_id="d", dataset_version="1.0"
    )
    strategy = FakeStrategy("passing", "passed")
    runner = EvalRunner({"passing": strategy}, feedback_dataset=_feedback_dataset())
    dataset = Dataset(
        id="d",
        version="1.0",
        cases=(
            EvalCase(
                case_id="billing-001",
                repository="r",
                title="修复重复扣款",
                description="客户端超时重试时可能产生第二笔扣款",
                tags=("payment", "idempotency"),
            ),
        ),
    )
    await runner.run(dataset=dataset, config=config, repo_root=tmp_path)
    assert "# 历史经验参考" in strategy.contexts["billing-001"]


@pytest.mark.asyncio
async def test_runner_passes_empty_context_without_dataset(tmp_path: Path) -> None:
    config = new_experiment_config(
        name="exp", strategies=["passing"], dataset_id="d", dataset_version="1.0"
    )
    strategy = FakeStrategy("passing", "passed")
    runner = EvalRunner({"passing": strategy})
    await runner.run(dataset=_dataset(), config=config, repo_root=tmp_path)
    assert strategy.contexts == {"c1": "", "c2": ""}
