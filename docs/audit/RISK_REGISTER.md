# RISK_REGISTER — 风险登记

> 审计对象：`src/openharness/`，commit `af94671`。风险等级：P0（阻断）/ P1（高）/ P2（中）/ P3（低）。

## 环境与平台

| # | 风险 | 触发条件 | 影响 | 等级 | 缓解 |
|---|---|---|---|---|---|
| R1 | `mcp>=1.0.0` 可能装到 2.x | `pip install -e ".[dev]"` 全量重装 | 运行时 MCP 兼容破坏 | P1 | M1 固定 `mcp<2.0.0`（当前 1.29.0 正常） |
| R2 | Windows 缺 `tzdata` | cron/zoneinfo 使用 | `cron_scheduler` 等报错 | P1 | dev 依赖加 `tzdata` |
| R3 | 真实凭据污染测试 | shell 存在 `ANTHROPIC_AUTH_TOKEN`/`ANTHROPIC_BASE_URL` | provider 检测测试失败、可能发起真实调用 | P0 | 测试前清全部 `ANTHROPIC_*`；用隔离 HOME；`~/.openharness/` 已在 `.gitignore` |
| R4 | 符号链接创建无权限 | Windows 默认无开发者模式 | `test_symlink_escape_blocked` 失败；M3 worktree symlink 受限 | P1 | `swarm/worktree.py` 已对 symlink OSError 降级；文档说明需开发者模式/管理员 |
| R5 | Windows 原子重命名语义 | `os.replace` 目标已存在 | `test_team_lifecycle` 失败 | P2 | 上游 `utils/fs.py` 的原子写需确认 Windows 行为；CI/Linux 复验 |
| R6 | git-bash 无控制台缓冲 | TUI/交互式命令在 git-bash 下运行 | `test_ui/test_modes` 失败 | P3 | 交互测试在真控制台/CI 跑 |
| R7 | Celery 在 Windows 不支持 prefork | M6 服务化 | 队列 worker 崩溃 | P1 | M6 用 `--pool=solo`/threads |
| R8 | Docker Desktop 依赖 WSL2 | Win11 Home | compose / docker 沙箱不可用 | P1 | M6 前验证 WSL2；不可用则降级本地 worktree |

## 执行与控制

| # | 风险 | 触发条件 | 影响 | 等级 | 缓解 |
|---|---|---|---|---|---|
| R9 | 任务取消未终止子进程树 | 长任务被取消 | 残留进程/状态不一致 | P0 | 复用 `BackgroundTaskManager.stop_task`（`tasks/manager.py:49`）；M3 验收含"超时终止子进程" |
| R10 | 中断恢复的尾部工具损坏 | `--continue/--resume` | 恢复后消息序列非法 | P1 | 上游已有 `sanitize_conversation_messages`（`engine/messages.py`）；ForgeFlow Checkpoint 需结合 |
| R11 | 非幂等工具重试 | 网络/工具失败后盲目重试 | 重复扣款式副作用 | P0 | ForgeFlow 规则：重试前检查工具幂等性（规格 §4.5/§11） |
| R12 | 预算超限后无限循环 | max_turns 上限未达但资源耗尽 | Token/成本失控 | P1 | ForgeFlow adapter 层叠加 Token/工具数/时长预算 → `BUDGET_EXCEEDED` |
| R13 | 并行工具 Trace 顺序错乱 | `asyncio.gather` 并行工具（`engine/query.py`） | 父子 span 无法还原 | P1 | 用 `ToolExecutionStarted` 事件序列 + metadata 建 span |

## 权限与安全

| # | 风险 | 触发条件 | 影响 | 等级 | 缓解 |
|---|---|---|---|---|---|
| R14 | 子 Agent 权限提权 | Review 用子 Agent 拥有写权限 | 绕过审批/越权写 | P0 | Reviewer 用只读 AgentDefinition + 限制工具；验证 `swarm/permission_sync.py` 传播 |
| R15 | 敏感路径读取 | 模型被提示注入诱导 | 凭据泄露 | P0 | 上游 `SENSITIVE_PATH_PATTERNS`（`permissions/checker.py:18`）始终生效 |
| R16 | 命令越权 | 模型执行危险命令 | 破坏仓库/环境 | P0 | ForgeFlow 加 forbidden_commands + 结构化参数；`denied_commands` 已有通配 |
| R17 | 工作区越界 | 工具读写 Workspace 之外 | 修改任务外文件 | P0 | 上游仅有 cwd 约束；ForgeFlow 需绝对路径解析 + 越界校验（M3） |

## 事件与可观测

| # | 风险 | 触发条件 | 影响 | 等级 | 缓解 |
|---|---|---|---|---|---|
| R18 | Trace 缺敏感脱敏 | 工具输入/输出含 Token/邮箱 | 数据泄露 | P0 | ForgeFlow `TraceEvent` 持久化前脱敏（规格 §7.5/§11） |
| R19 | 事件丢失 | 追加写未持久化 | 轨迹不完整 | P2 | 追加写 + 可重放 |

## 依赖与协作

| # | 风险 | 触发条件 | 影响 | 等级 | 缓解 |
|---|---|---|---|---|---|
| R20 | 范围蔓延 | 里程碑抢跑 | 验收失控 | P1 | 一次一个里程碑；§17.4 审查第一条查越界 |
| R21 | 夸大上游贡献 | 简历/README 未区分 | 诚信问题 | P1 | `docs/UPSTREAM_MAP.md` 四栏 + 简历数字只填真实评测 |

## 待确认项（不猜测）

- `test_autopilot/test_verification.py`、`test_services/test_cron_scheduler.py` ×2：疑似环境相关，需 Linux CI 复验。
- `test_auth/test_external.py`、`test_ui/test_react_backend.py`：受真实 `ANTHROPIC_BASE_URL` 影响，清环境后复验。
- `bridge/`、`autopilot/` 模块与 ForgeFlow 的重叠程度：需进一步确认是否复用。
