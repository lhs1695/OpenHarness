# ForgeFlow：研发任务交付与质量闭环平台
## 基于 OpenHarness 的深度二次开发项目说明与实施计划

> 文档用途：作为 Claude Code / Codex 的项目级规格说明、阶段计划和验收依据。  
> 当前状态：设计阶段。任何编码工作开始前，必须先完成上游源码审计并根据真实代码修正文档中的占位结构。  
> 项目名称：`ForgeFlow` 为暂定名，名称不包含具体技术栈，后续可替换。

---

## 1. 项目背景

OpenHarness 是一个通用 Agent Harness，已经提供 Agent Loop、工具系统、Skills、Plugins、Memory、Session Resume、Permissions、Hooks、多 Agent 协作和模型 Provider 适配等基础能力。

本项目不从零重写 Agent Runtime，也不把 OpenHarness 简单改名包装。项目目标是基于其通用执行能力，构建一套面向企业研发团队的业务系统：

> 研发人员提交任务后，系统根据任务等级、仓库策略和质量要求，自动完成代码分析、计划、隔离执行、测试验证、独立审查与交付；同时记录完整执行轨迹，并将轨迹用于回归评测、策略比较和经验回流。

本项目的业务对象不是“聊天用户”，而是：

- 研发负责人；
- 后端工程师；
- QA；
- 仓库维护者；
- 平台管理员。

本项目解决的业务问题是：

1. 研发任务如何被规范地交给 Agent，而不是只输入一句自然语言；
2. 不同仓库、风险等级和任务类型如何采用不同执行策略；
3. Agent 修改代码后，如何通过确定性的质量门禁判断能否交付；
4. 高风险变更如何进入人工审批；
5. 长任务如何取消、恢复和追踪；
6. 如何比较不同模型、Prompt 和执行策略的真实效果；
7. 如何把成功与失败轨迹沉淀为后续评测和经验数据。

---

## 2. 项目边界

### 2.1 本项目的核心贡献

以下内容应当作为个人项目的主要原创贡献：

1. **研发任务控制平面**
   - 任务建模；
   - 任务优先级与 SLA；
   - 仓库策略；
   - 风险评分；
   - 执行预算；
   - 审批流程；
   - 状态机。

2. **OpenHarness 适配层**
   - 将业务任务转换为 OpenHarness 可执行任务；
   - 管理 Agent 角色、工具权限和上下文；
   - 将 OpenHarness 运行事件转换为统一 Trace 事件；
   - 尽量通过扩展点接入，减少侵入式修改。

3. **隔离执行体系**
   - Local Git Worktree；
   - Docker Sandbox；
   - 统一执行后端接口；
   - 资源、路径和命令限制。

4. **质量门禁**
   - 测试；
   - Lint；
   - 类型检查；
   - 禁止路径；
   - Diff 范围；
   - 公共接口兼容；
   - Reviewer 审查；
   - 风险策略。

5. **全链路 Trace**
   - 模型调用；
   - 工具调用；
   - 命令执行；
   - 文件变化；
   - 测试结果；
   - 审批；
   - Token、成本和延迟；
   - 错误与恢复。

6. **评测和数据回流**
   - 固定任务集；
   - 多策略对比；
   - 确定性指标；
   - 可选 LLM Judge；
   - 轨迹清洗、脱敏和切分；
   - 偏好对和成功经验构造。

### 2.2 不应宣称为原创的能力

除非确实重写并有明确证据，否则以下能力属于上游 OpenHarness：

- 基础 Agent Loop；
- 通用 Tool Registry；
- 文件、Shell、搜索、MCP 等通用工具；
- Skills 与 Plugins 基础机制；
- Memory 与 Session Resume；
- Permissions 与 Hooks 基础机制；
- 多 Agent 基础能力；
- Provider 适配；
- 通用 Coding Agent 执行能力。

简历和 README 必须明确区分：

- 上游提供了什么；
- 本项目复用了什么；
- 本项目扩展了什么；
- 本项目修改了哪些上游代码以及为什么。

---

## 3. 产品定位

### 3.1 一句话定义

ForgeFlow 是一个面向研发团队的智能任务交付平台，根据任务风险、仓库策略和质量标准，驱动 Agent 完成代码分析、修改、验证和审查，并把执行过程沉淀为可回放、可评测的数据资产。

### 3.2 典型任务输入

```json
{
  "repository": "billing-service",
  "task_type": "bugfix",
  "priority": "P1",
  "title": "修复重复扣款问题",
  "description": "支付接口在客户端超时重试时可能产生第二笔扣款",
  "acceptance_criteria": [
    "相同幂等键只允许生成一笔支付记录",
    "新增并发与重试测试",
    "不得改变已有支付接口响应结构"
  ],
  "risk_tags": ["payment", "transaction", "idempotency"],
  "deadline_minutes": 240,
  "requested_by": "backend-team"
}
```

### 3.3 典型交付结果

```json
{
  "task_id": "task_123",
  "status": "COMPLETED",
  "decision": "READY_FOR_DRAFT_PR",
  "risk_score": 82,
  "changed_files": 5,
  "tests": {
    "targeted": "passed",
    "full": "passed"
  },
  "quality_gates": {
    "lint": "passed",
    "type_check": "passed",
    "forbidden_paths": "passed",
    "reviewer": "passed"
  },
  "human_approvals": 1,
  "token_usage": 43800,
  "duration_seconds": 215,
  "artifacts": [
    "plan.md",
    "patch.diff",
    "test-report.xml",
    "review-report.md",
    "trace.jsonl"
  ]
}
```

---

## 4. 业务规则

业务规则必须尽量由确定性代码执行，不应完全依赖模型判断。

### 4.1 任务优先级

| 优先级 | 含义 | 默认执行策略 |
|---|---|---|
| P0 | 线上重大故障 | 只允许调查和生成方案；禁止自动写入和提交 |
| P1 | 严重缺陷或高风险变更 | 强模型规划；人工批准计划；独立 Reviewer；禁止自动合并 |
| P2 | 普通 Bug 或中等功能 | 计划后执行；质量门禁通过后生成 Draft PR |
| P3 | 文档、测试或低风险修改 | 可快速执行；仍需基础测试和范围检查 |

### 4.2 仓库策略

每个仓库拥有独立策略，例如：

```yaml
repository: billing-service
sensitive_paths:
  - "src/payment/**"
  - "src/auth/**"
  - "migrations/**"
required_commands:
  - "pytest -q"
  - "ruff check ."
  - "mypy src"
forbidden_commands:
  - "git push --force"
  - "rm -rf"
  - "alembic upgrade head"
approval_rules:
  schema_change: ["backend_owner", "dba"]
  payment_change: ["backend_owner", "qa"]
max_changed_files: 12
max_execution_minutes: 45
max_agent_steps: 40
```

### 4.3 风险评分

第一版使用透明、可解释的规则引擎，范围为 0—100：

- 修改支付、认证、权限等敏感模块：`+20`
- 修改数据库 Schema 或 Migration：`+25`
- 修改公共 API：`+15`
- 修改文件超过 10 个：`+10`
- 缺少对应测试：`+15`
- Agent 执行中出现多次失败或回退：`+10`
- Reviewer 发现高风险问题：`+20`
- 仅文档或测试文件：可适当减分

风险等级：

- `0—29`：低风险；
- `30—59`：中风险；
- `60—79`：高风险；
- `80—100`：严重风险。

风险评分必须输出明确原因，不能只输出一个数字。

### 4.4 审批策略

- 低风险：质量门禁通过后可生成 Draft PR；
- 中风险：需要仓库维护者批准；
- 高风险：需要计划审批和最终结果审批；
- 严重风险：默认只生成方案，不执行写操作；
- 数据库迁移、删除文件、修改支付和权限逻辑必须人工审批；
- 所有审批操作必须记录操作者、时间、理由和对应 Trace。

### 4.5 预算策略

任务预算至少包含：

- 最大 Agent 步数；
- 最大模型调用次数；
- 最大工具调用次数；
- 最大 Token；
- 最大执行时间；
- 最大并发任务数。

超过预算后应进入 `BUDGET_EXCEEDED`，保存现场并等待人工决定，而不是继续无限循环。

---

## 5. 核心业务流程

```text
创建研发任务
    ↓
校验任务与仓库策略
    ↓
计算初始风险和执行预算
    ↓
准备隔离环境
    ↓
OpenHarness 分析仓库并生成计划
    ↓
是否需要计划审批？
    ├─ 是 → 等待人工审批
    └─ 否
    ↓
执行代码修改
    ↓
运行目标测试和静态检查
    ↓
失败时有限重试或重新规划
    ↓
独立 Reviewer 审查 Diff
    ↓
运行完整质量门禁
    ↓
重新计算最终风险
    ↓
是否需要最终审批？
    ├─ 是 → 等待人工审批
    └─ 否
    ↓
生成 Patch / Commit / Draft PR
    ↓
保存 Trace、报告和评测数据
    ↓
任务完成
```

### 5.1 任务状态机

```text
DRAFT
  ↓
READY
  ↓
PREPARING_ENVIRONMENT
  ↓
ANALYZING
  ↓
PLANNED
  ↓
WAITING_PLAN_APPROVAL（可选）
  ↓
EXECUTING
  ↓
VERIFYING
  ↓
REVIEWING
  ↓
WAITING_FINAL_APPROVAL（可选）
  ↓
DELIVERING
  ↓
COMPLETED
```

任意执行态可进入：

```text
PAUSED
FAILED
CANCEL_REQUESTED
CANCELLED
BUDGET_EXCEEDED
```

要求：

1. 明确定义每个状态允许的下一状态；
2. 非法状态转移必须拒绝并记录；
3. 所有状态转移具有幂等性；
4. 服务重启后可从持久化状态恢复；
5. 取消请求必须真正停止后台执行和子进程；
6. 非幂等工具执行失败后不得盲目重试。

---

## 6. 系统架构

```text
┌─────────────────────────────────────┐
│ API / CLI / 简易管理页面             │
└──────────────────┬──────────────────┘
                   ↓
┌─────────────────────────────────────┐
│ 研发任务控制平面                     │
│ Task / Policy / Risk / Budget       │
│ Approval / State Machine / SLA      │
└──────────────────┬──────────────────┘
                   ↓
┌─────────────────────────────────────┐
│ ForgeFlow Orchestrator              │
│ 业务任务 → OpenHarness 执行配置       │
│ 角色、上下文、工具、权限、Checkpoint  │
└──────────────────┬──────────────────┘
                   ↓
┌─────────────────────────────────────┐
│ OpenHarness Runtime                 │
│ Agent Loop / Tools / Skills         │
│ Plugins / Memory / Hooks / Agents   │
└──────────────────┬──────────────────┘
                   ↓
       ┌───────────┴───────────┐
       ↓                       ↓
Local Worktree             Docker Sandbox
       └───────────┬───────────┘
                   ↓
┌─────────────────────────────────────┐
│ Quality Gate & Reviewer             │
│ Tests / Lint / Types / Diff / Risk  │
└──────────────────┬──────────────────┘
                   ↓
┌─────────────────────────────────────┐
│ Trace / Evaluation / Feedback       │
│ Timeline / Metrics / Replay         │
│ Dataset / Experiment / Preference   │
└─────────────────────────────────────┘
```

### 6.1 建议技术栈

以源码审计结果和上游兼容性为准，默认建议：

- Python 3.11；
- FastAPI；
- Pydantic；
- SQLAlchemy 2.x；
- PostgreSQL；
- Redis；
- Celery；
- SSE；
- Docker Compose；
- pytest；
- Ruff；
- mypy；
- Alembic；
- GitHub Actions。

前端不是第一阶段重点：

- V1 使用 API + CLI；
- V2 增加简易 Trace 与任务管理页面；
- 不要因为 UI 延误核心闭环。

---

## 7. 模块设计

### 7.1 Task Control Plane

职责：

- 创建和校验研发任务；
- 加载仓库策略；
- 计算风险和预算；
- 驱动状态机；
- 管理审批；
- 调度执行；
- 查询任务状态；
- 处理取消和恢复。

### 7.2 OpenHarness Adapter

职责：

- 将 `DevelopmentTask` 转成 OpenHarness 输入；
- 选择 Planner、Implementer 和 Reviewer；
- 注册任务允许使用的工具；
- 设置权限、预算和上下文；
- 接收运行事件并转换为 ForgeFlow Trace；
- 对上游异常进行统一封装。

适配层必须避免业务层直接依赖大量上游内部类。

### 7.3 Execution Backend

统一接口示意：

```python
from typing import Protocol

class ExecutionBackend(Protocol):
    async def prepare(self, task_id: str, repository: str) -> str: ...
    async def execute(self, command: list[str], timeout_seconds: int) -> "ExecutionResult": ...
    async def collect_artifacts(self) -> list["Artifact"]: ...
    async def cancel(self) -> None: ...
    async def cleanup(self) -> None: ...
```

V1：

- Local Worktree。

V2：

- Docker Sandbox。

暂不实现：

- Kubernetes；
- 多云 Runner；
- Windows/Linux 全平台矩阵；
- 生产集群执行。

### 7.4 Quality Gate

质量门禁分为硬门禁和软门禁。

硬门禁失败时禁止交付：

- 目标测试失败；
- 禁止路径被修改；
- 出现未审批的 Migration；
- Secret 泄露；
- 命令越权；
- Reviewer 判定存在 P0/P1；
- 状态机或审计记录不完整。

软门禁需要人工决定：

- 完整测试耗时过长；
- Diff 超过建议大小；
- 类型检查存在历史遗留错误；
- 覆盖率小幅下降；
- Reviewer 仅发现维护性问题。

### 7.5 Trace

Trace 使用追加写事件模型，核心事件包括：

```text
task_created
task_state_changed
environment_preparing
environment_ready
plan_generated
approval_requested
approval_resolved
model_request_started
model_response_received
tool_call_started
tool_call_finished
command_started
command_finished
file_changed
test_started
test_finished
review_started
review_finished
quality_gate_finished
budget_updated
task_paused
task_resumed
task_cancelled
task_failed
task_completed
```

每条事件至少包含：

```text
event_id
task_id
run_id
agent_id
parent_event_id / span_id
event_type
timestamp
status
input_summary
output_summary
latency_ms
token_usage
estimated_cost
error_type
error_message
environment_id
metadata
```

敏感信息必须在持久化前脱敏。

### 7.6 Evaluation

评测优先使用确定性结果：

- 测试是否通过；
- Bug 是否被复现并修复；
- 静态检查是否通过；
- 是否修改禁止路径；
- 是否满足验收标准；
- 是否引入公共接口变化；
- 是否超出预算；
- 是否需要人工介入；
- 工具失败次数；
- Token、成本和耗时。

LLM Judge 只用于补充：

- 计划合理性；
- 修改是否过度；
- 代码可维护性；
- 解释是否清晰。

---

## 8. 数据模型

第一版至少包含以下实体。

### 8.1 Repository

```text
id
name
url / local_path
default_branch
policy_id
status
created_at
updated_at
```

### 8.2 RepositoryPolicy

```text
id
repository_id
sensitive_paths
forbidden_paths
required_commands
forbidden_commands
max_changed_files
max_execution_minutes
max_agent_steps
approval_rules
model_strategy
created_at
updated_at
```

### 8.3 DevelopmentTask

```text
id
repository_id
title
description
task_type
priority
acceptance_criteria
risk_tags
status
initial_risk_score
final_risk_score
budget
requested_by
created_at
updated_at
```

### 8.4 ExecutionRun

```text
id
task_id
strategy_name
model_config
environment_backend
status
started_at
finished_at
token_usage
estimated_cost
tool_call_count
error_count
checkpoint
```

### 8.5 Approval

```text
id
task_id
run_id
approval_type
status
requested_reason
requested_at
resolved_by
resolved_at
resolution_reason
```

### 8.6 TraceEvent

推荐 PostgreSQL JSONB 保存可扩展事件负载：

```text
id
task_id
run_id
event_type
occurred_at
payload
redaction_version
```

### 8.7 Artifact

```text
id
task_id
run_id
artifact_type
path
checksum
metadata
created_at
```

### 8.8 QualityGateResult

```text
id
task_id
run_id
gate_name
gate_type
status
details
created_at
```

### 8.9 EvaluationCase / Experiment

```text
EvaluationCase:
- id
- repository_fixture
- task_input
- acceptance_rules
- expected_failure
- tags

Experiment:
- id
- name
- strategy_configs
- dataset_version
- status
- aggregate_metrics
```

---

## 9. API 设计

### 9.1 任务接口

```text
POST   /api/v1/tasks
GET    /api/v1/tasks
GET    /api/v1/tasks/{task_id}
POST   /api/v1/tasks/{task_id}/start
POST   /api/v1/tasks/{task_id}/pause
POST   /api/v1/tasks/{task_id}/resume
POST   /api/v1/tasks/{task_id}/cancel
GET    /api/v1/tasks/{task_id}/events
GET    /api/v1/tasks/{task_id}/artifacts
```

`events` 使用 SSE 推送：

- 状态变化；
- Agent 输出；
- 工具执行；
- 测试结果；
- 审批请求；
- 预算消耗；
- 最终结果。

### 9.2 审批接口

```text
GET    /api/v1/approvals
POST   /api/v1/approvals/{approval_id}/approve
POST   /api/v1/approvals/{approval_id}/reject
```

审批接口必须具备幂等键。

### 9.3 仓库和策略

```text
POST   /api/v1/repositories
GET    /api/v1/repositories
GET    /api/v1/repositories/{repository_id}
PUT    /api/v1/repositories/{repository_id}/policy
```

### 9.4 评测

```text
POST   /api/v1/evaluations/experiments
GET    /api/v1/evaluations/experiments/{experiment_id}
GET    /api/v1/evaluations/experiments/{experiment_id}/report
```

---

## 10. 推荐目录结构

真实目录必须在上游审计后调整，以下是目标结构，而不是要求第一天移动所有文件。

```text
repository-root/
├── src/
│   ├── <openharness_upstream_package>/   # 上游代码，尽量少改
│   └── forgeflow/
│       ├── api/
│       │   ├── routes/
│       │   ├── schemas/
│       │   └── dependencies/
│       ├── domain/
│       │   ├── task.py
│       │   ├── policy.py
│       │   ├── risk.py
│       │   ├── approval.py
│       │   └── states.py
│       ├── application/
│       │   ├── task_service.py
│       │   ├── approval_service.py
│       │   ├── orchestration_service.py
│       │   └── event_service.py
│       ├── orchestration/
│       │   ├── state_machine.py
│       │   ├── budgets.py
│       │   ├── checkpoints.py
│       │   └── strategies.py
│       ├── integrations/
│       │   └── openharness/
│       │       ├── adapter.py
│       │       ├── event_mapper.py
│       │       ├── tool_policy.py
│       │       └── exceptions.py
│       ├── execution/
│       │   ├── base.py
│       │   ├── worktree.py
│       │   └── docker.py
│       ├── quality/
│       │   ├── gates.py
│       │   ├── reviewer.py
│       │   └── reports.py
│       ├── trace/
│       │   ├── events.py
│       │   ├── collector.py
│       │   ├── redaction.py
│       │   └── repository.py
│       ├── evaluation/
│       │   ├── datasets.py
│       │   ├── runner.py
│       │   ├── metrics.py
│       │   └── reports.py
│       └── infrastructure/
│           ├── database/
│           ├── redis/
│           ├── celery/
│           └── github/
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── e2e/
│   └── fixtures/
│       └── repositories/
├── evals/
│   ├── cases/
│   ├── datasets/
│   └── reports/
├── docs/
│   ├── PROJECT_SPEC.md
│   ├── ARCHITECTURE.md
│   ├── UPSTREAM_MAP.md
│   ├── STATE_MACHINE.md
│   ├── EVALUATION.md
│   ├── SECURITY.md
│   ├── HANDOFF.md
│   ├── PLANS.md
│   ├── adr/
│   └── learning/
├── patches/
├── docker-compose.yml
├── CLAUDE.md
├── AGENTS.md
├── UPSTREAM.md
└── README.md
```

---

## 11. 安全要求

1. 默认只允许在任务 Workspace 内读写；
2. 所有路径先解析为绝对路径，再验证是否越界；
3. Shell 命令通过结构化参数调用，禁止任意字符串拼接；
4. 默认禁用危险命令和生产凭据；
5. Docker 执行环境限制 CPU、内存、进程数和网络；
6. 不允许自动 `git push --force`；
7. V1 不允许自动合并 PR；
8. 高风险写操作必须通过 Approval；
9. Trace 持久化前进行密钥、Token、邮箱等脱敏；
10. 取消任务时必须终止子进程；
11. 重试前必须检查工具是否幂等；
12. 所有状态变更和审批均写入不可静默覆盖的审计事件；
13. Demo 只使用测试仓库和测试账号，不连接真实生产环境。

---

## 12. 非功能要求

### 12.1 可测试性

- 新增业务代码具有类型标注；
- 核心状态机、风险规则、预算规则必须单元测试；
- OpenHarness Adapter 使用接口隔离，便于 Mock；
- 执行后端具有集成测试；
- 至少提供一条端到端任务链路。

### 12.2 可观测性

每个请求和任务拥有：

- request_id；
- task_id；
- run_id；
- trace_id；
- structured logs；
- 可查询状态；
- 可导出执行轨迹。

### 12.3 可恢复性

- 服务重启后任务状态不丢失；
- 执行 Checkpoint 可恢复；
- Trace 采用追加写；
- 重复消息不造成重复状态转移；
- Celery 重试需要幂等保护。

### 12.4 可复现性

项目完成后必须支持：

```bash
git clone <repository>
cp .env.example .env
docker compose up --build
pytest
python -m forgeflow.evaluation.runner
```

具体命令以真实项目为准，但 README 必须提供一条明确路径。

---

## 13. 实施里程碑

原则：每个里程碑独立验收，一个里程碑一个分支或 Worktree；未通过当前验收，不进入下一阶段。

### M0：上游审计与基线

**目标**

- 固定上游版本和 commit；
- 安装并运行 OpenHarness；
- 运行现有测试；
- 梳理真实目录、核心调用链和扩展点；
- 明确哪些能力已存在。

**禁止**

- 修改业务代码；
- 重构上游；
- 创建 ForgeFlow 业务模块。

**产物**

```text
docs/audit/BASELINE.md
docs/audit/MODULE_MAP.md
docs/audit/CALL_FLOW.md
docs/audit/EXTENSION_POINTS.md
docs/audit/RISK_REGISTER.md
docs/UPSTREAM_MAP.md
```

**验收**

- 所有结论引用真实文件、类或函数；
- 记录实际安装、测试和运行结果；
- 明确适配方案和必须修改的上游点；
- 人工批准审计文档后才能进入 M1。

---

### M1：最小适配层与垂直链路

**目标**

打通：

```text
业务任务对象
→ OpenHarness Adapter
→ 分析一个测试仓库
→ 生成计划
→ 输出结构化结果
```

**范围**

- 暂不写代码；
- 暂不接数据库和队列；
- 使用内存状态；
- 只实现单任务、单进程。

**验收**

- 给定固定测试仓库和任务，能输出结构化计划；
- Adapter 不泄漏大量上游内部类型到业务层；
- 有 Adapter 单元测试；
- 有明确错误类型。

---

### M2：任务状态机、风险和预算

**目标**

实现：

- DevelopmentTask；
- RepositoryPolicy；
- 状态机；
- 风险评分；
- Budget；
- 非法转移保护。

**验收**

- 状态转移测试覆盖正常、失败、取消和非法路径；
- 风险评分原因可解释；
- 超预算任务停止；
- 同一命令重复执行不会重复改变状态。

---

### M3：Local Worktree 隔离执行

**目标**

实现：

- 创建临时分支和 Worktree；
- 限定 Workspace；
- 运行安全命令；
- 收集 Diff 和执行产物；
- 取消与清理。

**验收**

- 不修改原工作目录；
- 任务失败后可清理环境；
- 路径越界被拒绝；
- 超时后子进程被终止；
- 3 个固定简单任务可以在 Worktree 中完成。

---

### M4：代码修改与质量门禁

**目标**

打通完整链路：

```text
分析 → 计划 → 修改 → 目标测试 → 静态检查 → Diff 报告
```

**验收**

- 至少支持 pytest、Ruff、mypy 中实际可用的命令；
- 失败结果被结构化保存；
- 禁止路径和 Diff 大小门禁生效；
- 不允许仅通过“修改测试来掩盖 Bug”；
- 至少 5 个固定任务有可复现结果。

---

### M5：审批、Reviewer 与交付

**目标**

实现：

- 计划审批；
- 高风险操作审批；
- 独立 Reviewer；
- 最终审批；
- Patch 或 Draft PR 交付。

**验收**

- Reviewer 默认只读；
- 未批准的高风险任务不能继续；
- 审批接口幂等；
- Draft PR 只针对测试仓库；
- 所有审批进入审计 Trace。

---

### M6：服务化与持久化

**目标**

实现：

- FastAPI；
- PostgreSQL；
- Redis；
- Celery；
- SSE；
- Docker Compose。

**验收**

- API 可创建、启动、查询和取消任务；
- SSE 可实时显示状态和工具事件；
- 服务重启后任务和 Trace 不丢失；
- 重复 Celery 消息不会重复执行关键业务；
- `docker compose up` 可启动基础服务。

---

### M7：全链路 Trace

**目标**

实现：

- 统一事件模型；
- Trace Collector；
- 脱敏；
- Timeline 查询；
- Token、成本、延迟统计；
- 失败分类。

**验收**

- 一个任务可导出完整 JSONL Trace；
- 事件顺序和父子关系可还原；
- 敏感数据不出现在 Trace；
- 任务页面或 CLI 可以查看关键时间线；
- Trace 不依赖聊天文本才能理解。

---

### M8：评测平台

**目标**

建立 20—30 个固定任务组成的小型评测集，并支持多策略运行。

**初始策略**

1. 原始 OpenHarness 基线；
2. 计划 + 质量门禁；
3. 计划 + 质量门禁 + Reviewer；
4. 可选：加入历史经验检索。

**指标**

- 任务完成率；
- 测试通过率；
- 验收标准满足率；
- 修改范围正确率；
- 工具失败率；
- Token；
- 成本；
- 耗时；
- 人工介入次数。

**验收**

- 同一数据集可以重复运行；
- 实验配置被版本化；
- 报告包含失败案例，不只展示平均分；
- 不使用未经验证的漂亮数字。

---

### M9：数据回流与经验闭环

**目标**

实现：

```text
Trace
→ 脱敏
→ 清洗
→ 轨迹切分
→ 成功/失败分类
→ 偏好对或经验样本
→ Dataset Registry
```

**验收**

- 真实生成可查看的样本；
- 能说明每个样本来自哪个任务和哪个版本；
- 不声称已经完成模型后训练，除非真实实施；
- 可做一个“历史经验检索前后”的对比实验。

---

### M10：求职包装和维护

**产物**

- README；
- 架构图；
- 3 分钟演示视频；
- API 文档；
- 评测报告；
- 安全文档；
- 上游贡献说明；
- 40 个以上新增测试（根据实际范围调整，不为数字而凑）；
- GitHub Actions；
- 一页项目复盘；
- 20 个面试问题。

**最终验收**

- 从空环境能重新部署；
- 至少完成一个真实的端到端演示；
- 评测可以复现；
- 简历中的每个指标都有脚本或报告支撑；
- 清楚区分上游与个人贡献。

---

## 14. 第一版必须收敛的范围

### V1 必须有

- 单用户或单租户；
- 一个测试仓库类型；
- Local Worktree；
- 一个 Planner、一个 Implementer、一个 Reviewer；
- 任务状态机；
- 风险规则；
- 计划审批；
- 测试与静态检查；
- Trace；
- 10 个初始评测任务；
- API 或 CLI 中至少一种完整入口。

### V1 不做

- Kubernetes；
- 多云远程 Runner；
- 生产自动合并；
- 复杂前端；
- 完整多租户计费；
- 模型微调；
- vLLM 推理优化；
- 全量 SWE-bench；
- 十几个子 Agent；
- 任意网页和任意仓库的通用适配。

---

## 15. Git 与上游管理

建议本地保留两个目录：

```text
workspace/
├── OpenHarness-reference/   # 纯净只读参考
└── forgeflow/               # 个人 Fork 和二次开发
```

ForgeFlow 仓库：

```text
origin   = 个人 Fork
upstream = HKUDS/OpenHarness
```

开始开发时：

1. 记录上游 tag 和 commit；
2. 创建 `upstream-base-<version>` 标签；
3. `main` 保持可发布；
4. `develop` 用于集成；
5. 每个里程碑使用 `milestone/mX-*` 分支或 Worktree；
6. 不在开发期间频繁合并 `upstream/main`。

上游同步策略：

- 优先同步安全、兼容性和严重 Bug 修复；
- UI、聊天渠道和无关 Provider 可忽略；
- 在独立同步分支完成；
- 先跑上游测试，再跑 ForgeFlow 回归和评测；
- 更新 `UPSTREAM.md` 和 `docs/UPSTREAM_MAP.md`。

---

## 16. Claude Code / Codex 协作规则

项目根目录应维护：

- `PROJECT_SPEC.md`：本文件，产品和技术事实来源；
- `docs/PLANS.md`：当前里程碑和进度；
- `docs/HANDOFF.md`：跨会话交接；
- `CLAUDE.md`：Claude Code 的简短规则；
- `AGENTS.md`：Codex 的简短规则。

### 16.1 通用规则

1. 开始前阅读规格、架构、当前计划和交接文档；
2. 一次只做一个里程碑；
3. 先输出计划和验收测试，再修改代码；
4. 不进行无关重构；
5. 不静默修改公共接口；
6. 新行为必须有测试；
7. 先运行目标测试，再运行完整回归；
8. 不编造测试、性能或评测结果；
9. 发现规格与源码冲突时停止并报告；
10. 会话结束前更新 `HANDOFF.md`；
11. 复杂任务使用独立 Worktree；
12. 实现和审查尽量使用不同会话。

---

## 17. 可直接使用的提示词

### 17.1 M0：审计 OpenHarness

```text
你现在负责对当前 Fork 的 OpenHarness 进行源码审计。

当前阶段禁止修改任何业务源码，只允许：
1. 执行安装、启动、测试和静态检查；
2. 阅读源码；
3. 在 docs/audit/ 和 docs/learning/ 下创建文档。

请先阅读：
- README
- CHANGELOG
- pyproject.toml
- 当前仓库的开发说明

完成以下任务：

1. 记录当前 Git 分支、commit、tag、Python 要求、依赖管理、安装命令、启动命令和测试命令。
2. 实际运行可执行的安装、最小启动、测试、Lint 和类型检查，记录真实结果。
3. 分析一次完整请求从用户输入到模型调用、工具调用、权限检查、工具执行、结果返回和任务结束的调用链。
4. 找出 Agent Loop、Tool、Skill、Plugin、Memory、Session、Permission、Hook、Task、Multi-Agent、Provider 和 UI 的真实入口。
5. 对每个模块标记：
   - 直接复用；
   - 通过 Adapter 使用；
   - 需要扩展；
   - 可能必须修改；
   - 与 ForgeFlow 无关。
6. 特别检查：
   - 工作区路径隔离；
   - Shell 命令执行；
   - 并行工具调用；
   - 任务取消；
   - 中断恢复；
   - Token/步数预算；
   - 子 Agent 权限传播；
   - 事件和日志接口。
7. 输出：
   - docs/audit/BASELINE.md
   - docs/audit/MODULE_MAP.md
   - docs/audit/CALL_FLOW.md
   - docs/audit/EXTENSION_POINTS.md
   - docs/audit/RISK_REGISTER.md
   - docs/UPSTREAM_MAP.md
8. 所有结论必须引用真实文件、类、函数或配置。
9. 不确定的内容明确标记，禁止猜测。
10. 完成后只汇报审计结果，不进入编码。
```

### 17.2 架构修订

```text
请阅读：
- PROJECT_SPEC.md
- docs/audit/*
- docs/UPSTREAM_MAP.md

当前阶段仍然禁止实现业务代码。

根据真实 OpenHarness 源码，修订 ForgeFlow 架构：

1. 标出规格文档中与真实源码不一致的内容。
2. 确定最小侵入式集成方式。
3. 明确 OpenHarness Adapter 的接口。
4. 明确需要新增和需要修改的文件。
5. 定义任务状态机、风险规则、预算、审批和 Trace。
6. 把 M1—M10 拆成可独立验收的执行计划。
7. 输出：
   - docs/ARCHITECTURE.md
   - docs/STATE_MACHINE.md
   - docs/PLANS.md
   - docs/adr/0001-integration-strategy.md
8. 不要为了追求理想结构提前移动上游代码。
9. 完成后等待人工批准。
```

### 17.3 实现单个里程碑

```text
实现 docs/PLANS.md 中的 M{编号}，禁止提前实现后续里程碑。

开始前：
1. 阅读 PROJECT_SPEC.md、ARCHITECTURE.md、STATE_MACHINE.md、UPSTREAM_MAP.md 和 HANDOFF.md。
2. 检查当前 Git 状态。
3. 列出本次预计修改的文件。
4. 给出接口契约、失败场景和验收测试。
5. 识别对上游模块的影响。

实施要求：
- 先添加能够验证行为的测试。
- 只修改当前里程碑直接相关的代码。
- 不进行顺手重构。
- 不修改未声明的公共接口。
- 覆盖成功、失败、取消、超时、重试和非法输入中的适用场景。
- 使用明确异常类型和结构化日志。
- 不使用空实现、TODO 或伪造数据作为完成结果。
- 每个逻辑单元完成后运行目标测试。
- 最后运行当前可用的 Ruff、mypy、目标测试和完整回归。

结束时输出：
1. 修改文件；
2. 设计说明；
3. 实际测试命令与结果；
4. 未解决风险；
5. 人工验证步骤；
6. 推荐 Commit 信息；
7. 更新 docs/HANDOFF.md。

不要开始下一个里程碑。
```

### 17.4 独立审查

```text
你现在是独立代码审查者，只审查当前分支相对于 develop 的 Diff。
暂时不要修改代码。

重点检查：
1. 是否超出当前里程碑范围；
2. 状态机是否存在非法跳转、卡死或重复执行；
3. 取消是否真正终止后台任务和子进程；
4. 重试是否重复执行非幂等操作；
5. 数据库、Redis、队列和实际执行状态是否一致；
6. Workspace、路径、Shell、Git 和 Secret 是否安全；
7. 审批和风险规则是否可以绕过；
8. Trace 是否完整且已脱敏；
9. 测试是否只覆盖 Happy Path；
10. 是否夸大了上游之外的个人贡献。

按照 P0、P1、P2、P3 输出问题。
每个问题包含：
- 文件和位置；
- 触发条件；
- 影响；
- 修复建议；
- 建议增加的测试。

没有证据的问题不要报告。
```

### 17.5 学习和面试复盘

```text
请把刚完成的 M{编号} 作为 Python 后端和 Agent 工程面试项目教给我。

重点回答：
1. 这个里程碑解决了什么业务问题？
2. 请求、状态和数据的完整调用链是什么？
3. 哪些能力来自 OpenHarness，哪些是本项目新增？
4. 最重要的设计决策及替代方案是什么？
5. 最容易出现的 Bug 和故障是什么？
6. 测试为什么这样设计？
7. 面试官可能追问哪些问题？
8. 给我一个需要亲自完成的小改动；
9. 给我一个故障排查任务。

最后把不超过 1000 字的复习笔记写入：
docs/learning/M{编号}.md
```

---

## 18. CLAUDE.md / AGENTS.md 建议内容

两者保持短小，详细要求引用本规格，不要把整篇文档复制进去。

```markdown
# ForgeFlow Development Rules

ForgeFlow is a research-task delivery and quality-loop platform built on top of OpenHarness.

Before working:
- Read PROJECT_SPEC.md.
- Read docs/ARCHITECTURE.md, docs/PLANS.md, docs/UPSTREAM_MAP.md, and docs/HANDOFF.md.
- Work on exactly one approved milestone.

Rules:
- Preserve upstream license and attribution.
- Clearly distinguish upstream capabilities from ForgeFlow contributions.
- Prefer adapters and extensions over invasive upstream changes.
- Do not perform unrelated refactors.
- Add tests for new behavior.
- Use explicit errors, type annotations, and structured logs.
- Never fabricate test, benchmark, latency, cost, or quality results.
- Never bypass workspace, command, approval, or secret protections.
- Update docs/HANDOFF.md before ending a milestone.
```

---

## 19. 项目笔记结构

```text
docs/learning/
├── 00_project_positioning.md
├── 01_upstream_architecture.md
├── 02_agent_lifecycle.md
├── 03_context_and_memory.md
├── 04_tool_and_plugin_system.md
├── 05_permission_and_hooks.md
├── 06_task_and_recovery.md
├── 07_multi_agent.md
├── 08_openharness_adapter.md
├── 09_state_machine.md
├── 10_execution_isolation.md
├── 11_quality_gates.md
├── 12_trace_and_observability.md
├── 13_evaluation.md
└── 14_project_interview_review.md
```

每篇笔记固定回答：

1. 解决什么问题；
2. 为什么需要；
3. 核心调用链；
4. 真实代码位置；
5. 关键设计；
6. 失败场景；
7. 本项目如何使用；
8. 上游能力与个人贡献；
9. 面试问题；
10. 自己的理解。

---

## 20. 最终简历描述模板

数字必须来自真实评测。

### ForgeFlow｜研发任务交付与质量闭环平台

- 基于 OpenHarness 通用 Agent Runtime 深度二次开发面向研发团队的任务交付平台，设计任务分级、仓库策略、风险评分、执行预算、人工审批和质量门禁，实现从需求输入到 Patch / Draft PR 的完整业务闭环。
- 通过 OpenHarness Adapter 隔离业务层与上游实现，新增 Local Worktree / Docker 隔离执行、任务状态机、取消恢复和幂等控制，支持长任务中断后继续执行。
- 构建统一 Trace 事件模型，记录模型与工具调用、命令执行、文件变更、测试、审批、Token、成本和延迟，并实现轨迹脱敏、失败分类和任务回放。
- 建立包含 `[X]` 个可复现任务的回归评测集，对比原始策略、计划与质量门禁、独立 Reviewer 等方案，将任务成功率由 `[A]%` 提升至 `[B]%`，平均无效工具调用降低 `[C]%`。
- 使用 FastAPI、PostgreSQL、Redis、Celery 和 SSE 构建异步任务服务，通过 Docker Compose 与 GitHub Actions 实现一键部署、自动测试和回归评测。
- 构建执行轨迹清洗和经验样本生成管道，将成功、失败和人工修正记录转换为可追溯的评测与偏好数据。

---

## 21. 完成定义

项目只有同时满足以下条件才算完成：

- 能运行；
- 能测试；
- 能失败；
- 能恢复；
- 能取消；
- 能审批；
- 能追踪；
- 能评测；
- 能复现；
- 能明确说明上游和个人贡献；
- 能由本人脱离 AI 解释关键调用链和设计决策。

项目不以“生成了多少代码”为完成标准，而以：

> 是否构建了一个具有真实研发业务规则、可靠执行边界、可验证结果和持续评测闭环的 Agent 产品。

为最终标准。
