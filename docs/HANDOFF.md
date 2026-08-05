# HANDOFF — 跨会话交接

> 每次会话结束/里程碑结束更新本文件。新会话开始先读 `PROJECT_SPEC.md`、`docs/ARCHITECTURE.md`、`docs/PLANS.md`、`docs/UPSTREAM_MAP.md` 与本文件。
> 当前状态快照（给新读者，不含交接清单）见 `docs/STATUS.md`。

## 上次更新
- 2026-08-05（Phase 3 主流程完成 + **全面代码审计修复 P0–P3 全部落地**）

## Phase 3 加固（2026-08-05，审计修复 P0–P3）

对 `src/forgeflow/` 做全面代码质量审计后，按 P0–P3 修复全部发现（详见审计结论）：

- **P0-1 SEVERE 风险禁止执行写操作**：orchestrator 在 SEVERE 时只出方案、直接 FAIL 并记录 `severe_blocked` 事件；`approval_requirements(SEVERE)` 返回 []。测试：`test_severe_risk_task_is_blocked_from_execution`。
- **P0-2 审批状态持久化**：`ApprovalManager.reload` + `store.list_all_approvals` + `from_stored_approval`；factory/conftest 启动时水合——重启后审批中的任务不再卡死。测试：`test_reload_*`、`test_approvals_survive_service_restart`。
- **P0-3 任务创建风险输入真实化**：`_risk_inputs_from_spec` 从 risk_tags/task_type/acceptance_rules 推导 RiskInputs（migration/api 标签、缺测试启发），不再恒 0。测试：`test_risk_inputs_derived_from_task_not_zero` 等。
- **P1-4 resume 真正恢复执行**：`resume_task` 补调 `orchestrator.resume`（此前任务停在 READY 不执行）；重启语义（worktree 暂停时已清理）。
- **P1-5 两阶段审批流**：接上 `WAITING_FINAL_APPROVAL`——PLAN 门禁 → 执行 → 评审后 FINAL 门禁 → 交付；resume 不重复执行（execution 阶段仅一次）；交付 diff 经 `patch_ready` 事件持久化。测试：`test_medium_risk_waits_for_final_approval_*`、API 审批流测试重写。
- **P1-6/7 cancel 竞态 + 非法转移记录**：用户侧非法转移发布 `illegal_transition` 审计事件。
- **P2-8 统一 trace 模型**：删除重复的 `event_mapper.TraceEvent`，`map_stream_event` 改产出统一 `SpanEvent`。
- **P2-9 命令去重持久化**：`ProcessedCommandRecord` 表替代内存 set，重启后 Celery 重复投递仍幂等。
- **P2-10/11/12**：trace 批量单 commit；`create_task` 重复 id 抛 `TaskAlreadyExistsError`；risk/gates 路径匹配合并为 `domain/policy.path_matches`。
- **P3-13..16**：EventBus 空订阅集清理；worktree returncode 显式 + cleanup 杀运行中子进程；脱敏/secret 值类改 ASCII；`update_task` 显式刷新 `updated_at`。

质量基线：**247 passed / 1 skipped / 7 deselected**，ruff clean，mypy 57 源文件 clean。

## Phase 3 进行中（2026-08-05）—— 主流程已完成（除 A3 跨模型）

按 `docs/PHASE3.md` 优先级推进；本分支 `feat/phase3`（基于 develop）。**A1/B2/B1/A2(基础+真实数据集)/A4/B3/B4/B5 全部完成**（A3 跨模型矩阵按用户要求保留不做）。

- **B4 认证与任务属主**：✅ `api/auth.py` `ApiKeyAuthenticator`（`Authorization: Bearer` / `X-API-Key`，key→subject 映射）；`build_app(service, auth=None)`——未配 auth 时保持开放（向后兼容既有测试），配 auth 时任务端点 401 拒未认证、`requested_by` 由认证主体填充、列表按属主过滤；factory `api_key_auth_from_env`（`FORGEFLOW_API_KEYS`="key:subject,..." 或 `FORGEFLOW_API_KEY`）。测试 `test_api_auth.py`。
- **B3 多仓库支持**：✅ `PolicyProvider` 支持多策略注册 + `for_repository`；executor 加 `policy_resolver` 按任务仓库解析策略（Local 直接换 policy；Model 重建 PlanGatesStrategy）；factory 从 `FORGEFLOW_REPOSITORIES` 构建多策略。测试 `test_multi_repo.py`（per-repo 门禁命令各自生效）。
- **B5 服务可观测性补全**：✅ `command_results_from_eval` 把策略聚合的 gate/test 结果映射为 `ExecutionResult`；`ModelDrivenTaskExecutor` 填入 `outcome.command_results` → orchestrator `_record_commands` 落 trace → `/timeline` 出现 `command_finished`。测试含服务级 trace 断言。
- **A2 真实数据集**：✅ `EvalCase.metadata`（基础件）+ `evals/data/issues-attrs.json`（**21 个真实 python-attrs/attrs bug issue**，title/description/acceptance_rules 从 issue 正文诚实推导，metadata 含真实 issue_url/issue_id/labels/author）+ `datasets.py` `load_issues_dataset`/`get_dataset("issues-attrs")`。**如实标注**：运行需对应仓库 fixture（真实 attrs 仓库未 fixture 化，故"完成率可对到 issue"需补 fixture 后才可跑）。
- **A4 检索升级（语义 + 中文）**：✅ `_tokenize` 增加 CJK bigram（中文查询命中中文内容）；可选语义打分（`sentence-transformers`，pyproject 新增 `[retrieval]` extra）——命中 top-k 候选后按 embedding 重排；无依赖时关键词打分兜底。测试 `test_retrieval.py`（中文命中 + 无依赖 fallback）。
- **B1 orchestrator 接线**：✅ 在线策略在 cleanup 前捕获真实 `git diff HEAD` 到 `EvalResult.metadata["diff"]`；executor 经 `patch_from_eval` 构建 `Patch` 进 `ExecutionOutcome.patch`；`TaskOrchestrator` 接受可选 `delivery`，任务 COMPLETED 且带 patch 时调用 `create_draft_pr`（`head=forgeflow/{task_id}`），失败记 trace 事件不崩管道；factory 接线 `delivery_service_from_env`。测试：策略 diff 捕获、executor patch、交付调用/跳过。



按 `docs/PHASE3.md` 优先级推进；本分支 `feat/phase3`（基于 develop）。

- **A1 真实评测轨迹回流**：✅ 代码+测试完成，**在线验收已跑出真实样本**（`evals/data/real-feedback.json`，400 样本 / 369 success / 31 failure，8 case 全覆盖，provenance 含 dataset_version/case_id/repository/strategy）。在线策略（`evaluation/strategies_online.py`）新增可选 `feedback_registry` / `dataset_version`；每个 case 建 `TraceCollector`，经 `_TraceForwardingEngine` 把 plan/fix/review 各阶段 StreamEvent 转发入 collector，结束用 `TraceSampleBuilder.build` 产出 `FeedbackDataset` 注册进 `FeedbackRegistry`。runner 新增 `--feedback-output <json>`：在线运行结束后 `merge_datasets` 合并所有注册数据集写盘（可直接被 `--feedback-dataset` 回读做 before/after）。测试：`test_online_trace_feedback.py` + online 冒烟（`test_strategies_online_live.py`）。
  - **第一批真实在线结果**（`evals/reports/2026-08-05-online-a1-feedback.md`）：plan_gates 完成率 **75%（6/8）**；失败 billing-003（required_commands 硬门禁未过）+ billing-004（**900s 墙钟超时**——真实随机性，与上一轮该 case 被修复不同）。
  - **before/after 二次运行**（`evals/reports/2026-08-05-online-a1-before-after.md`）：带真实反馈检索 **100%（8/8）** vs 不带 **75%**。8 case 检索均命中真实成功样本。**如实标注**：单次运行含模型随机性（before 的 billing-004 超时为随机抖动），不可断言检索必然提升；但真实反馈已可回流并被检索消费——A1 闭环成立。
  - 与计划的偏差（有意）：collector 的 `task_id` 用 `{case_id}-{strategy}-{run_token}` 而非 `case_id`，避免多策略同秒注册同一数据集 id 覆盖丢数据；`--feedback-output` 写**合并后的单一** FeedbackDataset（而非 N 个文件），保证 `dataset_from_json` 往返可读、检索直接可消费。
- **B2 预算与成本治理**：✅ `ModelDrivenTaskExecutor` 接入 `BudgetTracker`（`application/executors.py`）；预算由 `budget_from_policy_and_env` 派生（policy `max_agent_steps`/`max_execution_minutes` + `FORGEFLOW_BUDGET_MAX_*` env 覆盖）；`execute` 记录 steps/tokens/duration，超限返回 `ExecutionOutcome(status="budget_exceeded")`，orchestrator 已落 `BUDGET_EXCEEDED` 状态（无需改状态机）。测试：`test_model_executor.py` 新增超步/超 token/策略派生/服务落库 BUDGET_EXCEEDED。
- **B1 真实 GitHub PR 提交**：✅ `infrastructure/github.py` 新增 `GitHubPrClient`（gh CLI 封装：repo view / pr create --draft，`GH_TOKEN` 注入，runner 可注入以便测试）；`DeliveryService` 放开守卫——真实仓库配置 GitHub client 时走真远程 Draft PR（返回 url/number），测试仓库保持本地 Draft 语义，无 GitHub client 时真实仓库仍被 `DraftPrGuardError` 拒绝。`application/factory.py` 读 `GITHUB_TOKEN`（`github_client_from_env` / `delivery_service_from_env`，`FORGEFLOW_TEST_REPOSITORIES`）。测试：`test_github_delivery.py`（fake runner 验证 gh 参数/环境/错误，守卫与 Draft 语义）。**未做**：orchestrator/交付链路真正在审批后调用 `create_draft_pr`（需 diff+head 分支，留待后续集成）。
- **A2 基础件**：✅ `EvalCase` 增加 `metadata: dict[str, str]` 字段（默认空，用于 issue_url/author 等 provenance）；`test_eval_datasets.py` 覆盖读写。

## 当前状态

- **里程碑**：**M0–M10 全部 ✅（已 merge 回 develop 并推送 origin）**。ForgeFlow 主体开发完成。
- **在线评测**：✅ 已实现 `raw` / `plan_gates` / `plan_gates_reviewer` 三个 Agent 驱动在线策略（`evaluation/strategies_online.py`，CLI `--online`），跑出真实三策略对比（`evals/reports/2026-08-05-online-default.md`）。
- **经验检索 before/after（P0-2）**：✅ 已实现 `EvalStrategy.run` 可选 `context` + runner `--feedback-dataset` 注入 + `feedback.py` JSON 序列化 + 种子集 `evals/data/seed-experience.json`；实测 plan_gates 75% → 87.5%（`evals/reports/2026-08-05-online-default-retrieval.md`）。
- **服务层模型驱动 executor（P1-1）**：✅ 已实现 `ModelDrivenTaskExecutor`（`application/executors.py`，复用在线 `PlanGatesStrategy`，`StoredTask→EvalCase→ExecutionOutcome`）+ `factory.py` `FORGEFLOW_EXECUTOR=model` 开关；服务级测试落库 COMPLETED + 在线冒烟通过。
- **Docker Compose 端到端验证（P0-1）**：✅ `docker compose up -d` 四服务 + API 全生命周期 COMPLETED。修了 Dockerfile（清华 pip 镜像、COPY frontend、装 git、装 pytest）与 compose（alpine 镜像、可写 git 化 fixture 挂载、`FORGEFLOW_REQUIRED_COMMANDS`）。api 镜像 **597MB**。
- **服务路径质量门禁（P0-1 遗留）**：✅ `FORGEFLOW_REQUIRED_COMMANDS` env 注入 policy，服务路径真跑仓库测试；容器内 billing 任务 FAILED 验证通过。
- **标签推送（P1-2）**：✅ `upstream-base-0.1.9` 已推送 origin。
- **上游同步（P2-1）**：✅ 已执行——`upstream/main` 相对 `develop` 0 新提交，无需同步。
- **复盘/简历/路线图/状态**：✅ `docs/RETROSPECTIVE.md`、`docs/RESUME.md`、`docs/NEXT_PHASE.md`、`docs/STATUS.md` 已就位。
- **分支/worktree**：
  - `main` @ `af94671`（可发布，含 setup 文档）
  - `develop`（含 M0–M10 + 本轮在线评测代码与文档，已推送 origin）
  - 当前会话在 `D:\workspace\OpenHarness-dev`（develop）；历史 worktree `vigilant-elgamal-93ae55` / `gifted-black-a912be` 为旧基线。
  - 上游基础标签 `upstream-base-0.1.9` @ `9b2efd7`（未推送，可选推送）
- **M0–M10 产物总览**：`src/forgeflow/`（domain/orchestration/integrations/execution/quality/trace/evaluation/api/application/infrastructure，~54 个源文件，mypy clean）、168 个 ForgeFlow 测试、`README.md` + `docs/*`（架构/状态机含 Mermaid、API、SECURITY、UPSTREAM_CONTRIBUTIONS、DEMO、INTERVIEW、EVALUATION 实测报告）、`evals/reports/`、`.github/workflows/ci.yml`、`docker-compose.yml`。
- **关键事实（可核验）**：`src/openharness/` **0 个源文件被修改**；上游文件改动仅 `pyproject.toml`（wheel/mcp<2.0.0/tzdata/marker/service extra）与 `README.md`（替换为 ForgeFlow 版）。
- **错误层级位置**：`forgeflow/errors.py`（原 `integrations/openharness/exceptions.py` 已删除）。
- **服务依赖**：pyproject 新增 `service` extra（fastapi/sqlalchemy/celery/redis/psycopg2）；venv 已装。

## 关键事实（新会话必须知道）

- 本机 `~/.openharness/` 有真实凭据；跑测试清全部 `ANTHROPIC_*` 环境变量（含 `ANTHROPIC_BASE_URL`）。
- 上游全树 ruff/mypy 本就不通过（ruff 709 / mypy 1188）；质量门禁只对改动文件做检查。
- 环境：Windows + git-bash；pip 清华镜像；`mcp<2.0.0`；`tzdata`；根 `.venv` 为 Python 3.12.10（mypy 需显式 `--python-version 3.11`）。
- 集成策略：adapt-and-extend，5 条接缝（ADR 0001）。不改上游核心。
- **ForgeFlow 代码质量命令**：
  - 单测：`pytest tests/forgeflow -q`（默认跳过 online）
  - 在线垂直链路：`pytest -m online tests/forgeflow/integration/test_vertical_chain.py`（需真实 API 凭据）
  - lint：`ruff check src/forgeflow tests/forgeflow`
  - mypy：`MYPYPATH=src mypy src/forgeflow --explicit-package-bases --python-version 3.11`（**必须带这些参数**：editable 安装 + py.typed 使 plain 命令报模块重复）
  - 测试文件 basename 不能与上游 `tests/` 冲突（曾与 `test_sandbox/test_adapter.py` 冲突，已改名 `test_plan_adapter.py`）。
  - 换 worktree 后需重装 editable：`python -m pip install -e ".[dev]" --no-build-isolation`（venv 需已装 `hatchling`、`editables`；build isolation 在代理/镜像下偶发失败）。

## 下一步（暂缓项，项目主体已完成）

1. **Agent 驱动在线评测**：✅ 已完成。三策略对比 `evals/reports/2026-08-05-online-default.md`：raw **100%（8/8）**、plan_gates **75%（6/8）**、plan_gates_reviewer **75%（6/8）**；基线 25% → 在线 75–100%，门禁策略平均工具失败较 raw 降约 43%。在线策略代码见 `evaluation/strategies_online.py`，运行 `--strategies raw,plan_gates,plan_gates_reviewer --online`。
2. **补写暂缓文档**：✅ `docs/RETROSPECTIVE.md`（一页复盘）与 `docs/RESUME.md`（PROJECT_SPEC §20 模板填真实数字）已补齐。
3. **经验检索 before/after（P0-2）**：✅ 已完成。plan_gates 75% → 87.5%（`evals/reports/2026-08-05-online-default-retrieval.md`）；机制见 `docs/NEXT_PHASE.md` P0-2。
4. **服务层模型驱动 executor（P1-1）**：✅ 已完成。`FORGEFLOW_EXECUTOR=model` 即可用真实 Agent 执行服务任务；见 `docs/NEXT_PHASE.md` P1-1。
5. **CI 在线评测 job**：✅ 已实现（`workflow_dispatch` 手动触发；需 GitHub Secret `DEEPSEEK_API_KEY`，无 secret 自动跳过）。定位为便利按钮，非门禁。
6. **待做/持续**：质量基线维护（P2-3）；可选 CI 定时在线评测、真实 trace 回流反馈管道。当前状态总览见 `docs/STATUS.md`。

## 待办/风险

- 未推送任何内容到 `upstream`（HKUDS/OpenHarness）。所有推送仅到 `origin`（自己的 fork）。
- `upstream-base-0.1.9` 标签尚未推送。
- **Docker daemon/WSL2 本机未运行**：`docker compose up` 需先启动 Docker Desktop；compose 文件已通过 `config --quiet` 语法校验。
- `test_autopilot`、`test_cron_scheduler` 等失败待 Linux CI 复验（见 BASELINE §4）。
- 在线评测数字与 DeepSeek 端点/模型相关：换模型需重跑才可复现；在线策略已加**墙钟超时**（规划 10min / 实现 15min / 评审 5min）避免挂起。
- 已知真实结果：门禁策略完成率（75%）低于无约束 raw（100%）——如实记录，不夸大。
- 测试文件 basename 不能与上游 `tests/` 冲突（曾踩 `test_adapter.py`/`test_registry.py`，本轮 `test_strategies_online.py` 自身 unit/integration 同名冲突，integration 已改名 `test_strategies_online_live.py`）。
- **venv 陷阱**：换 worktree 后若 editable 指向已删除的旧 worktree，需 `pip uninstall openharness-ai` + 清理 `site-packages/openharness` + 重装 `pip install -e ".[dev,service]" --no-build-isolation`。
