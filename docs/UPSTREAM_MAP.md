# UPSTREAM_MAP — 上游能力与 ForgeFlow 关系总表

> 审计对象：`src/openharness/`，commit `af94671`（包 `openharness-ai` 0.1.9）。
> 分类：**复用**（直接用）/ **适配**（通过 Adapter 用，不泄露内部类型）/ **扩展**（通过官方机制接入）/ **修改**（改上游源码，以 `patches/` 留存并 ADR 声明）/ **无关**。

## 上游提供的能力（ForgeFlow 复用什么）

| 上游能力 | 真实位置 | 标记 | ForgeFlow 用途 |
|---|---|---|---|
| Agent Loop（模型/工具循环） | `engine/query.py:633` `run_query`；`engine/query_engine.py:21` `QueryEngine` | **复用（不修改内部）** | 任务执行的运行时 |
| 工具系统 | `tools/base.py:35` `BaseTool`；`:60` `ToolRegistry`；`tools/__init__.py:48` `create_default_tool_registry` | **扩展** | 注册/裁剪任务工具 |
| 插件系统 | `plugins/loader.py:107` `load_plugins` | **扩展** | 装载质量门禁/命令 |
| 技能系统 | `skills/loader.py:42` `load_skill_registry` | **扩展** | 封装计划/审查/测试流程 |
| 钩子系统 | `hooks/events.py:8` `HookEvent`；`hooks/executor.py` `HookExecutor` | **扩展** | 审批点、预算检查、事件外发 |
| 权限系统 | `permissions/checker.py:57` `PermissionChecker`；`modes.py` `PermissionMode` | **复用 + 扩展** | 策略裁剪（denied/allowed/path_rules） |
| 记忆（文件式） | `memory/manager.py`、`memory/paths.py` | **复用** | 参考（ForgeFlow 有自己的 Trace/Dataset） |
| 会话恢复 | `services/session_storage.py:63`；`services/session_backend.py:14` `SessionBackend(Protocol)` | **复用 + 扩展（可替换）** | Checkpoint/断点恢复 |
| Provider 适配 | `api/client.py:80` `SupportsStreamingMessages`；`api/registry.py:55` `PROVIDERS` | **适配** | 多模型/多策略评测 |
| 事件流（Trace 源） | `engine/stream_events.py:82` `StreamEvent`；消费接缝 `ui/runtime.py:621` `handle_line` `render_event` | **扩展** | Trace 事件映射（零侵入） |
| 隔离执行 | `swarm/worktree.py:135` `WorktreeManager` | **复用 + 适配** | Local Worktree 后端（M3） |
| Docker 沙箱 | `sandbox/session.py:29` `start_docker_sandbox`；`sandbox/docker_backend.py` | **复用** | 隔离执行 V2 |
| 后台任务/取消 | `tasks/manager.py:49` `BackgroundTaskManager` | **复用** | 长任务取消/子进程终止 |
| 多 Agent / 子 Agent | `tools/agent_tool.py` `AgentTool`；`coordinator/agent_definitions.py:60` `AgentDefinition`；`swarm/subprocess_backend.py` | **扩展** | Planner/Implementer/Reviewer |
| Shell 子进程 | `utils/shell.py:51` `create_shell_subprocess`；`tools/bash_tool.py` `BashTool` | **复用** | 命令执行（ForgeFlow 叠加禁止命令表） |
| 配置/路径 | `config/settings.py:566` `Settings`；`config/paths.py` | **复用（改动最小化）** | ForgeFlow 配置尽量独立承载 |
| MCP 集成 | `mcp/`、`McpToolAdapter` | **复用** | 外部工具接入 |
| 前端/协议 | `ui/protocol.py` `BackendEvent`/`FrontendRequest` | **复用** | 实时事件订阅（SSE 映射参考） |

## ForgeFlow 原创贡献（上游没有的）

| 能力 | 说明 | 落地里程碑 |
|---|---|---|
| 研发任务控制平面 | `DevelopmentTask`、优先级/SLA、仓库策略、风险评分、执行预算、审批流程、状态机 | M2 / M5 |
| 业务任务 → OpenHarness 输入 | Adapter 层生成 system prompt + 任务消息，经 `submit_message` 执行 | M1 |
| 任务级 Trace | `StreamEvent` → ForgeFlow `TraceEvent`（含 span/父子、Token/成本/延迟、失败分类、脱敏） | M7 |
| 质量门禁 | 目标测试、Lint、类型、禁止路径、Diff 范围、接口兼容、Reviewer 审查、风险策略 | M4 / M5 |
| 评测与数据回流 | 固定任务集、多策略对比、确定性指标、轨迹清洗/切分、经验样本 | M8 / M9 |
| 服务化 | FastAPI、PostgreSQL、Redis、Celery、SSE、Docker Compose | M6 |

## 需修改上游的最小点（候选，待 ADR 确认）

| 位置 | 原因 | 建议 |
|---|---|---|
| `config/settings.py:566` `Settings` | 新增配置项会触碰该模型与 `merge_cli_overrides` | 优先独立 `forgeflow.toml`/环境变量；确需改则 ADR 声明 |
| `pyproject.toml` | M1 需将 `src/forgeflow` 加入 wheel；固定 `mcp<2.0.0`；加 `tzdata`；加 `online` marker | M1 里程碑内一次性改动 |

> 原则：**扩展点优先于侵入式修改**。若审计发现必须改上游核心（如循环行为、Checkpoint 语义），先在此登记，改动以 `patches/` 留存，并同步决策是否回馈上游（`PROJECT_SPEC.md` §2.2）。
