# NEXT_PHASE — ForgeFlow 下一阶段计划（Phase 2：加固与扩展）

> M0–M10 里程碑与 Agent 驱动在线评测（2026-08-05）已完成后的路线图。
> 本文档与 `PLANS.md`（里程碑历史）、根 `NEXT_STEPS.md`（交接提示词）、
> `HANDOFF.md`（会话交接）、`RETROSPECTIVE.md`（复盘）区分：聚焦"接下来做什么"，
> 每项含目标 / 验收 / 涉及文件 / 复用 / 风险 / 优先级。

## 1. 现状基线（2026-08-05，可核验）

- **里程碑**：M0–M10 全部完成并 merge 回 `develop`（已推送 origin）。
- **在线评测**（DeepSeek 真实调用，`evals/reports/2026-08-05-online-default.md`）：raw **100%（8/8）**、plan_gates **75%（6/8）**、plan_gates_reviewer **75%（6/8）**；基线 25% → 在线 75–100%。
- **质量**：ForgeFlow **181 passed / 1 skipped / 5 deselected（online）**；ruff / mypy clean（55 文件）；`src/openharness/` **0 源文件被修改**。
- **CI**（`.github/workflows/ci.yml`）：单 job，Python 3.11/3.12，清 `ANTHROPIC_*`，跑 ruff / mypy / `pytest tests/forgeflow`；`addopts -m "not online"` 默认跳过在线；**不含上游 `tests/`**。

## 2. 工作项（按优先级）

### P0-1 Docker Compose 端到端验证（NEXT_STEPS §4.4 落地）
- **目标**：`docker compose up --build` 起 postgres/redis/api/worker 四服务，验证任务 API 可用。
- **验收**：四服务 healthy/started；`GET localhost:8000/api/v1/tasks` 返回 200（路由 `api/app.py:43-45`）；POST 建任务 → start → SSE 事件可见。
- **前置风险**：
  1. 本机需先启动 Docker Desktop/WSL2（当前未运行）。
  2. Dockerfile `pip install -e ".[service]"` 未加 `--no-build-isolation`——代理/镜像下 hatchling build isolation 可能失败（项目已知坑，NEXT_STEPS §3）。
  3. wheel `force-include`（`pyproject.toml`）引用 `frontend/terminal/{package.json,tsconfig.json,src}`——文件在仓库**存在**，但 Docker build context 只 COPY `pyproject.toml/README.md/src/`，未含 `frontend/`——hatch 打包时**报错还是静默跳过需实测**；若失败，把 `frontend` 加入 COPY。
- **涉及**：`Dockerfile`、`docker-compose.yml`、（可能）`pyproject.toml`。

### P0-2 经验检索 before/after 对比实验（M9 未接线的对比）
- **目标**：同一在线策略（如 plan_gates）带/不带 `build_retrieval_context` 跑 `default` 数据集，比较完成率/测试通过率。
- **做法**：
  - 扩展 `EvalStrategy.run` 协议（`evaluation/strategies.py:23-27`）加可选 `context: str = ""`，策略把上下文拼进 `build_fix_prompt`（`evaluation/strategies_online.py`）。
  - 复用 `retrieve_experience` / `build_retrieval_context`（`evaluation/retrieval.py:22/39`，已实现有测试）。
  - runner 增加"是否注入检索上下文"开关；用 `retrieval_comparison` 记录注入摘要。
- **验收**：带/不带两次运行的完成率对比表；数字真实可复现；报告入 `evals/reports/`。
- **涉及**：`evaluation/strategies.py`、`evaluation/strategies_online.py`、`evaluation/runner.py`；复用 `evaluation/retrieval.py`。
- **风险**：检索质量依赖反馈数据集规模（当前无真实历史样本，可能命中为空 → 对比"无差异"也如实记录）。

### P1-1 服务层接真实 Agent executor
- **目标**：任务服务路径从确定性 `LocalTaskExecutor` 升级为模型驱动 executor。
- **做法**：实现 `ModelDrivenTaskExecutor` 满足 `TaskExecutor` protocol（`application/executors.py:30-31`），复用 `strategies_online.py` 的 runtime/agent 逻辑；在 `application/factory.py:36` 替换注入即可（`task_orchestrator.py:96` 只调 `_executor.execute`，`task_service.py` 不经 executor）。
- **验收**：服务端到端 建任务→start→模型驱动执行→状态/Trace 落库；质量门禁/审批仍生效。
- **涉及**：`application/executors.py`、`application/factory.py`；复用 `evaluation/strategies_online.py`。
- **风险**：在线执行时长/成本不可控 → 需预算与超时（复用 `orchestration/budgets.py` 与在线策略墙钟超时）；生产凭据管理。

### P1-2 推送 `upstream-base-0.1.9` 标签到 origin
- **验收**：`git push origin upstream-base-0.1.9` 后可 `git show-ref` 核验。
- **风险**：推送标签属共享状态，执行前确认。

### P2-1 上游同步（NEXT_STEPS §4.5）
- **规则**：仅里程碑间隙、且为安全/兼容/严重 bugfix 时 `git fetch upstream` → 独立 `sync/upstream-<sha>` 分支 → 上游测试 → ForgeFlow 回归 → 更新 `UPSTREAM_MAP`。
- **验收**：`UPSTREAM_MAP` 更新；`src/openharness` 仍 0 修改（确需修改须 `patches/` + ADR）。

### P2-2 CI 扩展（可选）
- **现状**：CI 只跑 `tests/forgeflow`，默认跳过 online，不含上游 `tests/`（故"14 个 Windows 预存失败"目前无 CI 复验）。
- **可选**：加 Linux 上游 `tests/` 复验 job；在线评测冒烟（需配 DeepSeek secret）。
- **验收**：CI 绿；新 job 不阻塞主流程。

### P2-3 质量基线维护
- 每个改动后：`pytest tests/forgeflow -q`、`ruff check src/forgeflow tests/forgeflow`、`MYPYPATH=src mypy src/forgeflow --explicit-package-bases --python-version 3.11`。
- 评测数字变化同步 `docs/EVALUATION.md` 与 README。

## 3. 依赖与排序建议

- P0-2（检索对比）无需 Docker，可立即开始；P0-1 依赖本机 Docker Desktop 可用。
- P1-1 依赖在线策略运行时（P0-2 会复用它，建议在其后）。
- 建议顺序：**P0-2 → P0-1 → P1-1 → P1-2 → P2-1/P2-2/P2-3 穿插**。

## 4. 完成定义

- 每项验收标准可执行、可复现；评测数字真实不编造（`PROJECT_SPEC` §16）；改动后质量基线全绿。
