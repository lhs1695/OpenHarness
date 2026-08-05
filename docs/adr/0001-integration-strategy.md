# ADR 0001 — OpenHarness 集成策略

- 日期：2026-08-05
- 状态：已接受（基于 M0 审计，见 `docs/audit/*` 与 `docs/UPSTREAM_MAP.md`）
- 里程碑：M0 → M1

## 背景

ForgeFlow 需要驱动 OpenHarness 执行研发任务、按策略裁剪工具与权限、消费执行事件构建 Trace、支持审批/预算/断点恢复，同时保持上游可同步。审计结论（`docs/audit/EXTENSION_POINTS.md`）：OpenHarness 提供了充分的无侵入扩展接缝，核心循环（`engine/query.py` `run_query`）不应修改。

## 决策：adapt-and-extend（适配 + 扩展，最小侵入）

ForgeFlow 通过以下 5 条已核验接缝接入，**不改动上游核心内部**：

| 接缝 | 真实位置 | 用途 |
|---|---|---|
| S1 进程内执行 + 事件回调 | `ui/runtime.py:746`（`async for event in bundle.engine.submit_message(...): await render_event(event)`）；`engine/query_engine.py:227` `submit_message`；`ui/app.py:300` `handle_line` | 任务输入（system prompt + 任务消息）→ 执行 → `StreamEvent` 流 |
| S2 快速通路 | `ui/app.py:177` `run_print_mode(output_format="stream-json")` | M1 垂直链路快速验证；最终以 S1 为主 |
| S3 工具/权限裁剪 | `tools/base.py:60` `ToolRegistry`；`coordinator/agent_definitions.py:60` `AgentDefinition`（`tools/disallowed_tools/permission_mode`）；`permissions/checker.py:57` | 按仓库策略限制任务可用工具与权限 |
| S4 断点/恢复 | `services/session_backend.py:14` `SessionBackend(Protocol)`（可替换） | 长任务 Checkpoint 基础 |
| S5 审批/预算/外发 | `hooks/events.py:8` `HookEvent`（USER_PROMPT_SUBMIT / PRE_TOOL_USE / POST_TOOL_USE / STOP）；`hooks/executor.py` | 审批点、预算检查、事件外发 |

隔离执行：M3 直接适配 `swarm/worktree.py:135` `WorktreeManager`（复用，不重写）。

## 必须修改的上游文件（最小集合）

| 文件 | 改动 | 里程碑 |
|---|---|---|
| `pyproject.toml` | wheel 增加 `src/forgeflow`；dev 依赖固定 `mcp<2.0.0` + 加 `tzdata`；可选 `forgeflow` console script；pytest 加 `online` marker | M1 |
| `config/settings.py`（候选） | 新增 ForgeFlow 配置项时优先走独立 `forgeflow.toml`/环境变量；确需触碰 `Settings` 时在此 ADR 追加记录 | 按需 |

除上述外，**不改任何 `engine/`、`api/`、`permissions/`、`ui/`、`tasks/` 等核心源码**。

## 适配层接口（M1 目标）

`src/forgeflow/integrations/openharness/adapter.py` 暴露给业务层的最小接口：

```python
# 目标签名（M1 落地，可在实现时微调，不泄漏上游内部类型）
class OpenHarnessAdapter(Protocol):
    async def prepare_context(self, task: DevelopmentTask, repo_path: str) -> RunContext: ...
    async def execute(self, ctx: RunContext, messages: list[Message]) -> AsyncIterator[TraceEvent]: ...
    def map_event(self, upstream_event: Any) -> TraceEvent | None: ...
```

- 业务层只依赖 ForgeFlow 类型（`DevelopmentTask` / `TraceEvent` / 自定义异常），不直接 import `openharness.*` 内部类。
- 异常统一封装：`ForgeFlowError` 层级（`MaxTurnsExceeded`、`ProviderError`、`TimeoutError`、`BudgetExceeded`）。
- 事件映射：`StreamEvent`（`engine/stream_events.py:82`）→ `TraceEvent`（`AssistantTurnComplete.usage` → token/成本；`ToolExecutionStarted/Completed` → 工具输入输出/`is_error`）。

## 备选方案与放弃原因

1. **整体改 `run_query` 循环**：拒绝。会破坏上游可同步性、增加回归面；S1 接缝已足够。
2. **把 ForgeFlow 做成 plugin/skill 挂载**：部分采用。技能/命令用官方机制挂载，但任务控制平面是独立进程内服务，不适合全部做成插件。
3. **独立仓库、把 OpenHarness 当 pip 依赖**：拒绝。需要改上游语义（隔离、审批）时无法本地补丁；当前放在同仓库 `src/forgeflow/`，改动可追踪、补丁可留存（`patches/`）。

## 影响与风险

- 上游同步：仅 `pyproject.toml` 需冲突协调；其余改动独立于上游文件 → 同步成本低。
- 若审计后期发现必须改核心（如 Checkpoint 语义），在本 ADR 追加"必须修改清单"，改动以 `patches/` 留存。
