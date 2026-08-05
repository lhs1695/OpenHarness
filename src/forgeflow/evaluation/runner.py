"""Evaluation runner — runs a strategy matrix over a dataset (spec §13 M8).

Also provides the CLI entry point: ``python -m forgeflow.evaluation.runner``.
"""

from __future__ import annotations

import argparse
import asyncio
import tempfile
from pathlib import Path

from forgeflow.evaluation.datasets import Dataset, EvalCase, get_dataset
from forgeflow.evaluation.experiment import (
    ExperimentConfig,
    ExperimentResult,
    new_experiment_config,
    new_experiment_result,
)
from forgeflow.evaluation.feedback import FeedbackDataset, dataset_from_json
from forgeflow.evaluation.fixtures import materialize_dataset_repos
from forgeflow.evaluation.metrics import compute_metrics
from forgeflow.evaluation.reports import render_report
from forgeflow.evaluation.retrieval import build_retrieval_context
from forgeflow.evaluation.strategies import EvalStrategy, default_strategies


def _retrieval_query(case: EvalCase) -> str:
    # Case descriptions are Chinese; retrieval tokenizes latin terms only, so the
    # latin tags are included to give the keyword-overlap scorer something to match.
    return f"{case.title} {case.description} {' '.join(case.tags)}"


class EvalRunner:
    """Run every configured strategy over every dataset case, repeatably."""

    def __init__(
        self,
        strategies: dict[str, EvalStrategy],
        feedback_dataset: FeedbackDataset | None = None,
    ) -> None:
        self._strategies = strategies
        self._feedback_dataset = feedback_dataset

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
                context = ""
                if self._feedback_dataset is not None:
                    context = build_retrieval_context(
                        _retrieval_query(case), self._feedback_dataset
                    )
                case_result = await strategy.run(
                    case,
                    repo_path=repo_path,
                    strategy_name=strategy_name,
                    context=context,
                )
                result.results.append(case_result)
        result.metrics_by_strategy = {
            strategy_name: compute_metrics(
                [item for item in result.results if item.strategy == strategy_name]
            )
            for strategy_name in config.strategy_names
        }
        return result


def _build_strategies(online: bool) -> dict[str, EvalStrategy]:
    if online:
        from forgeflow.evaluation.strategies_online import online_strategies

        return online_strategies()
    return default_strategies()


async def _run_experiment(
    name: str,
    dataset_id: str,
    strategies: list[str],
    repo_root: Path,
    output_path: Path | None,
    online: bool,
    feedback_dataset_path: Path | None,
) -> None:
    dataset = get_dataset(dataset_id)
    feedback_dataset = None
    if feedback_dataset_path is not None:
        feedback_dataset = dataset_from_json(feedback_dataset_path.read_text(encoding="utf-8"))
    config = new_experiment_config(
        name=name,
        strategies=strategies,
        dataset_id=dataset.id,
        dataset_version=dataset.version,
    )
    repositories = sorted({case.repository for case in dataset.cases})
    with tempfile.TemporaryDirectory(prefix="forgeflow-eval-") as tmp:
        work_root = materialize_dataset_repos(repo_root, Path(tmp) / "repos", repositories)
        result = await EvalRunner(_build_strategies(online), feedback_dataset).run(
            dataset=dataset, config=config, repo_root=work_root
        )
    report = render_report(result)
    if output_path is not None:
        output_path.write_text(report, encoding="utf-8")
    else:
        print(report)


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
    parser.add_argument(
        "--output",
        default=None,
        help="write the markdown report to this file (UTF-8) instead of stdout",
    )
    parser.add_argument(
        "--online",
        action="store_true",
        help="use the model-driven online strategies (requires API credentials)",
    )
    parser.add_argument(
        "--feedback-dataset",
        default=None,
        help="path to a FeedbackDataset JSON; injects retrieved historical "
        "experience into the strategies (before/after comparison)",
    )
    args = parser.parse_args()
    strategies = [item.strip() for item in args.strategies.split(",") if item.strip()]
    output = Path(args.output) if args.output else None
    feedback_dataset_path = Path(args.feedback_dataset) if args.feedback_dataset else None
    asyncio.run(
        _run_experiment(
            args.name,
            args.dataset,
            strategies,
            Path(args.repo_root),
            output,
            args.online,
            feedback_dataset_path,
        )
    )


if __name__ == "__main__":
    main()
