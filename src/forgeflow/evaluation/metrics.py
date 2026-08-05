"""Deterministic evaluation metrics (spec §7.6)."""

from __future__ import annotations

from typing import Any

from forgeflow.evaluation.datasets import EvalResult


def _metadata_int(result: EvalResult, key: str, default: int) -> int:
    value = result.metadata.get(key, default)
    return value if isinstance(value, int) else default


def compute_metrics(results: list[EvalResult]) -> dict[str, Any]:
    """Aggregate deterministic metrics over a set of EvalResults."""
    total = len(results)
    passed = sum(1 for result in results if result.status == "passed")
    errors = sum(1 for result in results if result.status == "error")
    tests_passed = sum(1 for result in results if result.tests_passed)
    forbidden = sum(1 for result in results if result.forbidden_paths_touched)
    tokens = sum(result.token_usage for result in results)
    cost = sum(result.cost for result in results)
    duration = sum(result.duration_ms for result in results)
    tool_failures = sum(_metadata_int(result, "tool_failures", 0) for result in results)

    def ratio(numerator: int) -> float:
        return round(numerator / total, 4) if total else 0.0

    return {
        "case_count": total,
        "pass_count": passed,
        "error_count": errors,
        "completion_rate": ratio(passed),
        "test_pass_rate": ratio(tests_passed),
        "forbidden_path_touches": forbidden,
        "total_tokens": tokens,
        "avg_tokens": round(tokens / total, 1) if total else 0,
        "total_cost_usd": round(cost, 6),
        "avg_cost_usd": round(cost / total, 6) if total else 0.0,
        "total_duration_ms": duration,
        "avg_duration_ms": round(duration / total, 1) if total else 0,
        "tool_failures_total": tool_failures,
    }
