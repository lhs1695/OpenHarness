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
| M6 服务化与持久化 | 待开始 | `milestone/m6-service` | `api/`、`infrastructure/`、compose |
| M7 全链路 Trace | 待开始 | `milestone/m7-trace` | `trace/*` |
| M8 评测平台 | 待开始 | `milestone/m8-eval` | `evaluation/*`、`evals/` |
| M9 数据回流与经验闭环 | 待开始 | `milestone/m9-feedback` | `evaluation/datasets.py` |
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

## M6 — 服务化与持久化

- `application/`、`api/`、`infrastructure/`（FastAPI + PostgreSQL + Redis + Celery + SSE + Docker Compose）。
- Windows：Celery 用 `--pool=solo`/threads；先验证 WSL2 再上 compose。
- 验收：API 可建/启/查/取消任务；SSE 实时；重启不丢；Celery 幂等；compose 可启动。

## M7 — 全链路 Trace

- `trace/events.py`、`collector.py`、`redaction.py`、`repository.py`。数据源 `StreamEvent`（`engine/stream_events.py:82`）。
- 验收：一个任务可导出完整 JSONL；父子/并行 span 可还原；敏感数据脱敏；CLI/页面可看时间线。

## M8 — 评测平台

- `evaluation/*` + `evals/`（20–30 固定任务）。初始策略：原始基线 / 计划+门禁 / 计划+门禁+Reviewer。
- 验收：同数据集可重复运行；实验配置版本化；报告含失败案例（不只平均分）。

## M9 — 数据回流与经验闭环

- `evaluation/datasets.py`、`docs/EVALUATION.md`。Trace → 脱敏 → 清洗 → 切分 → 成功/失败分类 → 样本。
- 验收：真实样本可查看、可溯源到任务与版本；可做"历史经验检索前后"对比实验；不夸大已做模型后训练。

## M10 — 包装与维护

- README、架构图、演示视频、API 文档、评测报告、安全文档、CI、40+ 测试、复盘、20 面试题。
- 验收：空环境可部署；端到端演示；评测可复现；简历指标有脚本支撑；清晰区分上游/个人贡献。

## 上游同步

- 仅里程碑间隙、且确为安全/兼容/严重 Bugfix 时：`git fetch upstream` → 独立 `sync/upstream-<sha>` 分支 → 先跑上游测试再跑 ForgeFlow 回归 → 更新 `UPSTREAM.md`/`docs/UPSTREAM_MAP.md`。
