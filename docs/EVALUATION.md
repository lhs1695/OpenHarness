# EVALUATION — 评测与数据回流

> 对应 `PROJECT_SPEC.md` §7.6/§13 M8/M9。所有数字必须来自真实评测，禁止编造。

## 1. 评测平台（M8）

- **数据集**：`forgeflow.evaluation.datasets`（`EvalCase` / 版本化 `Dataset`）。种子集：`billing-smoke`（6 个 bugfix 案例，测试失败基线）+ `cart-smoke`（2 个 verify 案例，测试通过）+ `default`。
- **策略**：`EvalStrategy` 协议 + `PipelineStrategy`（确定性本地：隔离 worktree + 必需命令 + 质量门禁，无需模型）。策略名 raw / plan_gates / plan_gates_reviewer 已就位；模型驱动的差异在在线阶段（Agent 修复）验证。
- **指标**：`metrics.compute_metrics`（完成率、测试通过率、禁止路径、Token、成本、耗时、工具失败数）。
- **实验**：`ExperimentConfig`（**版本化**）+ `EvalRunner`（策略矩阵，可重复）+ `render_report`（含失败案例）。
- **运行**：`python -m forgeflow.evaluation.runner --dataset default --strategies plan_gates`。

**失败分类**（`EvalResult.failure_class`）：
- `pass`：硬门禁通过；
- `baseline`：仓库测试未通过（bug 存在、未施加修复）——**不是缺陷**，是需要 Agent 修复的信号；
- `policy`：策略门禁失败（如禁止路径被改）；
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

**对比实验方法**：同一策略分别在不带 / 带检索上下文下运行同一数据集，比较完成率与测试通过率。当前本地 `PipelineStrategy` 不消费上下文；对比实验在 Agent 驱动的在线策略上线后执行（M9→M10 端到端验证）。

## 4. 复现路径（spec §12.4）

```bash
git clone <repository>
cp .env.example .env
docker compose up --build
pytest
python -m forgeflow.evaluation.runner
```
