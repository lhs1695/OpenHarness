"""Experiment config and result (versioned, per spec §8.9/§13 M8)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from forgeflow.evaluation.datasets import EvalResult


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class ExperimentConfig:
    name: str
    strategy_names: tuple[str, ...]
    dataset_id: str
    dataset_version: str
    config_version: str = "1.0"


@dataclass
class ExperimentResult:
    """Mutable during a run; serialized once complete."""

    experiment_id: str
    config: ExperimentConfig
    results: list[EvalResult] = field(default_factory=list)
    metrics_by_strategy: dict[str, dict[str, Any]] = field(default_factory=dict)
    created_at: str = ""

    @property
    def failures(self) -> list[EvalResult]:
        return [result for result in self.results if result.status != "passed"]

    @property
    def failures_by_strategy(self) -> dict[str, list[EvalResult]]:
        grouped: dict[str, list[EvalResult]] = {}
        for result in self.failures:
            grouped.setdefault(result.strategy, []).append(result)
        return grouped


def new_experiment_config(
    *,
    name: str,
    strategies: list[str],
    dataset_id: str,
    dataset_version: str,
    config_version: str = "1.0",
) -> ExperimentConfig:
    return ExperimentConfig(
        name=name,
        strategy_names=tuple(strategies),
        dataset_id=dataset_id,
        dataset_version=dataset_version,
        config_version=config_version,
    )


def new_experiment_result(config: ExperimentConfig) -> ExperimentResult:
    return ExperimentResult(
        experiment_id=f"exp_{uuid4().hex[:8]}",
        config=config,
        created_at=_now_iso(),
    )
