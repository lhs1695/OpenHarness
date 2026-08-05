"""Evaluation metrics unit tests."""

from forgeflow.evaluation.datasets import EvalResult
from forgeflow.evaluation.metrics import compute_metrics


def test_metrics_empty() -> None:
    metrics = compute_metrics([])
    assert metrics["completion_rate"] == 0.0
    assert metrics["case_count"] == 0


def test_metrics_all_passed() -> None:
    results = [
        EvalResult(case_id="c1", strategy="s", status="passed", tests_passed=True, token_usage=100, cost=0.01, duration_ms=1000),
        EvalResult(case_id="c2", strategy="s", status="passed", tests_passed=True, token_usage=200, cost=0.02, duration_ms=2000),
    ]
    metrics = compute_metrics(results)
    assert metrics["case_count"] == 2
    assert metrics["pass_count"] == 2
    assert metrics["completion_rate"] == 1.0
    assert metrics["test_pass_rate"] == 1.0
    assert metrics["avg_tokens"] == 150
    assert metrics["total_cost_usd"] == 0.03


def test_metrics_mixed() -> None:
    results = [
        EvalResult(case_id="c1", strategy="s", status="passed", tests_passed=True),
        EvalResult(case_id="c2", strategy="s", status="failed", tests_passed=False, forbidden_paths_touched=True),
        EvalResult(case_id="c3", strategy="s", status="error", error="boom"),
    ]
    metrics = compute_metrics(results)
    assert metrics["completion_rate"] == round(1 / 3, 4)
    assert metrics["error_count"] == 1
    assert metrics["forbidden_path_touches"] == 1
