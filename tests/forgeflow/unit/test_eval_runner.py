"""Evaluation runner unit tests — aggregation, repeatability, versioned config."""

from __future__ import annotations

from pathlib import Path

import pytest

from forgeflow.evaluation.datasets import Dataset, EvalCase, EvalResult
from forgeflow.evaluation.experiment import new_experiment_config
from forgeflow.evaluation.runner import EvalRunner
from forgeflow.evaluation.strategies import EvalStrategy


class FakeStrategy:
    def __init__(self, name: str, status: str) -> None:
        self._name = name
        self._status = status

    @property
    def name(self) -> str:
        return self._name

    async def run(self, case: EvalCase, *, repo_path: Path, strategy_name: str) -> EvalResult:
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
