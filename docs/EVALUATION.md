# EVALUATION — 评测与数据回流

> 对应 `PROJECT_SPEC.md` §7.6/§13 M8/M9。所有数字必须来自真实评测，禁止编造。

## 1. 评测平台（M8）

- **数据集**：`forgeflow.evaluation.datasets`（`EvalCase` / 版本化 `Dataset`）。种子集：`billing-smoke`（6 个 bugfix 案例，测试失败基线）+ `cart-smoke`（2 个 verify 案例，测试通过）+ `default`。
- **策略**：`EvalStrategy` 协议。**本地确定性**：`PipelineStrategy`（隔离 worktree + 必需命令 + 质量门禁，无需模型）。**在线模型驱动**：`strategies_online.py`（raw / plan_gates / plan_gates_reviewer），在隔离 worktree 里让真实 Agent 修复 bug，再跑测试 / 门禁 / 只读 Reviewer；CLI 用 `--online` 启用（需 API 凭据）。
- **指标**：`metrics.compute_metrics`（完成率、测试通过率、禁止路径、Token、成本、耗时、工具失败数、**Agent 未修复数**）。
- **实验**：`ExperimentConfig`（**版本化**）+ `EvalRunner`（策略矩阵，可重复）+ `render_report`（含失败案例）。
- **运行**：`python -m forgeflow.evaluation.runner --dataset default --strategies plan_gates`。

**失败分类**（`EvalResult.failure_class`）：
- `pass`：硬门禁通过；
- `baseline`：仓库测试未通过（bug 存在、未施加修复）——**不是缺陷**，是需要 Agent 修复的信号；
- `policy`：策略门禁失败（如禁止路径被改）；
- `agent_failed`：在线策略中 Agent 跑完后测试 / 门禁 / Reviewer 仍未通过（如实记录"为何未翻转"）；
- `error`：意外异常。

## 2. 数据回流管道（M9）

```text
Task Trace (SpanEvent)
  → 脱敏（trace.redaction）
  → 切分（feedback.segment_trace：每个模型轮次一段，其余事件独立）
  → 成功/失败分类（feedback.classify_segment）
  → 偏好对（feedback.build_preference_pairs：失败样本与同源成功样本配对）
  → 经验样本（ExperienceSample，含 provenance: dataset_version/case_id/repository）
  → FeedbackRegistry（版本化注册/查询）
```

- 每个样本都可**溯源**到 task_id / run_id / provenance。
- **不声称已完成模型后训练**——样本仅用于后续评测与经验检索。

## 3. 历史经验检索（before/after 对比）

- `retrieval.retrieve_experience(query, dataset, top_k)`：关键词重叠评分。
- `retrieval.build_retrieval_context(query, dataset)`：把检索到的成功样本渲染为可注入的策略上下文。
- `retrieval.retrieval_comparison(query, dataset)`：返回检索摘要（命中数、来源）。

**对比实验方法**：同一策略分别在不带 / 带检索上下文下运行同一数据集，比较完成率与测试通过率。本地 `PipelineStrategy` 与在线策略目前都不消费上下文；带上下文的对比实验留待后续（在线策略已上线，`--online` 可跑）。

## 3.5 实测报告（2026-08-05）

> 存档：`evals/reports/2026-08-05-default-plan_gates.md`（CLI `--output` 生成，UTF-8）。

- 数据集：`default` v2026-08-05（8 案例：billing-smoke 6 + cart-smoke 2）
- 策略：`plan_gates`（本地确定性策略）

| 指标 | 值 |
|---|---|
| 完成率 | 25.00%（2/8） |
| 测试通过率 | 25.00% |
| 基线失败 | 6 |
| 策略失败 | 0 |
| 平均耗时 | ~1.1s |

- 通过：`cart-001` / `cart-002`（干净仓库 verify 案例，测试通过）；
- 基线失败：`billing-001..006`（`billing-service` fixture 含幂等 bug，`pytest` 失败 → `required_commands` 硬门禁失败）。**这是正确信号**：bug 未修复时应失败；Agent 驱动策略修复后同一批案例应翻转为通过。

### 3.5.1 在线实测（Agent 驱动三策略，2026-08-05）

> 存档：`evals/reports/2026-08-05-online-default.md`（`python -m forgeflow.evaluation.runner --strategies raw,plan_gates,plan_gates_reviewer --online`，DeepSeek 真实调用）。

| 策略 | 完成率 | 通过/总数 | Agent 未修复 | 平均Token | 平均工具失败 | 平均成本 | 平均耗时 |
|---|---|---|---|---|---|---|---|
| raw | 100.00% | 8/8 | 0 | 13,240 | 0.88 | $0.072 | 30.3s |
| plan_gates | 75.00% | 6/8 | 2 | 28,609 | 0.50 | $0.167 | 63.9s |
| plan_gates_reviewer | 75.00% | 6/8 | 2 | 27,741 | 0.75 | $0.158 | 83.3s |

- **翻转**：6 个 billing 基线失败案例中，raw 全部修复通过；plan_gates / plan_gates_reviewer 修复 4 个（billing-001/002/004/006）。`billing-003`（负金额拒绝）与 `billing-005`（索引化重构）未被门禁策略修复。
- **评审拦截**：plan_gates_reviewer 中 `billing-005` 的修复被独立 Reviewer 拒绝（verdict=request_changes）。
- **约束的代价/收益**：门禁策略完成率低于 raw（75% vs 100%）且 Token 成本更高，但平均工具失败从 raw 的 0.88 降至 plan_gates 的 0.50 次/案例（约 -43%）。数字如实记录，不夸大"门禁提升成功率"。

## 4. 复现路径（spec §12.4）

```bash
git clone <repository>
cp .env.example .env
docker compose up --build
pytest
python -m forgeflow.evaluation.runner
```
