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
        "| 策略 | 完成率 | 通过/总数 | 测试通过率 | 平均Token | 平均成本 | 平均耗时 |",
        "|---|---|---|---|---|---|---|",
    ]
    for strategy, metrics in result.metrics_by_strategy.items():
        lines.append(
            f"| {strategy} | {metrics['completion_rate']:.2%} | "
            f"{metrics['pass_count']}/{metrics['case_count']} | "
            f"{metrics['test_pass_rate']:.2%} | {metrics['avg_tokens']} | "
            f"${metrics['avg_cost_usd']:.6f} | {metrics['avg_duration_ms']}ms |"
        )
    lines.append("")
    lines.append("## 失败案例")
    failures = result.failures
    if not failures:
        lines.append("（无）")
    else:
        for failure in failures:
            detail = failure.error or "failed"
            lines.append(f"- `{failure.case_id}` [{failure.strategy}] **{failure.status}** — {detail}")
    return "\n".join(lines)
