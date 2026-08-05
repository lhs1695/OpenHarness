"""Evaluation report rendering tests — failure labels and the agent_failed column."""

from __future__ import annotations

from forgeflow.evaluation.datasets import EvalResult
from forgeflow.evaluation.experiment import ExperimentResult, new_experiment_config
from forgeflow.evaluation.metrics import compute_metrics
from forgeflow.evaluation.reports import render_report


def _experiment() -> ExperimentResult:
    config = new_experiment_config(
        name="exp", strategies=["plan_gates"], dataset_id="default", dataset_version="2026-08-05"
    )
    results = [
        EvalResult(
            case_id="billing-001",
            strategy="plan_gates",
            status="failed",
            failure_class="agent_failed",
            error="test command exited 1",
        ),
        EvalResult(
            case_id="cart-001",
            strategy="plan_gates",
            status="passed",
            failure_class="pass",
            tests_passed=True,
        ),
    ]
    result = ExperimentResult(
        experiment_id="exp_abc12345",
        config=config,
        results=results,
        metrics_by_strategy={"plan_gates": compute_metrics(results)},
        created_at="2026-08-05T00:00:00+00:00",
    )
    return result


def test_render_report_lists_agent_failed_failure() -> None:
    report = render_report(_experiment())
    assert "Agent 未修复/被拒" in report
    assert "billing-001" in report
    assert "test command exited 1" in report


def test_render_report_includes_agent_failed_column() -> None:
    report = render_report(_experiment())
    assert "Agent 未修复" in report
    assert "50.00%" in report  # 1/2 pass
