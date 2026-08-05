# RESUME — ForgeFlow 简历描述

> 数字全部来自真实评测：`evals/reports/2026-08-05-default-plan_gates.md`（确定性本地基线）与
> `evals/reports/2026-08-05-online-default.md`（Agent 驱动在线，DeepSeek 真实调用），禁止编造（`PROJECT_SPEC.md` §16）。

## ForgeFlow｜研发任务交付与质量闭环平台

- 基于 OpenHarness 通用 Agent Runtime 深度二次开发面向研发团队的任务交付平台，设计任务分级、仓库策略、风险评分、执行预算、人工审批和质量门禁，实现从需求输入到 Patch / Draft PR 的完整业务闭环。
- 通过 OpenHarness Adapter 隔离业务层与上游实现，新增 Local Worktree / Docker 隔离执行、任务状态机、取消恢复和幂等控制，支持长任务中断后继续执行。
- 构建统一 Trace 事件模型，记录模型与工具调用、命令执行、文件变更、测试、审批、Token、成本和延迟，并实现轨迹脱敏、失败分类和任务回放。
- 建立包含 **8 个**可复现任务（6 个 bugfix + 2 个 verify）的回归评测集，对比原始 Agent、计划与质量门禁、独立 Reviewer 三种在线策略：确定性本地基线完成率 **25%**，Agent 驱动在线评测将任务成功率提升至 **75%**（计划+门禁方案；无约束 raw 策略达 **100%**），计划+门禁方案的平均工具失败从 0.88 降至 0.50 次/案例（**降低约 43%**）。
- 使用 FastAPI、PostgreSQL、Redis、Celery 和 SSE 构建异步任务服务，通过 Docker Compose 与 GitHub Actions 实现一键部署、自动测试和回归评测。
- 构建执行轨迹清洗和经验样本生成管道，将成功、失败和人工修正记录转换为可追溯的评测与偏好数据。

## 可核验的关键事实

- **上游边界**：`src/openharness/` **0 个源文件被修改**；上游文件改动仅 `pyproject.toml` 与 `README.md`（见 `docs/UPSTREAM_MAP.md` / `docs/UPSTREAM_CONTRIBUTIONS.md`）。
- **质量基线**：ForgeFlow **181 passed / 1 skipped / 5 deselected（online）**；`ruff` clean；`mypy` strict clean（55 个源文件）。
- **评测复现**：`python -m forgeflow.evaluation.runner --dataset default --strategies plan_gates`（本地确定性）
  `python -m forgeflow.evaluation.runner --dataset default --strategies raw,plan_gates,plan_gates_reviewer --online`（Agent 驱动）。
