# DEMO — 3 分钟演示脚本

> 目的：快速展示 ForgeFlow 的核心闭环。全部命令基于真实 CLI/API，**离线可用**（除标注"在线"的步骤）。
> 建议录屏前在干净的 bash 会话中清 `ANTHROPIC_*` 环境变量。

## 场景

一个带幂等 bug 的 `billing-service` 仓库，提交一个 bugfix 任务，ForgeFlow 走评测基线；随后用 API 走一次真实任务生命周期（建 → 启 → 查 → 取消）。

## 步骤

### 0:00–0:30 — 环境就绪

```bash
cd <repo>
.venv/Scripts/python -c "import forgeflow; print(forgeflow.__version__)"   # 0.1.0
.venv/Scripts/python -m pytest tests/forgeflow -q   # 168 passed（离线）
```

屏幕亮点：ForgeFlow 包可导入；测试全绿。

### 0:30–1:15 — 评测基线

```bash
.venv/Scripts/python -m forgeflow.evaluation.runner \
  --dataset default --strategies plan_gates --output evals/reports/demo.md
```

屏幕亮点（`evals/reports/demo.md`）：

```
完成率 25.00%（2/8） · 基线失败 6 · 策略失败 0
- billing-001 [plan_gates] **基线失败（测试未通过，未施加修复）** …
```

讲解：评测平台在隔离 worktree 里跑仓库必需命令 + 确定性门禁；billing 案例因 bug 未修复而判**基线失败**（正确信号），cart 干净仓库通过（无误报）。

### 1:15–2:15 — API 任务生命周期

```bash
# 启动服务（后台）
.venv/Scripts/python -m uvicorn forgeflow.api.server:app --port 8000 &
```

```bash
# 建任务
curl -s -X POST localhost:8000/api/v1/tasks \
  -H 'Content-Type: application/json' \
  -d '{"repository":"r","title":"修复重复扣款","task_type":"bugfix"}' | python -m json.tool

# 启动（幂等键）
curl -s -X POST "localhost:8000/api/v1/tasks/<task_id>/start?command_id=start-1" | python -m json.tool

# 查询 → COMPLETED
curl -s localhost:8000/api/v1/tasks/<task_id> | python -m json.tool

# 时间线 + Trace JSONL
curl -s localhost:8000/api/v1/tasks/<task_id>/timeline | python -m json.tool
curl -s localhost:8000/api/v1/tasks/<task_id>/trace | head

# 取消（演示取消语义）
curl -s -X POST localhost:8000/api/v1/tasks/<task_id>/cancel | python -m json.tool
```

屏幕亮点：任务状态 DRAFT → … → COMPLETED；时间线按序；Trace 可导出 JSONL。

### 2:15–2:45 — 状态机（可选 Mermaid 图翻页）

展示 [docs/STATE_MACHINE.md](docs/STATE_MACHINE.md) 的 Mermaid 状态图，指出审批分支与取消/超支分支。

### 2:45–3:00 — 收尾

一句话总结：**"确定性门禁兜底 + 全链路 Trace + 可评测数据回流"，上游复用不改、个人贡献在控制平面。**

## 在线演示（可选，需凭据）

```bash
pytest -m online tests/forgeflow/integration/test_vertical_chain.py   # 真实模型规划
pytest -m online tests/forgeflow/integration/test_reviewer_online.py  # 只读 Review
```

> 警告：在线步骤会调用真实模型（消耗凭据/配额），演示前确认已配好 DeepSeek 端点并清干净非目标凭据。

## 录屏提示

- 分辨率 1920×1080，终端 120 列；用 `--output` 写报告文件避免 Windows 控制台中文乱码。
- 提前建好任务并暖场，避免演示中等待。
