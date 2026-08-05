"""Experiment report rendering — aggregate metrics plus failure cases (spec §13 M8)."""

from __future__ import annotations

from forgeflow.evaluation.experiment import ExperimentResult


def render_report(result: ExperimentResult) -> str:
    """Render a markdown report. Always lists failure cases, not just averages."""
    lines = [
        f"# 评测报告 — {result.config.name}",
        f"- 实验 ID：`{result.experiment_id}`",
        f"- 数据集：`{result.config.dataset_id}` v{result.config.dataset_version}",
        f"- 策略：{', '.join(result.config.strategy_names)}",
        f"- 配置版本：{result.config.config_version}",
        f"- 创建时间：{result.created_at}",
        "",
        "## 汇总指标（按策略）",
        "| 策略 | 完成率 | 通过/总数 | 基线失败 | 策略失败 | 平均Token | 平均成本 | 平均耗时 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for strategy, metrics in result.metrics_by_strategy.items():
        lines.append(
            f"| {strategy} | {metrics['completion_rate']:.2%} | "
            f"{metrics['pass_count']}/{metrics['case_count']} | "
            f"{metrics['baseline_count']} | {metrics['policy_count']} | "
            f"{metrics['avg_tokens']} | ${metrics['avg_cost_usd']:.6f} | "
            f"{metrics['avg_duration_ms']}ms |"
        )
    lines.append("")
    lines.append("## 失败案例")
    failures = result.failures
    if not failures:
        lines.append("（无）")
    else:
        for failure in failures:
            detail = failure.error or "failed"
            label = _FAILURE_LABELS.get(failure.failure_class, failure.failure_class)
            lines.append(
                f"- `{failure.case_id}` [{failure.strategy}] **{label}** — {detail}"
            )
    return "\n".join(lines)


_FAILURE_LABELS = {
    "baseline": "基线失败（测试未通过，未施加修复）",
    "policy": "策略门禁失败",
    "error": "意外错误",
    "pass": "通过",
}
