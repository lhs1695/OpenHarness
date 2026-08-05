# ForgeFlow

**研发任务交付与质量闭环平台** —— 基于 [OpenHarness](https://github.com/HKUDS/OpenHarness) 通用 Agent Harness 的深度二次开发。

研发人员提交任务后，ForgeFlow 根据任务等级、仓库策略与质量要求，驱动 Agent 完成**代码分析、计划、隔离执行、测试验证、独立审查与交付**，并把执行过程沉淀为可回放、可评测的数据资产。

> 项目状态：Milestone M0–M9 完成，M10 包装中。详细规格见 [PROJECT_SPEC.md](PROJECT_SPEC.md)。

---

## 项目定位

- **业务对象**：研发负责人、后端工程师、QA、仓库维护者、平台管理员。
- **解决的问题**：研发任务如何被规范地交给 Agent、不同仓库/风险如何采用不同策略、修改后如何通过确定性质量门禁交付、高风险变更如何人工审批、长任务如何取消/恢复/追踪、如何比较不同模型/策略的真实效果、如何把执行轨迹沉淀为评测与经验数据。
- **原则**：业务规则尽量由**确定性代码**执行；评测数字**不编造**；上游能力**复用而非重写**。

## 特性亮点

| 能力 | 说明 | 里程碑 |
|---|---|---|
| 任务控制平面 | DevelopmentTask、仓库策略、风险评分（0–100 可解释）、执行预算、审批流程、幂等状态机 | M2/M5 |
| OpenHarness 适配层 | 业务层与上游隔离，5 条无侵入接缝接入 | M1 |
| 隔离执行 | Local Git Worktree（适配上游 `WorktreeManager`），路径越界校验、超时/取消终止进程树 | M3 |
| 质量门禁 | 禁止路径 / Diff 大小 / Secret 扫描 / 必需命令 / 改测试掩盖检测，硬/软门禁 | M4 |
| 审批 / Reviewer / 交付 | 幂等审批 + 审计、只读独立 Reviewer、Patch / Draft PR（仅测试仓库） | M5 |
| 服务化 | FastAPI 任务 API + SSE 实时事件 + SQLAlchemy 持久化 + Celery 幂等消息 | M6 |
| 全链路 Trace | 父子/并行 span、脱敏、JSONL 导出、时间线、Token/成本/延迟 | M7 |
| 评测平台 | 版本化数据集、策略矩阵、确定性指标、失败案例报告、CLI | M8 |
| 数据回流 | Trace → 经验样本（provenance）+ 偏好对 + 版本化 Registry + 经验检索 | M9 |

## 架构

架构图（Mermaid）见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)（架构总览 + 任务数据流时序图）与 [docs/STATE_MACHINE.md](docs/STATE_MACHINE.md)（状态机图）。

```text
入口 (FastAPI / CLI / SSE)
  → Task Control Plane（Task · Policy · Risk · Budget · Approval · StateMachine）
  → ForgeFlow Orchestrator（TaskService · TaskOrchestrator · EventBus）
  → OpenHarness Adapter（EngineLike · event_mapper · exceptions）
  → OpenHarness Runtime（复用不改：QueryEngine · Tools · WorktreeManager）
  → 隔离执行（WorktreeExecutionBackend）
  → Quality Gate & Reviewer → Patch / Draft PR
  → Trace / Evaluation / Feedback
```

## 快速开始

```bash
# 1) 克隆（本仓库为个人 fork，含 upstream remote）
git clone <repository>
cd <repository>

# 2) 环境（Python >=3.10，开发用 3.12；pip 清华镜像）
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev,service]"

# 3) 跑 ForgeFlow 测试（默认跳过 online）
.venv/Scripts/python -m pytest tests/forgeflow -q

# 4) 评测 CLI（确定性本地策略，无需模型）
.venv/Scripts/python -m forgeflow.evaluation.runner \
  --dataset default --strategies plan_gates --output evals/reports/report.md

# 5) 服务化（Docker Compose：postgres + redis + api + worker）
#    需先启动 Docker Desktop（本机 WSL2 未运行）
docker compose up --build
```

> 环境注意：测试前请清 `ANTHROPIC_AUTH_TOKEN`/`ANTHROPIC_BASE_URL` 等真实凭据；`mcp` 需 `<2.0.0`；Windows 需 `tzdata`。

## 评测与数据回流

- 评测：确定性指标（完成率/测试通过率/禁止路径/Token/成本/耗时），报告**含失败案例**并区分失败类型（基线 / 策略 / 错误）。
- 当前 `default` 数据集实测（`plan_gates` 本地策略）：**完成率 25%（2/8）**——2 个干净仓库 verify 案例通过，6 个 `billing-service` bugfix 案例因 bug 未修复而判**基线失败**（这是正确信号，需 Agent 驱动策略修复后翻转为通过）。存档见 [evals/reports/](evals/reports/)。
- 方法学与数据回流管道见 [docs/EVALUATION.md](docs/EVALUATION.md)。

## 上游 vs 个人贡献

- **上游提供（复用不改）**：Agent Loop、工具/技能/插件、Memory、Session Resume、Permissions、Hooks、多 Agent、Provider 适配、WorktreeManager。
- **本项目扩展**：任务控制平面、适配层、隔离执行、质量门禁、审批/Reviewer、服务化、Trace、评测、数据回流。
- 详细映射见 [docs/UPSTREAM_MAP.md](docs/UPSTREAM_MAP.md) 与 [docs/UPSTREAM_CONTRIBUTIONS.md](docs/UPSTREAM_CONTRIBUTIONS.md)。

## 文档索引

| 文档 | 内容 |
|---|---|
| [PROJECT_SPEC.md](PROJECT_SPEC.md) | 项目规格、里程碑、验收标准 |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | 架构（含 Mermaid 图） |
| [docs/STATE_MACHINE.md](docs/STATE_MACHINE.md) | 状态机（含 Mermaid 图） |
| [docs/API.md](docs/API.md) | HTTP API 文档 |
| [docs/EVALUATION.md](docs/EVALUATION.md) | 评测与数据回流 |
| [docs/SECURITY.md](docs/SECURITY.md) | 安全设计 |
| [docs/UPSTREAM_CONTRIBUTIONS.md](docs/UPSTREAM_CONTRIBUTIONS.md) | 上游贡献说明 |
| [docs/DEMO.md](docs/DEMO.md) | 3 分钟演示脚本 |
| [docs/INTERVIEW.md](docs/INTERVIEW.md) | 20 个面试问题 |
| [docs/PLANS.md](docs/PLANS.md) / [docs/HANDOFF.md](docs/HANDOFF.md) | 里程碑计划 / 跨会话交接 |

## License

MIT。上游 OpenHarness 代码保留其原始许可与归属（见 `LICENSE`）。
