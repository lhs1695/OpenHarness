# STATUS — ForgeFlow 项目状态总览（2026-08-05）

> 当前快照，用于快速了解项目到了哪一步（给新读者）。详细演进见 `docs/PLANS.md`（里程碑）、`docs/NEXT_PHASE.md`（路线图）；**操作性的跨会话交接见 `docs/HANDOFF.md`**（本文档只描述状态，不承载交接清单）；复盘见 `docs/RETROSPECTIVE.md`。

## 1. 一句话状态

**M0–M10 全部完成，Agent 驱动在线评测上线，Phase 2 计划项全部落地；Phase 3（生产化+数据闭环）主流程完成（除 A3 跨模型保留）：A1 真实轨迹回流（400 样本，检索 75%→100%）、A2 真实数据集（21 个真实 issue）、A4 中文/语义检索、B1 真实 PR（含 orchestrator 接线）、B2 预算、B3 多仓库、B4 认证、B5 command_results 落 trace（分支 `feat/phase3`）。**

## 2. 里程碑

M0 审计 → M1 适配层 → M2 控制平面 → M3 隔离执行 → M4 质量门禁 → M5 审批/Reviewer → M6 服务化 → M7 Trace → M8 评测 → M9 数据回流 → M10 包装 —— **全部 ✅**（详见 `docs/PLANS.md`）。

## 3. 真实评测数字（DeepSeek，2026-08-05）

| 维度 | 数字 | 存档 |
|---|---|---|
| 确定性本地基线（无模型） | `plan_gates` 完成率 **25%（2/8）** | `evals/reports/2026-08-05-default-plan_gates.md` |
| 在线三策略 | raw **100%（8/8）** · plan_gates **75%** · plan_gates_reviewer **75%** | `evals/reports/2026-08-05-online-default.md` |
| 经验检索 before/after | plan_gates **75% → 87.5%**（注入种子经验） | `evals/reports/2026-08-05-online-default-retrieval.md` |
| A1 真实反馈回流（Phase 3） | 真实样本 400 个（369 success / 31 failure）；不带检索 **75%** → 带真实反馈检索 **100%**（单次运行含随机性） | `evals/data/real-feedback.json` · `evals/reports/2026-08-05-online-a1-*.md` |
| 门禁 vs raw | 平均工具失败 0.88 → 0.50 次/案例（**降约 43%**），完成率 100%→75% 换安全 | — |

- 6 个 billing 基线失败案例：raw 全翻转；门禁策略翻 4 个；billing-005 被 Reviewer 拒绝（如实记录）。

## 4. 质量基线

- ForgeFlow **192 passed / 1 skipped / 6 deselected（online）**；`ruff` clean；`mypy` strict clean（55 源文件）。
- 上游边界可核验：`src/openharness/` **0 源文件被修改**；上游改动仅 `pyproject.toml` 与 `README.md`。

## 5. Git 状态

- `develop` 已推送 origin（含全部 Phase 2 提交）。
- 标签 `upstream-base-0.1.9`（@9b2efd7）已推送 origin。
- **上游同步（P2-1）**：`upstream/main` 相对 `develop` **0 新提交** → 无需同步；`UPSTREAM_MAP` 边界不变。
- 从未推送 `upstream`（HKUDS/OpenHarness），只推送自己的 fork。

## 6. Docker 状态

- `docker compose up -d` 端到端验证通过：四服务 + API 全生命周期 COMPLETED；api 镜像 **597MB**。
- 修复：Dockerfile（清华 pip 镜像、`COPY frontend`、装 git、装 pytest）、compose（alpine 镜像、可写 git 化 fixture 挂载、`FORGEFLOW_REQUIRED_COMMANDS`）。
- 当前：**所有容器已停止/删除，Docker 可安全退出**；恢复用 `docker compose up -d`（镜像缓存秒起）。

## 7. 已交付能力

评测平台（版本化数据集/策略/指标/CLI）、经验检索（`--feedback-dataset` before/after）、模型驱动服务 executor（`FORGEFLOW_EXECUTOR=model`）、服务路径质量门禁（`FORGEFLOW_REQUIRED_COMMANDS`）、Docker Compose 服务化、CI（离线 + 非阻塞上游复验 + 手动在线冒烟）。

## 8. 剩余 / 待做

| 项 | 状态 |
|---|---|
| CI 在线评测 job | ✅ 已实现（`workflow_dispatch` 手动触发，无 secret 自动跳过）；可选加 `schedule` 定时跑 |
| 上游同步（P2-1） | ⏸ upstream 0 新提交，按规则仅在必要时做 |
| 质量基线维护（P2-3） | 持续：改动后 `pytest tests/forgeflow` + `ruff` + `mypy` |
| Phase 3 剩余 | ⏸ 主流程完成（A1/A2/A4/B1/B2/B3/B4/B5）；**A3 跨模型保留不做**；A2 运行需补 attrs 仓库 fixture |

## 9. 文档导航

`PROJECT_SPEC.md`（规格）→ `docs/PLANS.md`（里程碑）→ `docs/ARCHITECTURE.md` / `docs/STATE_MACHINE.md`（设计，含 Mermaid）→ `docs/EVALUATION.md`（评测方法学+实测）→ `docs/NEXT_PHASE.md`（下一步路线图）→ `docs/RETROSPECTIVE.md`（复盘）→ `docs/RESUME.md`（简历）→ `docs/HANDOFF.md`（交接）。
