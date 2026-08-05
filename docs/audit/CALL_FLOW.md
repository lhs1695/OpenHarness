# CALL_FLOW — 一次完整请求的调用链

> 审计对象：`src/openharness/`，commit `af94671`。
> 说明：以下为「非交互式执行一条消息」的调用链，是 ForgeFlow 接入的主要路径。

## 调用链总览

```text
用户输入 / 任务提示词
  ↓
src/openharness/cli.py  Typer app 根命令（cli.py: app）
  ↓ --print 非交互模式
src/openharness/ui/app.py:177  async def run_print_mode(...)
  ├─ :210  bundle = await build_runtime(...)
  └─ :304  await handle_line(bundle, ..., render_event=_render_event)
        ↓
src/openharness/ui/runtime.py:274  async def build_runtime(...)
  ├─ :367  system_prompt_text = build_runtime_system_prompt(...)   # prompts/context.py:102
  └─ 组装 engine / tool_registry / permission_checker / hooks / session_backend / api_client
        ↓
src/openharness/ui/runtime.py:621  async def handle_line(..., render_event: StreamRenderer, ...)
  ├─ :626  render_event 参数注入（ForgeFlow 事件接缝在此）
  ├─ 斜杠命令分发（commands/registry.py）或：
  └─ :746  async for event in bundle.engine.submit_message(user_message or line):
             await render_event(event)
        ↓
src/openharness/engine/query_engine.py:227  async def submit_message(...) -> AsyncIterator[StreamEvent]
  └─ 追加 user 消息 → 委托 run_query
        ↓
src/openharness/engine/query.py:633  async def run_query(context, messages)
  ├─ :700  while turn_count < context.max_turns:           # 步数上限（Settings.max_turns=200）
  ├─ 每轮先做 auto-compact 检查（services/compact.py，触发 PRE/POST_COMPACT 钩子）
  ├─ 调用 api_client.stream_message(ApiMessageRequest(...))   # 模型调用（api/client.py: SupportsStreamingMessages）
  ├─ 产出 AssistantTextDelta / AssistantTurnComplete(usage)
  ├─ 若消息含 tool_uses：
  │    └─ :887  async def _execute_tool_call(...)           # 单工具或 asyncio.gather 并行（>1 个）
  │         ├─ PRE_TOOL_USE 钩子
  │         ├─ context.permission_checker.evaluate(...)     # permissions/checker.py:75
  │         ├─ 必要时 permission_prompt 确认（ui/permission_dialog.py 或注入的确认回调）
  │         ├─ tool.execute(parsed_input, ToolExecutionContext(...))   # tools/base.py:35 BaseTool
  │         ├─ 产出 ToolExecutionStarted / ToolExecutionCompleted（输出 / is_error）
  │         └─ POST_TOOL_USE 钩子
  │    └─ 工具结果追加为 ToolResultBlock（engine/messages.py:49）
  └─ 循环至模型不再请求工具，或抛 MaxTurnsExceeded
        ↓
render_event(event) 回调逐事件输出（文本 / stream-json 等，见 run_print_mode 输出格式）
        ↓
（会话模式）services/session_storage.py:63 save_session_snapshot 在 handle_line 后持久化
```

## 关键事件类型（engine/stream_events.py:82）

| 事件 | 字段 | ForgeFlow 用途 |
|---|---|---|
| `AssistantTextDelta` | `text` | 模型增量输出 |
| `AssistantTurnComplete` | `message`, `usage: UsageSnapshot` | 一轮完成 + Token 用量 |
| `ToolExecutionStarted` | `tool_name`, `tool_input` | 工具调用开始 |
| `ToolExecutionCompleted` | `tool_name`, `output`, `is_error`, `metadata` | 工具结果 / 失败 |
| `ErrorEvent` | `message`, `recoverable` | 错误分类 |
| `StatusEvent` | `message` | 状态提示 |
| `CompactProgressEvent` | `phase`, `trigger`, ... | 压缩进度 |

## ForgeFlow 的接入点（对应调用链位置）

1. **事件消费（无侵入）**：替换/包装 `handle_line` 的 `render_event` 回调（`runtime.py:746`），将 `StreamEvent` 映射为 ForgeFlow `TraceEvent`。
2. **任务输入**：用 `DevelopmentTask` 生成 system prompt + 首条 user message，通过 `submit_message` 在目标仓库 cwd 下执行。
3. **工具/权限裁剪**：`ToolRegistry`（`tools/base.py:60`）+ AgentDefinition 的 `tools/disallowed_tools/permission_mode`（`coordinator/agent_definitions.py:60`）。
4. **审批/预算**：`HookEvent`（USER_PROMPT_SUBMIT / PRE_TOOL_USE / POST_TOOL_USE / STOP）挂钩子。
5. **Checkpoint/恢复**：`SessionBackend`（`services/session_backend.py:14`）替换，或配合 `ExecutionRun.checkpoint`。
6. **步数/预算**：上游 `max_turns`（`query.py:700`）+ `Settings.max_tokens`；ForgeFlow 在 adapter 层叠加 Token/工具数/时长预算。

## 并行工具调用

`run_query` 在多个 `tool_uses` 时用 `asyncio.gather` 并行执行（`query.py` 内部），ForgeFlow Trace 需为并行工具建立 span/父子关系（可用 `ToolExecutionStarted` 的 event 序列 + metadata 关联）。

## 无交互执行入口（供 M1 快速验证）

- `run_print_mode(..., output_format="stream-json")`（`ui/app.py:177`）输出 JSON 事件流；
- `run_task_worker`（`ui/app.py:92`）stdin 驱动的一次性 worker（多 Agent subprocess backend 的入口，`swarm/subprocess_backend.py`）。
