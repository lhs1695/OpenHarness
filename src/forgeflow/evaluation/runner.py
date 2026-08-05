"""Evaluation runner — runs a strategy matrix over a dataset (spec §13 M8).

Also provides the CLI entry point: ``python -m forgeflow.evaluation.runner``.
"""

from __future__ import annotations

import argparse
import asyncio
import tempfile
from pathlib import Path

from forgeflow.evaluation.datasets import Dataset, get_dataset
from forgeflow.evaluation.experiment import (
    ExperimentConfig,
    ExperimentResult,
    new_experiment_config,
    new_experiment_result,
)
from forgeflow.evaluation.fixtures import materialize_dataset_repos
from forgeflow.evaluation.metrics import compute_metrics
from forgeflow.evaluation.reports import render_report
from forgeflow.evaluation.strategies import EvalStrategy, default_strategies


class EvalRunner:
    """Run every configured strategy over every dataset case, repeatably."""

    def __init__(self, strategies: dict[str, EvalStrategy]) -> None:
        self._strategies = strategies

    async def run(
        self,
        *,
        dataset: Dataset,
        config: ExperimentConfig,
        repo_root: Path,
    ) -> ExperimentResult:
        result = new_experiment_result(config)
        for strategy_name in config.strategy_names:
            strategy = self._strategies[strategy_name]
            for case in dataset.cases:
                repo_path = repo_root / case.repository
                case_result = await strategy.run(
                    case, repo_path=repo_path, strategy_name=strategy_name
                )
                result.results.append(case_result)
        result.metrics_by_strategy = {
            strategy_name: compute_metrics(
                [item for item in result.results if item.strategy == strategy_name]
            )
            for strategy_name in config.strategy_names
        }
        return result


async def _run_experiment(name: str, dataset_id: str, strategies: list[str], repo_root: Path) -> None:
    dataset = get_dataset(dataset_id)
    config = new_experiment_config(
        name=name,
        strategies=strategies,
        dataset_id=dataset.id,
        dataset_version=dataset.version,
    )
    repositories = sorted({case.repository for case in dataset.cases})
    with tempfile.TemporaryDirectory(prefix="forgeflow-eval-") as tmp:
        work_root = materialize_dataset_repos(repo_root, Path(tmp) / "repos", repositories)
        result = await EvalRunner(default_strategies()).run(
            dataset=dataset, config=config, repo_root=work_root
        )
    print(render_report(result))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a ForgeFlow evaluation experiment")
    parser.add_argument("--name", default="default-run")
    parser.add_argument("--dataset", default="default")
    parser.add_argument(
        "--strategies",
        default="plan_gates",
        help="comma-separated strategy names (raw, plan_gates, plan_gates_reviewer)",
    )
    parser.add_argument(
        "--repo-root",
        default="tests/forgeflow/fixtures/repositories",
        help="path to fixture repositories",
    )
    args = parser.parse_args()
    strategies = [item.strip() for item in args.strategies.split(",") if item.strip()]
    asyncio.run(_run_experiment(args.name, args.dataset, strategies, Path(args.repo_root)))


if __name__ == "__main__":
    main()
