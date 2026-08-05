# MODULE_MAP — OpenHarness 模块图与 ForgeFlow 关系

> 审计对象：`src/openharness/`（包 `openharness-ai` 0.1.9，commit `af94671`，见 `BASELINE.md`）。
> 分类标记：
> - **复用**：ForgeFlow 直接使用，不改代码；
> - **Adapter**：通过适配层间接使用，不泄漏内部类型；
> - **扩展**：通过官方扩展机制（工具/插件/钩子/Agent 定义等）接入；
> - **修改**：需要改动上游源码（应尽量避免，改动以 `patches/` 留存）；
> - **无关**：与 ForgeFlow 业务无关。

## 顶层文件

| 文件 | 职责 | 标记 |
|---|---|---|
| `__main__.py` | `python -m openharness` 入口，调用 `app()` | 复用 |
| `cli.py` | Typer CLI 根命令；`--continue/--resume/--max-turns/--permission-mode/--allowed-tools/--disallowed-tools/--backend-only/--task-worker/--print` 等；分发到 `run_print_mode` / `run_repl` / `run_task_worker` | 复用 + 扩展（ForgeFlow 可加子命令） |
| `main.py` | 包级主入口（若存在） | 复用 |

## 目录清单

### api — Provider 适配与用量
- 文件：`client.py`、`registry.py`、`provider.py`、`usage.py`、`auth_*` 等
- 职责：`SupportsStreamingMessages` 协议（`client.py:80`）；`ProviderSpec`（`registry.py:17`）+ `PROVIDERS`（`registry.py:55`）；`UsageSnapshot`（`usage.py`）；`detect_provider`（`provider.py`）
- 标记：**Adapter**（ForgeFlow 可通过协议接入自定义 Provider；`UsageSnapshot` 是 Token/成本统计来源）

### auth — 认证
- 职责：OAuth / API Key 解析（`config/settings.py:resolve_auth`）
- 标记：**无关**（ForgeFlow 单用户/单租户不需要多 Provider 认证矩阵；安全审计需关注）

### autopilot — 仓库级自动执行状态
- 职责："Project-level repo autopilot state, intake, and execution helpers"
- 标记：**参考**（任务 intake/执行帮助与 ForgeFlow 有概念重叠，需进一步确认是否可复用，不直接采用）

### bridge — 桥接会话
- 职责：跟踪/生成桥接会话（`manager.py`、`session_runner.py`）
- 标记：**无关**（面向 UI/命令的桥接会话）

### channels — 聊天渠道
- 职责：Slack / Telegram / Discord / Feishu / DingTalk / Matrix / Mocha 消息渠道
- 标记：**无关**（ForgeFlow V1 不接聊天渠道）

### commands — 斜杠命令
- 职责：`CommandRegistry` / `SlashCommand`（`commands/registry.py`）
- 标记：**扩展**（ForgeFlow 可注册任务/评测命令）

### config — 配置与路径
- 文件：`settings.py`（`Settings(BaseModel)` 于 `:566`；`max_tokens=16384` `:572`、`max_turns=200` `:581`）、`paths.py`（`get_config_dir/get_data_dir/get_sessions_dir/get_tasks_dir/get_project_config_dir`）
- 标记：**扩展**（ForgeFlow 新配置项会触碰 `Settings` 与 `merge_cli_overrides`，属**可能必须修改**的最小点之一，需 ADR 声明）

### coordinator — 协调器模式与 Agent 定义
- 文件：`coordinator_mode.py`、`agent_definitions.py`（`AgentDefinition(BaseModel)` 于 `:60`，含 `tools/disallowed_tools/model/effort/permission_mode/max_turns/skills/mcp_servers/hooks`）、`drain.py`
- 标记：**扩展**（ForgeFlow 的 Planner/Implementer/Reviewer 可做成 AgentDefinition YAML，从 `~/.openharness/agents` 加载）

### engine — 核心循环与事件
- 文件：`query.py`（`run_query` 于 `:633`，`while turn_count < context.max_turns` 于 `:700`；`_execute_tool_call` 于 `:887`）、`query_engine.py`（`QueryEngine` 于 `:21`，`submit_message` 于 `:227`）、`messages.py`（`ConversationMessage`、`ContentBlock` 判别联合）、`stream_events.py`（`StreamEvent` 联合于 `:82`）、`cost_tracker.py`（`CostTracker` 于 `:8`）
- 标记：**复用 + 扩展**。事件流 `StreamEvent`（`AssistantTurnComplete` 带 `usage`、`ToolExecutionStarted/Completed` 带输入输出/`is_error`）是 ForgeFlow Trace 的数据源；**核心循环内部尽量避免修改**（自动压缩、工具并行、预算控制都在这里）

### hooks — 生命周期钩子
- 文件：`events.py`（`HookEvent(str, Enum)` 于 `:8`：SESSION_START/END、PRE_COMPACT/POST_COMPACT、PRE_TOOL_USE/POST_TOOL_USE、USER_PROMPT_SUBMIT、NOTIFICATION、STOP、SUBAGENT_STOP）、`loader.py`（`HookRegistry`）、`executor.py`（`HookExecutor`，支持 command/http/prompt/agent 四类）、`schemas.py`
- 标记：**扩展**（ForgeFlow 用 hooks 做审批点、预算检查、事件外发）

### keybindings / vim / voice / themes / output_styles — TUI 与输入
- 职责：快捷键、Vim 模式、语音、主题、输出样式
- 标记：**无关**

### mcp — MCP 集成
- 职责：MCP server 连接与工具适配（`McpToolAdapter`）
- 标记：**复用**（工具层；注意环境需 `mcp<2.0.0`，见 `RISK_REGISTER.md`）

### memory — 文件式记忆
- 文件：`manager.py`、`paths.py`（`get_project_memory_dir`）、`scan.py`、`relevance.py`、`search.py`、`schema.py`
- 职责：markdown 文件 + YAML frontmatter + `MEMORY.md` 索引，非向量库
- 标记：**复用**（ForgeFlow 的评测经验回流可参考其思路，但 ForgeFlow 有独立的 Trace/Dataset 体系）

### permissions — 权限
- 文件：`checker.py`（`PermissionChecker` 于 `:57`；`SENSITIVE_PATH_PATTERNS` 于 `:18`；`evaluate` 于 `:75`；`PermissionDecision` 于 `:40`）、`modes.py`（`PermissionMode`：DEFAULT/PLAN/FULL_AUTO）
- 标记：**复用 + 扩展**（ForgeFlow 用 `denied_tools/allowed_tools/denied_commands/path_rules` + AgentDefinition 的 `permission_mode` 做策略裁剪；**避免默认修改 `evaluate` 核心逻辑**，除非审计证明必须）

### personalization — 个人化规则提取
- 职责：从会话提取本地规则（`extractor.py`、`session_hook.py`）
- 标记：**无关**（面向个人使用习惯；与研发任务平台业务无直接关系）

### plugins — 插件系统
- 文件：`loader.py`（`load_plugins` 于 `:107`；manifest `plugin.json`；贡献 skills/commands/agents/tools/hooks/mcp_servers）、`types.py`（`LoadedPlugin`）、`installer.py`
- 标记：**扩展**（ForgeFlow 可整体做成插件，或复用插件机制装载质量门禁/工具）

### prompts — 提示词构建
- 文件：`context.py`（`build_runtime_system_prompt` 于 `:102`）等
- 标记：**复用 + 扩展**（ForgeFlow 生成任务 system prompt，覆盖/拼接上游）

### sandbox — 沙箱
- 文件：`adapter.py`（`wrap_command_for_sandbox` 于 `:105`）、`session.py`（`start_docker_sandbox` 于 `:29`）、`docker_backend.py`（`DockerSandboxSession`）
- 标记：**复用**（ForgeFlow 隔离执行 V2 的 Docker 后端；V1 用本地 worktree）

### services — 会话/压缩/后台
- 文件：`session_storage.py`（`save_session_snapshot` 于 `:63`、`load_session_snapshot` 于 `:123`）、`session_backend.py`（`SessionBackend(Protocol)` 于 `:14`）、`compact*`、`cron_scheduler.py`、`memory_*`、`autodream.py`
- 标记：**复用 + 扩展**（`SessionBackend` 是**可替换接缝**，ForgeFlow 可用自定义后端做 Checkpoint）

### skills — 技能
- 文件：`loader.py`（`load_skill_registry` 于 `:42`）、`registry.py`（`SkillRegistry`）、`types.py`（`SkillDefinition`）、`_frontmatter.py`
- 职责：`SKILL.md` + YAML frontmatter；来源含 `~/.openharness/skills`、`.openharness/skills`、`.claude/skills`
- 标记：**复用 + 扩展**（ForgeFlow 用 Skill 封装任务流程/质量流程）

### state — 应用状态
- 文件：`app_state.py`、`store.py`（observable 状态存储）
- 标记：**参考**（偏 UI 状态；ForgeFlow 状态机是业务状态机，独立实现，不直接复用）

### swarm — 多 Agent 与 Worktree 隔离
- 文件：`worktree.py`（`WorktreeManager` 于 `:135`，`create_worktree` 用 `git worktree add -B worktree-<slug>`）、`registry.py`（`BackendRegistry`）、`subprocess_backend.py`、`permission_sync.py`、`worktree.py`
- 标记：**复用 + 扩展**（**隔离执行已存在**——ForgeFlow M3 直接适配 `WorktreeManager`）

### tasks — 后台任务管理
- 文件：`manager.py`（`BackgroundTaskManager` 于 `:49`：`create_shell_task/create_agent_task/stop_task/write_to_task/read_task_output`，任务 ID 前缀 b/a/r/t/d）
- 标记：**复用**（ForgeFlow 任务取消、子进程终止用它）

### tools — 工具系统
- 文件：`base.py`（`ToolExecutionContext` 于 `:18`、`ToolResult` 于 `:27`、`BaseTool(ABC)` 于 `:35`、`ToolRegistry` 于 `:60`）、`__init__.py`（`create_default_tool_registry` 于 `:48`，注册约 50 个内置工具）、`bash_tool.py`（`BashTool`）、`agent_tool.py`、`skill_tool.py` 等
- 标记：**扩展**（ForgeFlow 用 `ToolRegistry` + 插件工具装载机制注册任务工具）

### ui — 运行时与协议
- 文件：`app.py`（`run_task_worker` 于 `:92`、`run_print_mode` 于 `:177`）、`runtime.py`（`build_runtime` 于 `:274`、`handle_line` 于 `:621`、`render_event: StreamRenderer` 参数于 `:626`）、`protocol.py`（`BackendEvent/FrontendRequest`）
- 标记：**复用 + 扩展**（**`render_event` 是 ForgeFlow 无侵入事件消费接缝**：`handle_line` 内 `async for event in bundle.engine.submit_message(...): await render_event(event)`（`runtime.py:746`））

### utils — 工具函数
- 文件：`shell.py`（`create_shell_subprocess` 于 `:51`，`resolve_shell_command`）、`fs.py`、`lock.py` 等
- 标记：**复用**（Shell 子进程、原子写、文件锁）

## 结论摘要

- 直接复用量大：engine 事件流、tools、skills、plugins、hooks、permissions、sandbox、tasks、swarm/worktree、services/session_backend。
- 无侵入扩展点充分：工具注册、插件、Skill、Hook、AgentDefinition、SessionBackend、Provider 协议、`render_event` 事件接缝。
- 需谨慎修改的最小点：`config/settings.py`（新增配置项）。
- 与 ForgeFlow 无关：channels、bridge、keybindings、vim、voice、themes、output_styles、personalization。
