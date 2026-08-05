# SECURITY — ForgeFlow 安全设计

> 原则（对应 `PROJECT_SPEC.md` §11）：默认只读/限界；所有路径先解析绝对路径再验证越界；命令结构化参数；敏感信息持久化前脱敏；高风险写操作必须审批。本文件逐条说明**已实现**的防护与**未覆盖**项。

## 1. 威胁模型

| 威胁 | 场景 | 防护 |
|---|---|---|
| Secret 泄露 | Agent/模型输出或命令输出含 Token/密钥/邮箱 | 脱敏（见 §2.1）+ Secret 扫描门禁（§2.4） |
| 路径越界 | 工具读写工作区之外（含符号链接指向外部） | 路径边界（§2.2） |
| 命令越权 | 模型执行危险/禁止命令 | 结构化参数 + 禁止命令（§2.3）+ 必需命令门禁 |
| 提示注入 | 恶意仓库内容诱导模型读写凭据 | 上游 `SENSITIVE_PATH_PATTERNS` 始终生效（§2.5） |
| 子 Agent 提权 | Reviewer 用写工具修改代码 | 只读 Reviewer（§2.6） |
| 越权交付 | 对非测试仓库生成 Draft PR | Draft PR 守卫（§2.7） |
| 重复执行 | 消息重投导致关键业务重复 | 幂等（状态机 / 审批 / command_id，§2.8） |

## 2. 已实现的防护

### 2.1 敏感数据脱敏
- `src/forgeflow/trace/redaction.py`：`sk-`、AWS `AKIA`、`api_key/secret/token/password` 赋值、邮箱 → `<redacted>`。
- 应用位置：`TraceCollector`（`trace/collector.py`）对所有 span 摘要/metadata 在持久化前脱敏；`TraceSampleBuilder`（`evaluation/feedback.py`）对样本内容脱敏。

### 2.2 工作区路径边界
- `src/forgeflow/execution/base.py` `resolve_workspace_path`：把路径 `resolve()` 为绝对路径后校验是否在工作区根内；`..`、外部绝对路径、**符号链接指向外部**均抛 `PathEscapeError`（spec §11.2）。
- 命令一律以 `cwd=工作区` 的结构化参数运行（`execution/worktree.py` `create_subprocess_exec`，不拼接 shell 字符串）。

### 2.3 命令与超时控制
- `execution/worktree.py`：超时用 `asyncio.wait_for` + Windows `taskkill /T /F` 终止**进程树**；处理了 taskkill 已回收进程后 `ProcessLookupError` 的边界。
- `RepositoryPolicy.forbidden_commands` 提供禁止命令表（配合权限检查）。

### 2.4 确定性质量门禁
- `quality/gates.py`：
  - `forbidden_paths_gate`（硬）：改动触及禁止路径 → 阻止交付；
  - `secret_scan_gate`（硬）：改动文件含 secret 模式；
  - `required_commands_gate`（硬）：必需命令（pytest/ruff/mypy）退出码非 0；
  - `test_masking_gate`（软）：代码变更任务只改测试 → 疑似掩盖 bug；
  - `reviewer_gate`（硬）：Reviewer 判定 P0/P1 → 阻止交付。

### 2.5 敏感路径始终拒绝
- 复用上游 `PermissionChecker`（`openharness/permissions/checker.py` `SENSITIVE_PATH_PATTERNS`）：SSH 密钥、AWS/GCP/Azure 凭据、Docker/K8s config、`.openharness/credentials.json` **任何权限模式下都拒绝**。

### 2.6 只读独立 Reviewer
- `quality/reviewer.py`：`read_only_tool_registry` 白名单仅含 `read_file/glob/grep/lsp` 等只读工具（**无 bash/write/edit**）+ PLAN 权限模式；在线真实 Review 已实测。

### 2.7 Draft PR 守卫
- `orchestration/delivery.py`：`DeliveryService.create_draft_pr` 仅允许**测试仓库**，否则抛 `DraftPrGuardError`（真实 GitHub 提交留后续）。

### 2.8 幂等与审计
- 状态机 `TaskStateMachine.apply` 对重复事件幂等 no-op（`orchestration/state_machine.py`）；
- 审批 `ApprovalManager.resolve` 幂等（`domain/approval.py`），且所有请求/解决进入审计日志（操作者/时间/理由）；
- 服务层 `command_id` 去重（`application/task_service.py`），Celery 重投递不重复执行。

## 3. 未覆盖项（V1 边界，明确声明）

- **认证/授权**：V1 单用户/单租户，API 无鉴权；多租户认证留后续。
- **Docker 沙箱**：V2 计划项（`sandbox/` 上游已存在，未启用）；本机 Docker/WSL2 未运行，`docker compose up` 需启动 Docker Desktop。
- **GitHub 提交**：Draft PR 只做守卫与准备，未实际调用 GitHub API。
- **Secret 管理**：本机 `~/.openharness/` 有真实凭据；测试/演示必须清 `ANTHROPIC_*` 环境变量，且 `.openharness/` 已 gitignore。

## 4. 运行建议

- 演示只用测试仓库与测试账号，不连接真实生产环境。
- CI 中清空 `ANTHROPIC_*` 环境变量再跑离线测试；`online` 测试显式 `-m online` 且需凭据。
