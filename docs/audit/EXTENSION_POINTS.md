# EXTENSION_POINTS — 真实扩展点与 ForgeFlow 接入方案

> 审计对象：`src/openharness/`，commit `af94671`。所有引用均已核验（文件 + 行号）。

## A. 官方扩展机制（设计即支持）

### A1. 工具系统（BaseTool + ToolRegistry）
- 位置：`tools/base.py:35` `BaseTool(ABC)`；`:60` `ToolRegistry`；`tools/__init__.py:48` `create_default_tool_registry`（注册 40 个内置工具 + MCP 工具）
- 机制：子类实现 `execute(arguments, context) -> ToolResult`，Pydantic `input_model` 自动生成 API schema；`ToolRegistry.to_api_schema()` 提供给模型。
- 插件工具动态加载：`plugins/loader.py` `_load_plugin_tools`（从 `<plugin_dir>/tools/*.py` 导入 BaseTool 子类）。
- ForgeFlow：注册「任务执行」「审批」「质量门禁」专用工具；用 `ToolRegistry` 裁剪任务可用工具集。

### A2. 插件系统（Plugins）
- 位置：`plugins/loader.py:107` `load_plugins`；manifest `plugin.json` 或 `.claude-plugin/plugin.json`；贡献 `skills/commands/agents/tools/hooks/mcp_servers`。
- 发现路径：`~/.openharness/plugins` 与 `<cwd>/.openharness/plugins`，受 `Settings.allow_project_plugins` 与 `enabled_plugins` 控制。
- ForgeFlow：可将质量门禁/评测命令做成插件，或复用插件装载机制。

### A3. 技能系统（Skills）
- 位置：`skills/loader.py:42` `load_skill_registry`；`skills/registry.py` `SkillRegistry`；`SKILL.md` + YAML frontmatter（`skills/_frontmatter.py`）。
- 来源：内置 `skills/bundled/content/*.md` + 用户/项目目录（`~/.openharness/skills`、`.openharness/skills`、`.claude/skills`）。
- ForgeFlow：用 Skill 封装「计划生成」「审查」「测试流程」。

### A4. 钩子系统（Hooks）
- 位置：`hooks/events.py:8` `HookEvent`（SESSION_START/END、PRE_COMPACT/POST_COMPACT、PRE_TOOL_USE/POST_TOOL_USE、USER_PROMPT_SUBMIT、NOTIFICATION、STOP、SUBAGENT_STOP）；`hooks/loader.py` `HookRegistry`；`hooks/executor.py` `HookExecutor`（command/http/prompt/agent 四类，`$ARGUMENTS` 替换，`OPENHARNESS_HOOK_EVENT`/`OPENHARNESS_HOOK_PAYLOAD` 环境变量）。
- ForgeFlow：审批点、预算检查、事件外发（如 POST `/trace`）。

### A5. Agent 定义（AgentDefinition）
- 位置：`coordinator/agent_definitions.py:60` `AgentDefinition(BaseModel)`（字段含 `system_prompt/tools/disallowed_tools/model/effort/permission_mode/max_turns/skills/mcp_servers/hooks/background/isolation`）。
- 加载：`~/.openharness/agents` 目录 YAML；`get_agent_definition(name)`；`AgentTool`（`tools/agent_tool.py`）据此派生子 Agent。
- ForgeFlow：为 Planner / Implementer / Reviewer 提供三份 AgentDefinition YAML（含只读权限的 Reviewer）。

### A6. Session 后端（可替换）
- 位置：`services/session_backend.py:14` `SessionBackend(Protocol)`（get_session_dir/save_snapshot/load_latest/list_snapshots/load_by_id/export_markdown）；`DEFAULT_SESSION_BACKEND`；默认实现 `services/session_storage.py`（`save_session_snapshot:63`、`load_session_snapshot:123`，原子写 + 固定 tool_metadata 白名单）。
- ForgeFlow：提供自定义 SessionBackend 或结合 `ExecutionRun.checkpoint` 做长任务断点恢复。

### A7. Provider 适配
- 位置：`api/client.py:80` `SupportsStreamingMessages(Protocol)`；`api/registry.py:17` `ProviderSpec`、`:55` `PROVIDERS`；`api/usage.py` `UsageSnapshot`；`config/settings.py:566` `Settings` + `ProviderProfile`。
- 机制：实现 `stream_message(request) -> AsyncIterator[ApiStreamEvent]` 即可接入新 Provider；检测由 `detect_provider_from_registry` 完成。
- ForgeFlow：评测多 Provider/多模型策略时直接复用。

### A8. 事件流（Trace 数据源）
- 位置：`engine/stream_events.py:82` `StreamEvent` 联合（`AssistantTurnComplete.usage`、`ToolExecutionStarted/Completed` 带 tool 输入输出与 `is_error`）。
- 消费接缝：`ui/runtime.py:621` `handle_line(..., render_event: StreamRenderer, ...)`；`:746` `async for event in bundle.engine.submit_message(...): await render_event(event)`。
- ForgeFlow：`render_event` 回调把 `StreamEvent` 映射为 TraceEvent——**零侵入事件消费**。

### A9. 隔离执行（已存在，直接适配）
- 位置：`swarm/worktree.py:135` `WorktreeManager`（`create_worktree(repo_path, slug, branch, agent_id)` 用 `git worktree add -B worktree-<slug> HEAD`，位于 `~/.openharness/worktrees`，symlink `node_modules/.venv/__pycache__/.tox`，`cleanup_stale` 清理孤儿）；`validate_worktree_slug` 防路径穿越。
- 沙箱：`sandbox/adapter.py:105` `wrap_command_for_sandbox`；`sandbox/session.py:29` `start_docker_sandbox`；`sandbox/docker_backend.py` `DockerSandboxSession`。
- ForgeFlow：M3 直接适配 `WorktreeManager` 作为 Local Worktree 后端；Docker 沙箱留 V2。

## B. 专项检查（PROJECT_SPEC §17.1 第 6 项）

### B1. 工作区路径隔离
- `utils/shell.py` `create_shell_subprocess` 的 cwd 恒为 `str(Path(cwd).resolve())`；子进程在指定 cwd 下运行。
- 会话/记忆按 `<project>-<sha1[:12]>` 命名空间（`config/paths.py`），不同 worktree 因 cwd 不同而隔离。
- 说明：上游的「任务 Workspace」概念是 cwd 约束，**没有** ForgeFlow 需要的「绝对路径越界校验」工具级强制；ForgeFlow 需在 adapter/工具层补强（路径解析为绝对路径后校验是否越界）。

### B2. Shell 命令执行
- `utils/shell.py:51` `create_shell_subprocess`：bash `-lc` / pwsh / cmd 选择；Docker 沙箱路由；`BashTool`（`tools/bash_tool.py`，timeout ≤600s，`_terminate_process(force=True)`，输出截断 12000 字符，交互命令预检）。
- ForgeFlow：**必须**在工具/权限层加禁止命令表与结构化参数约束（上游只有 `denied_commands` 通配，无「按仓库策略的 forbidden_commands + required_commands」）。

### B3. 并行工具调用
- `run_query` 在多个 `tool_uses` 时用 `asyncio.gather` 并行执行（`engine/query.py` 内部）。
- ForgeFlow：Trace 需为并行工具建立父子 span。

### B4. 任务取消
- `tasks/manager.py:49` `BackgroundTaskManager.stop_task`（SIGTERM→SIGKILL）；`BashTool` `_terminate_process`；React TUI `FrontendRequest(type="interrupt")`；`asyncio.CancelledError` 在 `BashTool.execute` 中处理。
- ForgeFlow：取消请求 → `stop_task` 终止子进程 → 状态机到 CANCELLED；需验证长任务下子进程树确实终止（Windows 下需注意）。

### B5. 中断恢复
- 每次 `handle_line` 后 `save_session_snapshot`（`services/session_storage.py:63`）；CLI `--continue/--resume`（`cli.py` → `load_session_snapshot/load_session_by_id`）；恢复后 `sanitize_conversation_messages`（`engine/messages.py`）修复中断的工具尾部。
- ForgeFlow：可复用快照机制作为 Checkpoint 基础，但业务状态机需自行持久化。

### B6. Token / 步数预算
- `Settings.max_turns=200`（`config/settings.py:581`）、`Settings.max_tokens=16384`（`:572`）；`run_query` 的 `turn_count < max_turns` 守卫（`query.py:700`）与 `MaxTurnsExceeded`；自动压缩 `auto_compact_if_needed`；`CostTracker`（`engine/cost_tracker.py:8`）。
- ForgeFlow：在上游基础上叠加任务级预算（最大工具调用、最大 Token、最大时长、最大并发），超限进入 `BUDGET_EXCEEDED` 并停止。

### B7. 子 Agent 权限传播
- `swarm/permission_sync.py`（文件信箱 `~/.openharness/teams/<team>/permissions/`）；`TeammateSpawnConfig.permissions/plan_mode_required/allow_permission_prompts/worktree_path`；环境变量 `CLAUDE_CODE_TEAM_NAME/AGENT_ID/AGENT_NAME/COLOR`。
- `AgentDefinition.permission_mode`（PERMISSION_MODES: acceptEdits / bypassPermissions / dontAsk）。
- ForgeFlow：Reviewer 用只读 AgentDefinition + 限制工具；需验证权限确实不会被子 Agent 提权。

### B8. 事件 / 日志接口
- 引擎事件：`engine/stream_events.py`（上述 A8）。
- UI 协议：`ui/protocol.py` `BackendEvent` / `FrontendRequest`（transcript_item、tool_started/completed、permission_response、interrupt…）。
- 持久化：`get_logs_dir()`、`get_tasks_dir()/<id>.log`、会话快照。
- ForgeFlow：以 `StreamEvent` 为主 Trace 源；UI 协议层提供实时订阅参考（SSE 时可映射）。

## C. 需要修改上游的最小点（候选，待 ADR 确认）

| 位置 | 原因 | 建议 |
|---|---|---|
| `config/settings.py:566` `Settings` | ForgeFlow 新增任务/策略配置项会触碰该模型与 `merge_cli_overrides` | 尽量通过环境变量/独立 `forgeflow.toml` 承载，避免改 Settings |
| （如需要）`engine/query.py` | 若要改循环行为（强制预算、特殊工具语义） | 优先 adapter 层控制，不进 `run_query` |

除上述外，其余能力均通过 A1–A9 无侵入接入。
