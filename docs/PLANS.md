# PLANS — ForgeFlow 里程碑计划与进度

> 工作文档：记录每个里程碑的目标、交付、验收与状态。执行规则见 `PROJECT_SPEC.md` §16/§17。
> 工作流：一个里程碑一个 Worktree（从 `develop` 派生）→ 先验收测试 → 实现 → 目标测试 → §17.4 独立审查 → merge 回 develop → 更新本文件 + `docs/HANDOFF.md`。

## 进度总览

| 里程碑 | 状态 | worktree / 分支 | 关键产出 |
|---|---|---|---|
| M0 上游审计与基线 | ✅ 完成（2026-08-05，已审查） | `milestone/m0-audit` | `docs/audit/*`、`docs/UPSTREAM_MAP.md`、`docs/adr/0001` |
| M1 最小适配层与垂直链路 | ✅ 实现完成（待独立审查） | `milestone/m1-adapter` | `src/forgeflow/integrations/openharness/*` + `domain/task.py` + 测试 |
| M2 状态机/风险/预算 | 待开始 | `milestone/m2-control-plane` | `domain/*`、`orchestration/*` |
| M3 Local Worktree 隔离执行 | 待开始 | `milestone/m3-isolation` | `execution/worktree.py` |
| M4 代码修改与质量门禁 | 待开始 | `milestone/m4-quality` | `quality/*` |
| M5 审批/Reviewer/交付 | 待开始 | `milestone/m5-approval` | `domain/approval.py`、`quality/reviewer.py` |
| M6 服务化与持久化 | 待开始 | `milestone/m6-service` | `api/`、`infrastructure/`、compose |
| M7 全链路 Trace | 待开始 | `milestone/m7-trace` | `trace/*` |
| M8 评测平台 | 待开始 | `milestone/m8-eval` | `evaluation/*`、`evals/` |
| M9 数据回流与经验闭环 | 待开始 | `milestone/m9-feedback` | `evaluation/datasets.py` |
| M10 包装与维护 | 待开始 | `milestone/m10-packaging` | README、CI、40+ 测试 |

## M1 — 最小适配层与垂直链路（实现完成，待独立审查）

**目标**：打通 `DevelopmentTask → Adapter → 分析测试仓库 → 生成计划 → 结构化结果`。不接 DB/队列，内存状态，单任务单进程。

**落地文件**：
```text
src/forgeflow/__init__.py
src/forgeflow/py.typed
src/forgeflow/domain/task.py            # DevelopmentTask（pydantic，最小字段）
src/forgeflow/integrations/openharness/adapter.py      # S1 接缝：EngineLike + run_plan
src/forgeflow/integrations/openharness/event_mapper.py # StreamEvent → TraceEvent
src/forgeflow/integrations/openharness/exceptions.py   # ForgeFlowError 层级
tests/forgeflow/unit/test_adapter.py                   # 13 项（fake engine）
tests/forgeflow/unit/test_event_mapper.py
tests/forgeflow/integration/test_vertical_chain.py      # online marker
tests/forgeflow/fixtures/repositories/billing-service/  # 最小 fixture 仓库
pyrightconfig.json                                       # extraPaths=src（编辑器）
```

**对 `pyproject.toml` 的改动**（ADR 0001 已声明）：wheel 增加 `src/forgeflow`；dev 依赖固定 `mcp<2.0.0` + 加 `tzdata`；pytest 加 `online` marker + `addopts = "-m \"not online\""`。

**实际验证结果（2026-08-05）**：
- 单元测试：`pytest tests/forgeflow -q` → **13 passed, 1 deselected**（online 默认跳过）
- 垂直链路（真实模型）：`pytest -m online tests/forgeflow/integration/test_vertical_chain.py` → **1 passed**（41.6s，DeepSeek 端点，输出结构化 TaskPlan + token）
- Lint：`ruff check src/forgeflow tests/forgeflow` → **clean**
- 类型：`MYPYPATH=src mypy src/forgeflow --explicit-package-bases --python-version 3.11` → **Success**（8 文件）
- 设计要点：adapter 通过注入的 `EngineLike` 驱动引擎（接口隔离，便于 Mock）；业务层不 import `openharness.*`；`TraceEvent`/`TaskPlan` 为 ForgeFlow 类型。

**注意**：ForgeFlow 的 mypy 需用上述命令（editable 安装 + py.typed 会导致 plain `mypy src/forgeflow` 报模块重复）。

**验收**：
- 固定测试仓库 + 任务 → 输出结构化计划（目标文件、步骤、风险点、测试计划、token/时长）；
- Adapter 不泄漏上游内部类型到业务层（业务层不 import `openharness.*` 内部类）；
- Adapter 单元测试通过；明确错误类型。

**验证命令**：`pytest tests/forgeflow -q`；`ruff check src/forgeflow`；`mypy src/forgeflow --python-version 3.11`（只对 ForgeFlow 代码，不要求上游全树通过）。

## M2 — 状态机/风险/预算

- `domain/policy.py`、`domain/risk.py`、`orchestration/state_machine.py`、`orchestration/budgets.py`。
- 状态机见 `docs/STATE_MACHINE.md`；风险规则透明可解释（0–100，输出原因）；预算超限 → `BUDGET_EXCEEDED`。
- 验收：状态转移测试覆盖正常/失败/取消/非法；风险原因可解释；超预算停止；同一命令重复执行不重复改状态。

## M3 — Local Worktree 隔离执行

- `execution/base.py` + `execution/worktree.py`（适配 `WorktreeManager`，`swarm/worktree.py:135`）。
- 验收：不修改原工作目录；失败可清理；路径越界拒绝（绝对路径解析 + 越界校验）；超时终止子进程；3 个固定任务完成。

## M4 — 代码修改与质量门禁

- `quality/gates.py`、`quality/reports.py`。门禁只对**改动文件**跑 ruff/mypy（上游全树本就不通过，见 `docs/audit/BASELINE.md` §3.4/3.5）。
- 验收：支持 pytest/Ruff/mypy 中实际可用命令；失败结构化保存；禁止路径与 Diff 大小门禁生效；禁止"改测试掩盖 Bug"；5 个固定任务可复现。

## M5 — 审批/Reviewer/交付

- `domain/approval.py`、`quality/reviewer.py`（Reviewer = 只读 AgentDefinition + 限制工具）。
- 验收：Reviewer 默认只读；未批准高险不继续；审批接口幂等；Draft PR 仅测试仓库；审批进审计 Trace。

## M6 — 服务化与持久化

- `application/`、`api/`、`infrastructure/`（FastAPI + PostgreSQL + Redis + Celery + SSE + Docker Compose）。
- Windows：Celery 用 `--pool=solo`/threads；先验证 WSL2 再上 compose。
- 验收：API 可建/启/查/取消任务；SSE 实时；重启不丢；Celery 幂等；compose 可启动。

## M7 — 全链路 Trace

- `trace/events.py`、`collector.py`、`redaction.py`、`repository.py`。数据源 `StreamEvent`（`engine/stream_events.py:82`）。
- 验收：一个任务可导出完整 JSONL；父子/并行 span 可还原；敏感数据脱敏；CLI/页面可看时间线。

## M8 — 评测平台

- `evaluation/*` + `evals/`（20–30 固定任务）。初始策略：原始基线 / 计划+门禁 / 计划+门禁+Reviewer。
- 验收：同数据集可重复运行；实验配置版本化；报告含失败案例（不只平均分）。

## M9 — 数据回流与经验闭环

- `evaluation/datasets.py`、`docs/EVALUATION.md`。Trace → 脱敏 → 清洗 → 切分 → 成功/失败分类 → 样本。
- 验收：真实样本可查看、可溯源到任务与版本；可做"历史经验检索前后"对比实验；不夸大已做模型后训练。

## M10 — 包装与维护

- README、架构图、演示视频、API 文档、评测报告、安全文档、CI、40+ 测试、复盘、20 面试题。
- 验收：空环境可部署；端到端演示；评测可复现；简历指标有脚本支撑；清晰区分上游/个人贡献。

## 上游同步

- 仅里程碑间隙、且确为安全/兼容/严重 Bugfix 时：`git fetch upstream` → 独立 `sync/upstream-<sha>` 分支 → 先跑上游测试再跑 ForgeFlow 回归 → 更新 `UPSTREAM.md`/`docs/UPSTREAM_MAP.md`。
