# PLANS — ForgeFlow 里程碑计划与进度

> 工作文档：记录每个里程碑的目标、交付、验收与状态。执行规则见 `PROJECT_SPEC.md` §16/§17。
> 工作流：一个里程碑一个 Worktree（从 `develop` 派生）→ 先验收测试 → 实现 → 目标测试 → §17.4 独立审查 → merge 回 develop → 更新本文件 + `docs/HANDOFF.md`。

## 进度总览

| 里程碑 | 状态 | worktree / 分支 | 关键产出 |
|---|---|---|---|
| M0 上游审计与基线 | ✅ 完成（2026-08-05，已审查） | `milestone/m0-audit` | `docs/audit/*`、`docs/UPSTREAM_MAP.md`、`docs/adr/0001` |
| M1 最小适配层与垂直链路 | ✅ 实现完成（待独立审查） | `milestone/m1-adapter` | `src/forgeflow/integrations/openharness/*` + `domain/task.py` + 测试 |
| M2 状态机/风险/预算 | ✅ 实现完成（待独立审查） | `milestone/m2-control-plane` | `domain/{policy,risk}`、`orchestration/{state_machine,budgets}`、`errors.py` |
| M3 Local Worktree 隔离执行 | ✅ 实现完成（待独立审查） | `milestone/m3-isolation` | `execution/{base,worktree}.py` |
| M4 代码修改与质量门禁 | ✅ 实现完成（待独立审查） | `milestone/m4-quality` | `quality/{gates,reports}.py` |
| M5 审批/Reviewer/交付 | ✅ 实现完成（待独立审查） | `milestone/m5-approval` | `domain/approval.py`、`quality/reviewer.py`、`orchestration/delivery.py` |
| M6 服务化与持久化 | ✅ 实现完成（待独立审查） | `milestone/m6-service` | `api/`、`application/`、`infrastructure/`、compose |
| M7 全链路 Trace | ✅ 实现完成（待独立审查） | `milestone/m7-trace` | `trace/*` |
| M8 评测平台 | ✅ 实现完成（待独立审查） | `milestone/m8-eval` | `evaluation/*` + `evals/` 数据集 + fixture |
| M9 数据回流与经验闭环 | ✅ 实现完成（待独立审查） | `milestone/m9-feedback` | `evaluation/{feedback,registry,retrieval}.py` |
| M10 包装与维护 | 待开始 | `milestone/m10-packaging` | README、CI、40+ 测试 |

## M1 — 最小适配层与垂直链路（实现完成，待独立审查）

**目标**：打通 `DevelopmentTask → Adapter → 分析测试仓库 → 生成计划 → 结构化结果`。不接 DB/队列，内存状态，单任务单进程。

**落地文件**：
```text
src/forgeflow/__init__.py
src/forgeflow/py.typed
src/forgeflow/domain/task.py            # DevelopmentTask（pydantic，最小字段）
src/forgeflow/integrations/openharness/adapter.py      # S1 接缝：EngineLike + run_plan
src/forgeflow/integrations/openharness/event_mapper.py # StreamEvent → TraceEvent
src/forgeflow/integrations/openharness/exceptions.py   # ForgeFlowError 层级
tests/forgeflow/unit/test_adapter.py                   # 13 项（fake engine）
tests/forgeflow/unit/test_event_mapper.py
tests/forgeflow/integration/test_vertical_chain.py      # online marker
tests/forgeflow/fixtures/repositories/billing-service/  # 最小 fixture 仓库
pyrightconfig.json                                       # extraPaths=src（编辑器）
```

**对 `pyproject.toml` 的改动**（ADR 0001 已声明）：wheel 增加 `src/forgeflow`；dev 依赖固定 `mcp<2.0.0` + 加 `tzdata`；pytest 加 `online` marker + `addopts = "-m \"not online\""`。

**实际验证结果（2026-08-05）**：
- 单元测试：`pytest tests/forgeflow -q` → **13 passed, 1 deselected**（online 默认跳过）
- 垂直链路（真实模型）：`pytest -m online tests/forgeflow/integration/test_vertical_chain.py` → **1 passed**（41.6s，DeepSeek 端点，输出结构化 TaskPlan + token）
- Lint：`ruff check src/forgeflow tests/forgeflow` → **clean**
- 类型：`MYPYPATH=src mypy src/forgeflow --explicit-package-bases --python-version 3.11` → **Success**（8 文件）
- 设计要点：adapter 通过注入的 `EngineLike` 驱动引擎（接口隔离，便于 Mock）；业务层不 import `openharness.*`；`TraceEvent`/`TaskPlan` 为 ForgeFlow 类型。

**注意**：ForgeFlow 的 mypy 需用上述命令（editable 安装 + py.typed 会导致 plain `mypy src/forgeflow` 报模块重复）。

**验收**：
- 固定测试仓库 + 任务 → 输出结构化计划（目标文件、步骤、风险点、测试计划、token/时长）；
- Adapter 不泄漏上游内部类型到业务层（业务层不 import `openharness.*` 内部类）；
- Adapter 单元测试通过；明确错误类型。

**验证命令**：`pytest tests/forgeflow -q`；`ruff check src/forgeflow`；`mypy src/forgeflow --python-version 3.11`（只对 ForgeFlow 代码，不要求上游全树通过）。

## M2 — 状态机/风险/预算（实现完成，待独立审查）

**交付**：
- `domain/policy.py` — `RepositoryPolicy`（敏感/禁止路径、必需/禁止命令、文件数/时长/步数上限、审批规则）。
- `domain/risk.py` — 规则引擎：8 条可解释规则（敏感模块+20 / Migration+25 / 公共API+15 / 多文件+10 / 缺测试+15 / 多次失败+10 / Reviewer高风险+20 / 仅文档测试-10），输出 0–100 分 + 每项原因，等级 LOW/MEDIUM/HIGH/SEVERE。
- `orchestration/state_machine.py` — 表驱动状态机：`transition(state,event)` 纯函数 + `TaskStateMachine.apply`（幂等 no-op）；非法转移抛 `IllegalTransitionError`；PAUSE/RESUME、CANCEL→CANCELLED、BUDGET_EXCEEDED、FAIL 全路径。
- `orchestration/budgets.py` — `Budget`/`BudgetUsage`/`check_budget` 纯检查 + `BudgetTracker` 状态跟踪（步数/模型/工具/Token/时长）。
- **错误层级收敛**：`ForgeFlowError` 体系移到业务层 `forgeflow/errors.py`（`integrations/.../exceptions.py` 删除），adapter 与 M1 测试已更新导入。

**实际验证（2026-08-05）**：
- `pytest tests/forgeflow -q` → **52 passed, 1 deselected**（M1 13 + M2 39）
- `ruff check src/forgeflow tests/forgeflow` → clean
- `MYPYPATH=src mypy src/forgeflow --explicit-package-bases --python-version 3.11` → Success（13 文件）

**验收对应**：状态转移测试覆盖正常/审批/取消/暂停恢复/非法/幂等（`test_state_machine.py`）；风险原因可解释（`test_risk.py` 断言 reasons 含"（+20）"）；超预算检测（`test_budgets.py`）；同一命令重复执行不重复改状态（幂等 no-op 测试）。

## M3 — Local Worktree 隔离执行（实现完成，待独立审查）

**交付**：
- `execution/base.py` — `ExecutionBackend` Protocol（spec §7.3）、`ExecutionResult`（含 `timed_out`）、`Artifact`、纯函数 `resolve_workspace_path`（绝对路径解析 + 越界校验，spec §11.2）。
- `execution/worktree.py` — `WorktreeExecutionBackend`：**适配**上游 `WorktreeManager`（`swarm/worktree.py:135`）为每个任务创建 git worktree；命令用结构化参数 + `cwd=workspace`；超时/取消用 `taskkill /T /F`（Windows）终止进程树；`collect_artifacts` 产出 changed_file + diff_stat；`cleanup` 移除 worktree。
- `errors.py` 新增 `PathEscapeError`、`ExecutionNotPreparedError`。

**实际验证（2026-08-05）**：
- `pytest tests/forgeflow -q` → **61 passed, 1 skipped**（skip = Windows 无符号链接权限），M3 新增 10 项（5 路径单测 + 4 集成 + 1 清理）
- `ruff check src/forgeflow tests/forgeflow` → clean
- `MYPYPATH=src mypy src/forgeflow --explicit-package-bases --python-version 3.11` → Success（16 文件）

**验收对应**：不修改原工作目录（`test_task_change_isolated_from_original` 断言原仓库文件未变）；路径越界拒绝（`..`、绝对路径、符号链接 → `PathEscapeError`）；超时终止子进程（`time.sleep(30)` timeout=2 → `timed_out`）；3 个固定任务完成（跑测试 / 改动隔离 / 安全约束）；失败可清理（`test_cleanup_removes_worktree`）。

## M4 — 代码修改与质量门禁（实现完成，待独立审查）

**交付**：
- `quality/gates.py` — 5 个确定性纯门禁（`GateResult` 结构化输出）：
  - `forbidden_paths_gate`（**硬**：改动触及禁止路径 → FAILED）
  - `diff_size_gate`（**软**：改动文件数 > `max_changed_files`）
  - `test_masking_gate`（**软**：代码变更任务只改测试 → 疑似掩盖 Bug）
  - `secret_scan_gate`（**硬**：改动文件含 api_key/token/AWS key 等模式）
  - `required_commands_gate`（**硬**：仓库必需命令全部退出码 0）
- `quality/reports.py` — `QualityReport`（`hard_failures`/`soft_failures`/`passed`/`summarize`）+ `QualityGateRunner`（收集改动文件、读内容、跑必需命令、评估全部门禁）+ `render_report_markdown`。
- **M3 后端修复**：`collect_artifacts` 增加未跟踪文件（`git ls-files --others`）并过滤缓存目录——`git diff HEAD` 不显示新文件导致改动清单为空。

**实际验证（2026-08-05）**：
- `pytest tests/forgeflow -q` → **81 passed, 1 skipped**（M4 新增 20：13 门禁单测 + 6 固定任务集成 + 1 报告）
- `ruff check src/forgeflow tests/forgeflow` → clean
- `MYPYPATH=src mypy src/forgeflow --explicit-package-bases --python-version 3.11` → Success（19 文件）

**验收对应**：支持实际可用的必需命令（`required_commands_gate` + runner 用 `shlex.split` 结构化执行）；失败结构化保存（`GateResult.details` + `QualityReport.summarize`）；禁止路径与 Diff 大小门禁生效（硬/软）；禁止"改测试掩盖 Bug"（`test_masking_gate`）；7 个固定任务可复现（`test_quality_gates.py`）。

## M5 — 审批/Reviewer/交付（实现完成，待独立审查）

**交付**：
- `domain/approval.py` — `ApprovalManager`（幂等 resolve：重复/冲突再解决返回首次结果、不重复审计）、`approval_requirements(risk_level)`（LOW=无 / MEDIUM=FINAL / HIGH=PLAN+FINAL）、`assert_approvals_complete`（**未批准高险任务不能继续**）、审计日志（requested/approved/rejected，含操作者/时间/理由）。
- `quality/reviewer.py` — 只读 Reviewer：`read_only_tool_registry`（白名单 read_file/glob/grep/lsp 等，**无 bash/write/edit**）、`build_review_engine`（只读工具 + PLAN 权限）、`build_review_prompt`（强制 READ-ONLY）、`parse_review`（P0–P3 findings + verdict + summary）、`Reviewer`（注入引擎）。
- `quality/gates.py` + `reviewer_gate`（**硬**：Reviewer 判定 P0/P1 → 阻止交付）。
- `orchestration/delivery.py` — `make_patch`、`DeliveryService.create_draft_pr`（**Draft PR 只允许测试仓库**，非测试仓库抛 `DraftPrGuardError`；真实 GitHub 提交留 M6）。

**实际验证（2026-08-05）**：
- `pytest tests/forgeflow -q` → **106 passed, 1 skipped**（M5 新增 25）
- 在线只读 Review：`pytest -m online .../test_reviewer_online.py` → **1 passed**（19.8s，真实模型产出 ReviewReport）
- `ruff check src/forgeflow tests/forgeflow` → clean
- `MYPYPATH=src mypy src/forgeflow --explicit-package-bases --python-version 3.11` → Success（22 文件）

**验收对应**：Reviewer 默认只读（只读工具白名单 + 在线验证）；未批准高险不继续（`assert_approvals_complete` 抛 `ApprovalRequiredError`）；审批接口幂等（重复/冲突 resolve 幂等）；Draft PR 仅测试仓库（`DraftPrGuardError`）；审批进审计 Trace（audit_log 记录操作者/时间/理由）。

## M6 — 服务化与持久化（实现完成，待独立审查）

**交付**：
- `infrastructure/` — SQLAlchemy 持久化（`database.py` SQLite 默认 / PostgreSQL URL、`models.py` Task/Run/TraceEvent/Approval、`store.py` `TaskStore`）。
- `application/` — `EventBus`（异步队列，SSE 源）、`TaskOrchestrator`（驱动状态机 + 逐步持久化状态与 Trace + 审批门 + 取消/暂停/恢复 + 可注入 `TaskExecutor`）、`TaskService`（建/启/查/取消/暂停/审批 + `command_id` 幂等）、`executors.py`（`LocalTaskExecutor`：worktree + 必需命令 + 门禁）、`factory.py`（env 构建服务）。
- `api/` — FastAPI：`POST/GET /api/v1/tasks`、`GET /tasks/{id}`、`POST /tasks/{id}/start|pause|resume|cancel`、`GET /tasks/{id}/events`（SSE）、`GET /tasks/{id}/approvals`、`POST /approvals/{id}/approve|reject`、`server.py`（uvicorn 入口）。
- `infrastructure/celery_app.py` — Celery `execute_task_message`（worker 无 loop 时 `run_sync` 全量执行；重复投递经 `command_id` 幂等）。
- `docker-compose.yml`（postgres + redis + api + worker）+ `Dockerfile`。
- pyproject：新增 `service` extra（fastapi/sqlalchemy/celery/redis/psycopg2）。

**实际验证（2026-08-05）**：
- `pytest tests/forgeflow -q` → **123 passed, 1 skipped**（M6 新增 17：service/持久化恢复/Celery 幂等/API+SSE/审批流）
- `ruff check src/forgeflow tests/forgeflow` → clean
- `MYPYPATH=src mypy src/forgeflow --explicit-package-bases --python-version 3.11` → Success（37 文件）
- `docker compose -f docker-compose.yml config --quiet` → 语法有效（**本机 Docker daemon/WSL2 未运行，`up` 需启动 Docker Desktop 后验证**）

**验收对应**：API 可建/启/查/取消任务（TestClient + live uvicorn 集成测试）；SSE 实时事件（live server 测试验证 stream 收到 `task_state_changed`）；重启不丢（SQLite 持久化 + 双服务恢复测试：任务状态与 Trace 事件都在）；Celery 重复消息不重复执行（`command_id` 幂等，eager 模式测试）；compose 文件（语法校验通过，运行待 Docker 环境）。

## M7 — 全链路 Trace（实现完成，待独立审查）

**交付**：
- `trace/events.py` — `SpanEvent`（event_id/span_id/parent_event_id/status/summaries/latency/token/estimated_cost/error）+ `estimate_cost`（名义单价估算）。
- `trace/redaction.py` — `redact` / `redact_payload`（sk-/AKIA/api_key/token/邮箱等模式 → `<redacted>`）。
- `trace/collector.py` — `TraceCollector`：消费 `StreamEvent`（`engine/stream_events.py:82`）构建模型轮次 span + 工具子 span（**并行工具共享同一父 span**，按 tool_name+顺序关联）、命令 span、任务事件；`to_jsonl` / `timeline` / `summary`；持久化前脱敏。
- `trace/repository.py` — `TraceRepository`：保存/加载 SpanEvent、导出 JSONL、时间线查询（经 `TaskStore` 持久化）。
- **编排器接入**：`TaskOrchestrator` 每次运行建 Collector，喂状态事件 + 命令结果，结束经 `TraceRepository` 持久化；`ExecutionOutcome` 增加 `command_results`。
- **API**：`GET /api/v1/tasks/{id}/timeline` + `GET /api/v1/tasks/{id}/trace`（JSONL 导出）。

**实际验证（2026-08-05）**：
- `pytest tests/forgeflow -q` → **139 passed, 1 skipped**（M7 新增 16：redaction ×6 + collector ×8 + 集成 ×2）
- `ruff check src/forgeflow tests/forgeflow` → clean
- `MYPYPATH=src mypy src/forgeflow --explicit-package-bases --python-version 3.11` → Success（42 文件）

**验收对应**：一个任务可导出完整 JSONL（`export_trace_jsonl` + live API `/trace` 测试）；父子/并行 span 可还原（collector 测试断言工具 span 父=轮次 span、并行工具共享父 span）；敏感数据脱敏（`redaction` + collector 输出断言）；时间线可查（`timeline` + live API `/timeline` 测试）；Trace 含结构化事件（不依赖聊天文本）。

## M8 — 评测平台（实现完成，待独立审查）

**交付**：
- `evaluation/datasets.py` — `EvalCase`/`Dataset`（版本化）+ 种子数据集：`billing-smoke`（6 个 bugfix 案例，测试失败基线）+ `cart-smoke`（2 个 verify 案例，测试通过）+ `default`（合并）。
- `evaluation/metrics.py` — 确定性指标：完成率/测试通过率/禁止路径/Token/成本/耗时/工具失败数。
- `evaluation/experiment.py` — `ExperimentConfig`（策略 + dataset_id + **版本化**）+ `ExperimentResult`（per-strategy 指标 + 失败案例）。
- `evaluation/strategies.py` — `EvalStrategy` 协议 + `PipelineStrategy`（**确定性本地策略**：隔离 worktree + 必需命令 + 质量门禁，无需模型）；`default_strategies` 提供 raw / plan_gates / plan_gates_reviewer。
- `evaluation/runner.py` + `__main__.py` — `EvalRunner` 跑策略矩阵；**CLI** `python -m forgeflow.evaluation.runner`（spec §12.4 复现路径）。
- `evaluation/fixtures.py` — 将纯文件 fixture 物化为临时 git 仓库；新增 `cart-service` 干净 fixture。

**实际验证（2026-08-05）**：
- `pytest tests/forgeflow -q` → **152 passed, 1 skipped**（M8 新增 13：datasets/metrics/runner/策略集成）
- CLI 实测：`python -m forgeflow.evaluation.runner --dataset default --strategies plan_gates` → 报告完成率 25%（2/8：cart 通过、billing 因 bug 测试失败），含 6 个失败案例
- `ruff check src/forgeflow tests/forgeflow` → clean
- `MYPYPATH=src mypy src/forgeflow --explicit-package-bases --python-version 3.11` → Success（51 文件）

**验收对应**：同数据集可重复运行（runner 重复运行指标一致 + 策略重复一致）；实验配置版本化（`ExperimentConfig.config_version` + `dataset_version`）；报告含失败案例（`render_report` 逐条列出失败案例，不只平均分）；不夸大数字（指标全由真实 EvalResult 计算）。

## M9 — 数据回流与经验闭环（实现完成，待独立审查）

**交付**：
- `evaluation/feedback.py` — `TraceSampleBuilder`：Trace → 脱敏 → **切分**（每模型轮次一段，其余独立）→ **成功/失败分类** → 偏好对（失败样本与同源成功样本配对）→ `ExperienceSample`（含 provenance: dataset_version/case_id/repository）。
- `evaluation/registry.py` — `FeedbackRegistry`（**版本化**注册/查询/latest）。
- `evaluation/retrieval.py` — `retrieve_experience`（关键词重叠评分）+ `build_retrieval_context`（把成功样本渲染为策略上下文）+ `retrieval_comparison`（检索摘要，供 before/after 对比）。
- `docs/EVALUATION.md` — 评测与数据回流文档（失败分类、管道、对比方法、复现路径）。
- **可读性改进**（M8 报告）：`EvalResult.failure_class` = pass/baseline/policy/error；报告显示"基线失败（测试未通过，未施加修复）"与策略失败计数。

**实际验证（2026-08-05）**：
- `pytest tests/forgeflow -q` → **168 passed, 1 skipped**（M9 新增 16）
- `ruff check src/forgeflow tests/forgeflow` → clean
- `MYPYPATH=src mypy src/forgeflow --explicit-package-bases --python-version 3.11` → Success（54 文件）
- CLI 报告现显示：`plan_gates | 25% | 2/8 | 基线6 | 策略0 | ...`，billing 案例标为"基线失败"

**验收对应**：真实样本可查看（`TraceSampleBuilder` 输出含脱敏内容 + provenance）；样本可溯源到任务与版本（task_id/run_id/provenance）；可做"历史经验检索前后"对比（`retrieval_comparison` + `build_retrieval_context`，Agent 驱动策略上线后执行）；不夸大已做模型后训练（文档明确"仅用于后续评测与检索"）。

## M10 — 包装与维护

- README、架构图、演示视频、API 文档、评测报告、安全文档、CI、40+ 测试、复盘、20 面试题。
- 验收：空环境可部署；端到端演示；评测可复现；简历指标有脚本支撑；清晰区分上游/个人贡献。

## 上游同步

- 仅里程碑间隙、且确为安全/兼容/严重 Bugfix 时：`git fetch upstream` → 独立 `sync/upstream-<sha>` 分支 → 先跑上游测试再跑 ForgeFlow 回归 → 更新 `UPSTREAM.md`/`docs/UPSTREAM_MAP.md`。
