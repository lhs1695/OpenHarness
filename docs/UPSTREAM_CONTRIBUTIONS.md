# UPSTREAM_CONTRIBUTIONS — 上游贡献说明

> 目的：如实、可核验地说明本项目相对 OpenHarness 复用什么、扩展什么、修改什么（对应 `PROJECT_SPEC.md` §2.2）。所有结论可用 `git diff main develop --stat` 复核。

## 1. 复用了什么（上游能力，直接使用不改源码）

| 上游能力 | 位置 | ForgeFlow 用途 |
|---|---|---|
| Agent Loop | `src/openharness/engine/query.py` `run_query` | 任务执行运行时 |
| 工具系统 | `src/openharness/tools/base.py` `BaseTool/ToolRegistry` | 工具注册/裁剪基础 |
| 技能 / 插件 / 钩子 | `skills/` `plugins/` `hooks/` | 官方扩展机制 |
| 记忆 / 会话恢复 | `memory/` `services/session_storage.py` | 基础能力（未深度使用） |
| 权限检查 | `permissions/checker.py` `SENSITIVE_PATH_PATTERNS` | 敏感路径始终拒绝 |
| 多 Agent / 隔离 | `swarm/worktree.py` `WorktreeManager` | M3 隔离执行后端（适配） |
| Provider 适配 | `api/client.py` `SupportsStreamingMessages` | 模型接入 |
| 事件流 | `engine/stream_events.py` `StreamEvent` | M7 Trace 数据源 |

> 说明：这些能力**一个源文件都未改动**。见 §3 复核命令。

## 2. 扩展了什么（新增 `src/forgeflow/`，M1–M9）

| 模块 | 说明 |
|---|---|
| `domain/` | DevelopmentTask、RepositoryPolicy、风险评分（0–100 可解释）、Approval |
| `orchestration/` | 幂等状态机、预算、Patch / Draft PR 守卫 |
| `integrations/openharness/` | 适配层（EngineLike 注入 + 事件映射 + 异常层级） |
| `execution/` | WorktreeExecutionBackend（适配上游 WorktreeManager）+ 路径边界 |
| `quality/` | 确定性质量门禁 + 只读 Reviewer |
| `trace/` | 全链路 Trace（span 树 / 脱敏 / JSONL） |
| `evaluation/` | 评测平台 + 数据回流（数据集 / 策略 / 指标 / 样本） |
| `api/` `application/` `infrastructure/` | FastAPI 服务化 + SQLAlchemy 持久化 + Celery |

## 3. 修改了什么（上游文件，仅 2 个）

### 3.1 `pyproject.toml`（5 处，均为配置）

| 改动 | 原因 |
|---|---|
| `[tool.hatch.build.targets.wheel] packages` 增加 `src/forgeflow` | 打包 ForgeFlow 包 |
| `mcp>=1.0.0` → `mcp>=1.0.0,<2.0.0` | mcp 2.x 移除 `mcp.server.fastmcp`，测试收集失败（环境已知坑） |
| dev 依赖增加 `tzdata>=2024.0` | Windows `zoneinfo` 需要 |
| pytest 增加 `online` marker + `addopts = "-m \"not online\""` | 在线测试默认跳过 |
| 新增 `service` extra（fastapi/sqlalchemy/celery/redis/psycopg2） | M6 服务化依赖，不污染默认依赖 |

### 3.2 `README.md`
- 替换为 ForgeFlow 项目 README（本仓库已作为 ForgeFlow 开发载体）；上游 README 内容保留在 git 历史与上游仓库。

### 3.3 明确声明：**0 个 `src/openharness/` 源文件被修改**

复核命令：

```bash
git diff main develop --name-only -- src/openharness   # 应输出为空
```

## 4. 可回馈上游的候选（未提交）

| 候选 | 位置 | 说明 |
|---|---|---|
| mcp 版本固定 `<2.0.0` | `pyproject.toml` | 上游依赖约束过宽，已在环境坑中复现（用户曾提 PR #341） |
| 未跟踪文件捕获 | ForgeFlow `execution/worktree.py` `collect_artifacts` | 思路：`git diff HEAD` 不显示新文件；上游 `swarm` 相关工具可参考 |
| `online` 测试标记 | pytest 配置 | 上游真实 API 测试缺乏默认跳过机制 |

## 5. 与 `docs/UPSTREAM_MAP.md` 的关系

- `UPSTREAM_MAP.md`：按能力列出的"复用/适配/扩展/修改"总表（含真实文件/行号）；
- 本文件：聚焦"到底改了什么、可回馈什么"，供求职与诚信审计使用。
