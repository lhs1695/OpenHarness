# PHASE3 — ForgeFlow 下一阶段：生产化 + 数据闭环

> 定位：与 `docs/NEXT_PHASE.md`（Phase 2 加固，已全部完成）区分——本阶段从
> **业务能力**与**数据**两个支柱推进，把"验证过的平台"推向"贴近生产、越用越好"。
> 每项含 现状 / 做法 / 验收 / 涉及文件。

## 1. 现状基线（2026-08-05，可核验）

- **已完成**：在线评测（raw/plan_gates/plan_gates_reviewer 100/75/75%）、经验检索（75→87.5%）、
  模型驱动服务 executor（`FORGEFLOW_EXECUTOR=model`）、Docker Compose、CI、文档整理。
- **关键缺口**：在线评测无 trace（数据未回流）；`create_draft_pr` 纯本地（无真实交付）；
  `budgets` 未接入；单仓库、无认证；数据集为玩具 fixture、缺 provenance。

## 2. 支柱 A：数据闭环（让平台"越用越好"）

### A1 真实评测轨迹回流（最高优先）
- **现状**：`evaluation/strategies_online.py` 的 `_collect_stream`（:308-319）只消费 StreamEvent 计数，不记录 SpanEvent；`feedback.py` 的 `TraceSampleBuilder.build`（:155）消费 SpanEvent。
- **做法**：在 `_collect_stream` 循环内把每个 StreamEvent 转发给 `TraceCollector.on_stream_event`（`trace/collector.py:41`），收集一次在线评测的 SpanEvent → `TraceSampleBuilder.build` → 注册进 `FeedbackRegistry`；检索改用真实历史样本重跑 before/after。
- **验收**：一次在线评测后 `FeedbackRegistry` 有真实 success/failure 样本；`evals/reports/` 出现"真实数据 before/after"报告。
- **涉及**：`evaluation/strategies_online.py`、`evaluation/feedback.py`（复用）、`trace/collector.py`（复用）、`evaluation/registry.py`（复用）、runner 增加"是否回流"开关。

### A2 真实数据集（来自真实 GitHub issue）
- **现状**：`EvalCase`（`evaluation/datasets.py:12-20`）有 case_id/repository/title/description/task_type/priority/acceptance_rules/tags/test_command，够用但无来源 provenance。
- **做法**：给 `EvalCase` 加 `metadata`（issue_url/id/labels/author）；从真实开源仓库 issue 构造 20+ 个 bugfix 案例；跑通 CLI。
- **验收**：数据集每案例可溯源到真实 issue；完成率数字可对到 issue。
- **涉及**：`evaluation/datasets.py`、`evals/data/` 新数据集 JSON、runner 加载。

### A3 跨模型评测矩阵
- **现状**：只在 DeepSeek 跑。
- **做法**：CLI 加 `--model`（或经 settings profile），同一数据集跑 DeepSeek/Claude/GPT，产出"模型 × 策略"完成率/成本矩阵。
- **验收**：`evals/reports/` 有跨模型矩阵报告（数字真实，禁止编造）。
- **涉及**：`evaluation/runner.py`、`evaluation/strategies_online.py`（模型可注入，已支持）。

### A4 检索升级（语义 + 中文）
- **现状**：`evaluation/retrieval.py` 按拉丁词重叠打分（`_term_set` `[a-z0-9_]+`），中文描述靠 tags 命中。
- **做法**：加语义检索（embedding 相似度，可选依赖 `sentence-transformers` 或 API embedding）与中文分词，替换/增强关键词打分。
- **验收**：检索命中显著更相关；before/after 对比差异更可信。
- **涉及**：`evaluation/retrieval.py`、`pyproject.toml`（可选依赖）、检索测试。

## 3. 支柱 B：业务能力（让交付"真实落地"）

### B1 真实 GitHub PR 提交
- **现状**：`orchestration/delivery.py:55-66` `create_draft_pr` 只返回本地 `DraftPr`，不调 GitHub；`DraftPrGuardError`（:32）限制测试仓库。
- **做法**：复用 `openharness/autopilot/service.py:1320/1326/1344` 的 gh CLI 封装（repo view/pr list/pr edit）；配置 `GITHUB_TOKEN`；放开守卫为真实仓库（仍对测试仓库保持 Draft 语义）。
- **验收**：审批通过后对真实仓库真的创建 Draft PR（隔离环境验证，不污染真实远端）。
- **涉及**：`orchestration/delivery.py`、`application/factory.py`（token 配置）、`pyproject.toml`。

### B2 预算与成本治理
- **现状**：`orchestration/budgets.py` `Budget`（:9-16）/`BudgetTracker`（:55-83）存在，但 `ModelDrivenTaskExecutor` 未用；步数/超时硬编码（`strategies_online.py:77-85`）。
- **做法**：executor/策略接 `BudgetTracker`，超预算返回 `budget_exceeded`（orchestrator `task_orchestrator.py:106` 已有分支）。
- **验收**：在线执行受步数/Token/时长预算约束；超限任务状态正确（BUDGET_EXCEEDED）。
- **涉及**：`application/executors.py`、`evaluation/strategies_online.py`、`orchestration/budgets.py`（复用）。

### B3 多仓库支持
- **现状**：`PolicyProvider` 单仓库（`application/factory.py:57`）。
- **做法**：多仓库策略注册；服务按任务 `repository` 选策略。
- **验收**：一个服务实例可处理多个仓库、各自门禁策略。
- **涉及**：`application/task_service.py`、`application/factory.py`、`domain/policy.py`（复用）。

### B4 认证与任务属主
- **现状**：无认证。
- **做法**：API-key / OAuth（复用 openharness auth 层），任务按用户隔离。
- **验收**：未认证请求被拒；任务有属主、列表按属主过滤。
- **涉及**：`api/app.py`、`application/task_service.py`、`infrastructure/models.py`。

### B5 服务可观测性补全
- **现状**：模型 executor 的 `command_results` 不落 trace。
- **做法**：`ModelDrivenTaskExecutor` 把执行结果输出到 `TraceCollector`（orchestrator `_record_commands` 路径）。
- **验收**：`/timeline`、`/trace` 完整记录模型执行的命令与结果。
- **涉及**：`application/executors.py`、`application/task_orchestrator.py`（复用）。

## 4. 排序与依赖

- **A1 数据回流**优先：它是 M9 完整闭环，且让 A3/A4 有真实数据支撑。
- **B2 预算**先于 B1 真实提交（先控成本再碰真实远端）。
- 建议顺序：**A1 → B2 → B1 → A2 → A3 → A4 → B3/B4/B5（穿插）**。

## 5. 完成定义

- 每项验收可执行、可复现；评测数字真实不编造（`PROJECT_SPEC` §16）；改动后质量基线（`pytest tests/forgeflow` + ruff + mypy）保持全绿。
