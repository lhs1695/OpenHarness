# ARCHITECTURE — ForgeFlow 架构

> 基于 M0 审计（`docs/audit/*`、`docs/UPSTREAM_MAP.md`）修订的**目标架构**。落地前不批量建脚手架；每个模块在对应里程碑落地。
> 集成策略见 `docs/adr/0001-integration-strategy.md`。

## 1. 分层

```text
┌──────────────────────────────────────────┐
│ 入口：API (FastAPI) / CLI / 简易页面      │   M6 服务化；V1 先 CLI+API
├──────────────────────────────────────────┤
│ Task Control Plane（业务层）              │
│  DevelopmentTask · RepositoryPolicy      │   M2
│  Risk · Budget · Approval · StateMachine │   M2 / M5
├──────────────────────────────────────────┤
│ ForgeFlow Orchestrator（应用层）          │
│  任务→策略→执行编排 · 审批驱动 · Trace收集│   M1–M7
├──────────────────────────────────────────┤
│ OpenHarness Adapter（集成层）             │
│  经 S1–S5 接缝驱动上游 · 事件映射         │   M1
├──────────────────────────────────────────┤
│ OpenHarness Runtime（上游，复用不改）     │
│  engine/query.py · tools · hooks ·       │
│  swarm/worktree.py · session_backend     │
├──────────────────────────────────────────┤
│ 执行隔离：Local Worktree (M3) / Docker (V2)│
├──────────────────────────────────────────┤
│ Quality Gate & Reviewer · Trace · Eval   │   M4/M5 · M7 · M8/M9
└──────────────────────────────────────────┘
```

## 2. 与上游的接缝（来自审计，逐条可验证）

| 接缝 | 位置 | ForgeFlow 用途 | 里程碑 |
|---|---|---|---|
| S1 进程内执行+事件回调 | `ui/runtime.py:746`；`engine/query_engine.py:227` | 任务输入 → `StreamEvent` 流 | M1 |
| S2 快速通路 | `ui/app.py:177` `run_print_mode` | stream-json 快速验证 | M1 |
| S3 工具/权限裁剪 | `tools/base.py:60`；`coordinator/agent_definitions.py:60` | 按策略限制工具/权限 | M2/M4 |
| S4 Session 后端替换 | `services/session_backend.py:14` | Checkpoint/断点恢复 | M1/M5 |
| S5 钩子 | `hooks/events.py:8` | 审批点、预算、外发 | M2/M5/M7 |
| 隔离执行（复用） | `swarm/worktree.py:135` `WorktreeManager` | Local Worktree 后端 | M3 |

## 3. 目标目录（`src/forgeflow/`，逐里程碑落地）

```text
src/forgeflow/
├── domain/            task.py · policy.py · risk.py · approval.py · states.py      (M2/M5)
├── application/       task_service · approval_service · orchestration_service · event_service (M2/M6)
├── orchestration/     state_machine · budgets · checkpoints · strategies            (M2/M5/M7)
├── integrations/openharness/
│   ├── adapter.py · event_mapper.py · tool_policy.py · exceptions.py               (M1)
├── execution/         base · worktree (适配 WorktreeManager) · docker               (M3/M6)
├── quality/           gates · reviewer · reports                                    (M4/M5)
├── trace/             events · collector · redaction · repository                   (M7)
├── evaluation/        datasets · runner · metrics · reports                         (M8/M9)
└── infrastructure/    database · redis · celery · github                            (M6)
```

## 4. 核心数据流（一次任务）

```text
POST /tasks
  → DevelopmentTask 校验（domain/task）
  → RepositoryPolicy 加载 + 初始风险 + 预算（domain/risk, orchestration/budgets）
  → StateMachine: DRAFT → READY → PREPARING_ENVIRONMENT
  → execution/worktree.prepare（适配 WorktreeManager）
  → Adapter.prepare_context：生成 system prompt + 任务消息（S1）
  → QueryEngine.submit_message → run_query → StreamEvent（模型/工具）
  → Adapter.map_event → TraceEvent（trace/collector 追加写）
  → 预算/审批检查（orchestration/budgets + S5 hooks + domain/approval）
  → quality gates（M4）+ reviewer（M5）→ 最终风险重算
  → 交付：patch / commit / Draft PR（M5，仅测试仓库）
  → Trace 落库 + 评测数据回流（M7/M8/M9）
```

## 5. 与规格 §6/§10 的差异（审计修正）

1. **上游代码位置**：上游包为 `src/openharness/`（规格里的 `<openharness_upstream_package>/` 占位 → 实测为 `src/openharness`）。ForgeFlow 放 `src/forgeflow/`。
2. **`docs/` 非空**：已有 `SHOWCASE.md`、`autopilot/`（跟踪）。ForgeFlow 文档只新增子目录（`docs/audit/`、`docs/adr/`、`docs/learning/`）。
3. **隔离执行已存在**：`WorktreeManager`（`swarm/worktree.py:135`）已提供 git worktree 隔离，M3 是**适配**而非从零实现。
4. **Trace 数据源**：`StreamEvent`（`engine/stream_events.py:82`）已含模型/工具/Token 事件，M7 的 collector 是消费它，不是发明新事件源。
5. **预算基础**：上游 `Settings.max_turns/max_tokens`（`config/settings.py:581/572`）与 `MaxTurnsExceeded`；ForgeFlow 在 adapter 层叠加任务级预算。

## 6. 边界（V1 收敛）

- 单用户/单租户；一个测试仓库类型；Local Worktree。
- 一个 Planner、一个 Implementer、一个 Reviewer。
- 不做：Kubernetes、多云 Runner、自动合并、复杂前端、多租户计费、模型微调、全量 SWE-bench。

## 7. 质量与非功能

- 业务代码有类型标注；状态机/风险/预算必须有单元测试；Adapter 用接口隔离便于 Mock；执行后端有集成测试；一条端到端任务链路。
- 可观测：request_id / task_id / run_id / trace_id + 结构化日志。
- 可恢复：任务状态持久化、Checkpoint 可恢复、Trace 追加写、重复消息幂等。
- 可复现：`git clone → cp .env.example .env → docker compose up --build → pytest → python -m forgeflow.evaluation.runner`。
