# PHASE3 — ForgeFlow 下一阶段：生产化 + 数据闭环

> 定位：与 `docs/NEXT_PHASE.md`（Phase 2 加固，已全部完成）区分——本阶段从
> **业务能力**与**数据**两个支柱推进，把"验证过的平台"推向"贴近生产、越用越好"。
> 每项含 现状 / 做法（详细） / 测试 / 验收。

## 本轮执行状态（2026-08-05，分支 `feat/phase3`）

**A1/A2/B1/B2/B3/B4/B5/A4 全部完成**（A3 跨模型矩阵按用户要求保留不做）+ **全面代码审计 P0–P3 修复全部落地**（SEVERE 执行守卫、审批持久化、风险评分真实化、两阶段审批、resume 修复、统一 trace 模型、命令去重持久化等）。质量基线：**247 passed / 1 skipped / 7 deselected**，ruff clean，mypy 57 源文件 clean。

- **A1 真实评测轨迹回流**：✅ 代码+测试+在线验收完成。真实样本 `evals/data/real-feedback.json`（400 样本 / 369 success / 31 failure）。before/after：不带检索 **75%（6/8）** → 带真实反馈检索 **100%（8/8）**（单次运行，含模型随机性，如实记录）。
- **B2 预算与成本治理**：✅ `ModelDrivenTaskExecutor` 接入 `BudgetTracker`（policy+env 派生预算），超限返回 `budget_exceeded`，orchestrator 落 `BUDGET_EXCEEDED`。
- **B1 真实 GitHub PR 提交**：✅ 能力层 + **orchestrator 接线**。在线策略捕获真实 diff → `ExecutionOutcome.patch` → 任务 COMPLETED 且配 DeliveryService 时调用 `create_draft_pr`（head=forgeflow/{task_id}）。
- **A2 真实数据集**：✅ `EvalCase.metadata` + `evals/data/issues-attrs.json`（**21 个真实 attrs bug issue**，issue_url 可溯源）+ `get_dataset("issues-attrs")`。运行需补真实仓库 fixture（如实标注）。
- **A4 检索升级**：✅ 中文 CJK bigram + 可选语义打分（`[retrieval]` extra，sentence-transformers），无依赖兜底。
- **B3 多仓库**：✅ PolicyProvider 多策略 + executor `policy_resolver` + factory `FORGEFLOW_REPOSITORIES`。
- **B4 认证**：✅ `ApiKeyAuthenticator`（Bearer / X-API-Key），认证主体填 requested_by、列表按属主过滤；未配 auth 时开放（兼容既有测试）。
- **B5 command_results 落 trace**：✅ 模型 executor 填 command_results → `/timeline` 有 command_finished。
- **遗留**：A3 跨模型（保留）；A2 运行需 attrs 仓库 fixture；B1 真实远端提交需在隔离测试仓库验证。

## Phase 3 收尾清单（2026-08-05，新增 4 项，仍属 Phase 3）—— ✅ 全部完成

在审计加固基础上补最后缺口，按序实现：**交付闭环 → 风险闭环 → 真实数据跑通 → 简易 UI**。

1. ✅ **真实远端交付闭环（B1 补全）**：`GitHubPublisher`（`infrastructure/github.py`：clone → apply diff → commit → push，`GH_TOKEN` 认证；本地裸仓集成测试验证真实 git push）+ `DeliveryService` 接 `remotes`/`base_branch`/`publisher` + orchestrator `_deliver` 发布后 `gh pr create --draft`；factory 从 `FORGEFLOW_REPOSITORY_REMOTES`（name=clone_url）与 `FORGEFLOW_PR_BASE` 配置。head 分支为空时自动生成 `forgeflow/{uuid}`。**已用隔离测试仓库 `lhs1695/forgeflow-delivery-test` 端到端实测**：真实 push 分支 + 建 Draft PR（`feat: hello.py`，base main，head `forgeflow/task_*`）；修复了 `.forgeflow.patch` 临时文件泄漏进 PR 的 bug（回归测试断言发布分支不含该文件）。测试 PR/分支已清理。
2. ✅ **final_risk_score 执行后重算 + 启发式完善**：`ExecutionOutcome.changed_files` 填充（Local 从 report、Model 从 diff）→ orchestrator `_record_final_risk` 用 `_risk_inputs_from_changes` 推导丰富 RiskInputs：migration/schema 路径（+25）、公共 API 路径（+15）、docs/test-only 减分（-10）、非测试代码缺测试（+15）、agent_failures（工具失败≥2 → +10）、reviewer_blockers（P0/P1 → +20）。测试覆盖各分支。
3. ✅ **真实仓库 fixture 化跑通 issues-attrs**：浅克隆真实 python-attrs/attrs（3.3MB，git-ignored）为 fixture；**修复嵌套仓库名 materialize 丢路径 bug**（`materialize_git_repo` 保留相对路径）；**修复 src-layout 包解析**（worktree 后端检测 `src/` 目录并加入 PYTHONPATH——否则 `import attr` 解析到 site-packages 而非仓库源码，收集报错）；基线 test_command 聚焦运行时单元测试（排除需外部二进制的 mypy/pyright 集成测试）。`--dataset issues-attrs` 离线全量 **21/21 通过（100%）**，真实报告 `evals/reports/2026-08-05-issues-attrs-offline.md`——当前 attrs main 通过全部单元测试，21 个已修复 issue 全部验证通过。
4. ✅ **简易管理 UI**：`src/forgeflow/api/static/index.html`（vanilla JS）由 `GET /` 提供——任务列表/筛选/创建/详情/开始-暂停-恢复-取消/审批批准拒绝/timeline，5s 自动刷新；Playwright 实测通过。

## 给下一轮对话的提示词（复制本块给 Claude Code）

```text
你是 ForgeFlow 项目的下一位开发会话。上一位会话把 Phase 3 计划交接给你，请按下列顺序执行。

## 开始前必读
- docs/PHASE3.md（本阶段计划，含每项详细改动说明）
- docs/STATUS.md（当前状态快照）
- docs/NEXT_STEPS.md（交接提示词 + 维护清单 + 环境坑）
- PROJECT_SPEC.md（规格与 §16 规则：禁止编造数字）

## 环境
- 从 develop 派生新 worktree：git worktree add -b feat/phase3 .claude/worktrees/phase3 develop
- 装依赖：python -m pip install -e ".[dev,service]" --no-build-isolation
- 若 import 失败（editable 指向已删 worktree）：见 NEXT_STEPS §3.1 重装。
- 跑测试前清全部 ANTHROPIC_*（含 ANTHROPIC_BASE_URL）；在线评测需 DeepSeek 凭据（~/.openharness/settings.json）。

## 本轮任务（按优先级，一项完成再下一项）
1. [最高优先] A1 真实评测轨迹回流 —— ✅ 已完成（见上文"本轮执行状态"与 `docs/EVALUATION.md` §3.6）。
2. B2 预算与成本治理 —— ✅ 已完成。
3. B1 真实 GitHub PR 提交 —— ✅ 能力层已完成；**剩余**：orchestrator 审批后真正调用 `create_draft_pr` 的集成（需 diff + head 分支）。
4. 继续推进：A2 真实数据集（`EvalCase.metadata` 已加；需 20+ 真实 GitHub issue 构造 `evals/data/issues-*.json`）、A3 跨模型矩阵、A4 语义检索、B3 多仓库、B4 认证、B5 command_results 落 trace。

## 规则
- 不改 src/openharness/ 任何源文件；新能力放 src/forgeflow/。
- 新行为必须有测试；只对改动文件跑 ruff/mypy（命令见 NEXT_STEPS §3）。
- 每完成一项更新 docs/HANDOFF.md 与本文件；结束前汇报：改了什么、真实数字、遗留风险。
```

## 1. 现状基线（2026-08-05，可核验）

- **已完成**：在线评测（raw/plan_gates/plan_gates_reviewer 100/75/75%）、经验检索（75→87.5%）、
  模型驱动服务 executor（`FORGEFLOW_EXECUTOR=model`）、Docker Compose、CI、文档整理。
- **关键缺口**：在线评测无 trace（数据未回流）；`create_draft_pr` 纯本地（无真实交付）；
  `budgets` 未接入；单仓库、无认证；数据集为玩具 fixture、缺 provenance。

## 2. 支柱 A：数据闭环（让平台"越用越好"）

### A1 真实评测轨迹回流（最高优先）

**现状**：`evaluation/strategies_online.py` 的 `_collect_stream`（:308-319）只消费 StreamEvent 计数，
不记录 SpanEvent；`feedback.py` 的 `TraceSampleBuilder.build`（:155）消费 SpanEvent。

**做法（详细）**：
1. 在 `strategies_online.py` 增加可选的 `trace_collector` 参数（每策略 `run()` 透传）：策略为每个
   案例建 `TraceCollector(task_id=case.case_id, run_id=f"run_{case.case_id}")`（复用 `trace/collector.py`）。
2. 在 `_collect_stream` 的 `async for event in engine.submit_message(prompt)` 循环内，
   把每个 StreamEvent 转发给 `collector.on_stream_event(event)`（`trace/collector.py:41`）。
3. 策略结束（plan / impl / review 各阶段）后，用 `collector.events()` 拿到 SpanEvent 列表；
   经 `TraceSampleBuilder().build(task_id, run_id, events, provenance={dataset_version, case_id, repository})`
   （`feedback.py:155`）产出 `FeedbackDataset`。
4. 注册进 `FeedbackRegistry`（`evaluation/registry.py`，`register(dataset)`）。
5. runner 增加 `--feedback-output <json>`：评测结束后把所有 `FeedbackDataset` 用
   `dataset_to_json`（`feedback.py` 已有）写盘；后续运行 `--feedback-dataset <json>`（runner 已支持）
   即用真实历史重跑检索 before/after。

**测试**：离线单测——fake engine 产 StreamEvent，断言 collector 收到事件、`TraceSampleBuilder` 产出
样本、`FeedbackRegistry` 可查；在线冒烟标记 `online`（复用现有 online 测试模式）。

**验收命令**：
```bash
python -m forgeflow.evaluation.runner --dataset default --strategies plan_gates --online \
  --feedback-output evals/data/real-feedback.json
python -m forgeflow.evaluation.runner --dataset default --strategies plan_gates --online \
  --feedback-dataset evals/data/real-feedback.json --output evals/reports/real-before-after.md
```

### A2 真实数据集（来自真实 GitHub issue）

**现状**：`EvalCase`（`evaluation/datasets.py:12-20`）有 case_id/repository/title/description/task_type/
priority/acceptance_rules/tags/test_command，够用但无来源 provenance。

**做法（详细）**：
1. `EvalCase` 加 `metadata: dict[str, str] = field(default_factory=dict)`（dataclass 字段，默认空），
   用于存 `issue_url` / `issue_id` / `labels` / `author`。
2. 新增 `evals/data/issues-*.json`：从真实开源仓库（如 billing 类 / 工具类 Python 库）的 bugfix issue
   提取 title/description/acceptance_rules/tags，构造 20+ 个 EvalCase。
3. `evaluation/datasets.py` 注册新数据集（仿 `get_dataset`）；runner `--dataset <id>` 直接可用。

**测试**：单测断言 metadata 写入与回读；数据集加载可复现。

**验收**：每个 case 的 `metadata.issue_url` 可溯源到真实 issue；完成率数字可对到 issue。

### A3 跨模型评测矩阵

**现状**：只在 DeepSeek 跑（`strategies_online.py` 的 runtime 经 `OPENHARNESS_MODEL`/settings 定模型）。

**做法（详细）**：
1. runner 加 `--model <name>`：透传给 `strategies_online.default_runtime_factory` 的 `build_runtime(model=...)`
   （已支持模型注入），或经 settings profile 切换。
2. 分别配 DeepSeek / Claude / GPT 凭据（settings profile 或 env），同一数据集各跑一遍三策略。
3. 产出"模型 × 策略"完成率/成本/耗时矩阵，报告入 `evals/reports/`。

**测试**：离线单测 `--model` 透传（fake runtime 记录 model）；矩阵渲染单测。

**验收**：矩阵报告数字真实可复现（禁止编造）；跨模型差异可解释。

### A4 检索升级（语义 + 中文）

**现状**：`evaluation/retrieval.py` 按拉丁词重叠打分（`_term_set` `[a-z0-9_]+`，:11-19），中文描述靠 tags 命中。

**做法（详细）**：
1. `retrieve_experience` 增加语义打分路径：用 embedding 相似度（可选依赖 `sentence-transformers` 或
   API embedding），`pyproject.toml` 加 `[retrieval]` extra。
2. 中文分词：`jieba` 或 n-gram 切分，替代纯拉丁 `_term_set`。
3. 保留关键词打分作为 fallback（无 embedding 依赖时仍可用）；打分融合或择优。

**测试**：检索单测（中文 query 命中率提升、无依赖 fallback 不炸）。

**验收**：检索命中显著更相关；真实数据 before/after（A1 产出）对比差异更可信。

## 3. 支柱 B：业务能力（让交付"真实落地"）

### B1 真实 GitHub PR 提交

**现状**：`orchestration/delivery.py:55-66` `create_draft_pr` 只返回本地 `DraftPr`，不调 GitHub；
`DraftPrGuardError`（:32）限制测试仓库。

**做法（详细）**：
1. 复用 `openharness/autopilot/service.py:1320/1326/1344` 的 gh CLI 封装（repo view / pr list / pr edit），
   或直接在 `delivery.py` 用 subprocess 调 `gh pr create --draft --base ... --head ...`。
2. `application/factory.py` 读 `GITHUB_TOKEN` env，配置 gh 认证（`GH_TOKEN`）。
3. 放开守卫：真实仓库允许创建 Draft PR；测试仓库保持 Draft 语义不变。
4. 真实远端提交只在显式隔离环境（专用测试仓库）验证，不污染真实远端。

**测试**：mock gh CLI（fake subprocess 返回码/输出）离线测 `create_draft_pr`；隔离环境在线冒烟。

**验收**：审批通过后对真实仓库真的创建 Draft PR；守卫与 Draft 语义行为正确。

### B2 预算与成本治理

**现状**：`orchestration/budgets.py` `Budget`（:9-16）/`BudgetTracker`（:55-83）存在，但
`ModelDrivenTaskExecutor` 未用；步数/超时硬编码（`strategies_online.py:77-85`）。

**做法（详细）**：
1. `ModelDrivenTaskExecutor` 构造时建 `BudgetTracker(Budget(...))`（预算来自 policy 或 env）。
2. 每次 `strategy.run` 前/后更新 tracker：步数（`EvalResult.metadata["tool_calls"]`）、
   token（`EvalResult.token_usage`）、时长（`EvalResult.duration_ms`）。
3. 超预算 → `ExecutionOutcome(status="budget_exceeded")`（orchestrator `task_orchestrator.py:106`
   已有 `BUDGET_EXCEEDED` 分支，无需改状态机）。
4. `strategies_online.py` 的硬编码步数/超时改为从预算派生（或保留上限 + 预算兜底）。

**测试**：fake strategy 返回超预算结果 → executor 产出 `budget_exceeded`；orchestrator 落 `BUDGET_EXCEEDED`。

**验收**：在线执行受步数/Token/时长预算约束；超限任务状态正确。

### B3 多仓库支持

**现状**：`PolicyProvider` 单仓库（`application/factory.py:57`）。

**做法（详细）**：
1. `PolicyProvider` 支持 `dict[str, RepositoryPolicy]` 注册；`for_repository(name)` 查策略。
2. `application/factory.py` 从 env（`FORGEFLOW_REPOSITORIES` 逗号分隔）或注册表构建多策略。
3. 服务按任务 `StoredTask.repository` 选策略（`task_service` / orchestrator 处）。

**测试**：多仓库任务各自门禁策略生效（fake 后端单测）。

**验收**：一个服务实例可处理多个仓库、各自策略。

### B4 认证与任务属主

**现状**：无认证（`api/app.py` 直接放行）。

**做法（详细）**：
1. API 加认证依赖（复用 openharness auth 层：API-key / OAuth），`api/app.py` 加 `Depends`。
2. `CreateTaskInput.requested_by` 从认证主体填充并落库（`infrastructure/models.py` 已有字段）。
3. 任务列表按属主过滤。

**测试**：未认证请求 401；认证后创建/列表按属主过滤。

**验收**：未认证被拒；任务有属主、列表按属主过滤。

### B5 服务可观测性补全

**现状**：模型 executor 的 `command_results` 不落 trace（orchestrator `_record_commands` 只收
`ExecutionOutcome.command_results`，`ModelDrivenTaskExecutor` 未填）。

**做法（详细）**：
1. `ModelDrivenTaskExecutor` 把策略执行的关键命令/结果填入 `ExecutionOutcome.command_results`
   （可先从 `EvalResult` 或策略 metadata 映射）。
2. 复用 orchestrator `_record_commands`（`task_orchestrator.py:128-137`）落 trace，无需改编排。

**测试**：`/timeline`、`/trace` 断言含模型执行的命令与结果。

**验收**：服务路径的 timeline/trace 完整记录模型执行的命令与结果。

## 4. 排序与依赖

- **A1 数据回流**优先：它是 M9 完整闭环，且让 A3/A4 有真实数据支撑。
- **B2 预算**先于 B1 真实提交（先控成本再碰真实远端）。
- 建议顺序：**A1 → B2 → B1 → A2 → A3 → A4 → B3/B4/B5（穿插）**。

## 5. 完成定义

- 每项验收可执行、可复现；评测数字真实不编造（`PROJECT_SPEC` §16）。
- 改动后质量基线全绿：`pytest tests/forgeflow -q`、`ruff check src/forgeflow tests/forgeflow`、
  `MYPYPATH=src mypy src/forgeflow --explicit-package-bases --python-version 3.11`。
