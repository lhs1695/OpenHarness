# NEXT_PHASE — ForgeFlow 下一阶段计划（Phase 2：加固与扩展）

> M0–M10 里程碑与 Agent 驱动在线评测（2026-08-05）已完成后的路线图。
> 本文档与 `PLANS.md`（里程碑历史）、根 `NEXT_STEPS.md`（交接提示词）、
> `HANDOFF.md`（会话交接）、`RETROSPECTIVE.md`（复盘）区分：聚焦"接下来做什么"，
> 每项含目标 / 验收 / 涉及文件 / 复用 / 风险 / 优先级。

## 1. 现状基线（2026-08-05，可核验）

- **里程碑**：M0–M10 全部完成并 merge 回 `develop`（已推送 origin）。
- **在线评测**（DeepSeek 真实调用，`evals/reports/2026-08-05-online-default.md`）：raw **100%（8/8）**、plan_gates **75%（6/8）**、plan_gates_reviewer **75%（6/8）**；基线 25% → 在线 75–100%。
- **质量**：ForgeFlow **190 passed / 1 skipped / 6 deselected（online）**；ruff / mypy clean（55 文件）；`src/openharness/` **0 源文件被修改**。
- **CI**（`.github/workflows/ci.yml`）：单 job，Python 3.11/3.12，清 `ANTHROPIC_*`，跑 ruff / mypy / `pytest tests/forgeflow`；`addopts -m "not online"` 默认跳过在线；**不含上游 `tests/`**。

## 2. 工作项（按优先级）

### P0-1 Docker Compose 端到端验证（NEXT_STEPS §4.4 落地）—— ✅ 已完成（2026-08-05）
- **结果**：`docker compose up -d` 起 postgres(healthy)/redis/api/worker 四服务；`GET localhost:8000/api/v1/tasks` 返回 200；POST 建任务 → start → 状态机 9 次流转 → **COMPLETED**。api 镜像实际 **597MB**（未压缩）。
- **修的问题（Dockerfile）**：
  1. 容器内 pip 默认 PyPI 在墙内挂起 → 加 `ARG PIP_INDEX_URL`（默认清华镜像）。
  2. wheel `force-include` 引用 `frontend/terminal/*` 不在 build context → `COPY frontend ./frontend`。
  3. **容器没有 git** → `LocalTaskExecutor` 建 worktree 报 `FileNotFoundError: 'git'` → Dockerfile 装 `git`。
- **修的问题（compose）**：
  1. `postgres:16`/`redis:7` 从 1ms.run 镜像源拉取 TLS 超时 → 改用本机已有的 alpine 变体。
  2. fixture 目录不是 git 仓库、且 `:ro` 只读挂载挡了 `git worktree add`（要写源 `.git` refs）→ 建 `.docker/repos/billing-service`（git 化副本，`.gitignore` 排除）并**可写**挂载。
- **遗留缺口（如实记录）**：服务策略（`factory.py` 的 `RepositoryPolicy`）**无 required_commands**——服务路径的 `LocalTaskExecutor` 实际不跑仓库测试（只有评测路径经 `_policy_for_case` 注入测试命令）；本次任务 COMPLETED 但未真正跑 pytest。这是服务路径质量门禁的配置缺口，后续可加 `FORGEFLOW_REQUIRED_COMMANDS` 之类注入。

### P0-2 经验检索 before/after 对比实验（M9 未接线的对比）—— ✅ 已完成（2026-08-05）
- **结果**：plan_gates 带检索 **87.5%（7/8）** vs 不带检索 **75%（6/8）**（`evals/reports/2026-08-05-online-default-retrieval.md` vs `...online-default.md`）。注入种子经验后 billing-003 被修复；billing-005 仍未修复。单次运行含模型随机性，如实记录。
- **落地**：`EvalStrategy.run` 协议加可选 `context`；在线策略把 `build_retrieval_context` 拼进 `build_fix_prompt`；runner `--feedback-dataset <json>` 注入；`feedback.py` 加 `dataset_to_json`/`dataset_from_json`；种子集 `evals/data/seed-experience.json`。
- **遗留**：检索按拉丁词重叠打分，中文描述靠 case tags 命中；无真实 trace 历史（在线评测未回流样本到反馈管道）——让检索消费真实历史是后续工作。

### P1-1 服务层接真实 Agent executor —— ✅ 已完成（2026-08-05）
- **落地**：`ModelDrivenTaskExecutor`（`application/executors.py`）满足 `TaskExecutor` protocol，复用在线 `PlanGatesStrategy`，`StoredTask → EvalCase → ExecutionOutcome` 适配；`factory.py` 加 `FORGEFLOW_EXECUTOR=model` 开关（默认 local）。
- **验证**：离线单元+服务级测试（orchestrator→executor→COMPLETED 落库）6 passed；在线冒烟 `test_model_executor_online` 通过（76s，真实模型）。
- **遗留**：在线执行时长/成本受策略墙钟超时约束，未接 `budgets.py` 预算；Trace 只记录状态事件、不记录命令输出（EvalResult 不带 command_results）；生产凭据管理靠 `~/.openharness`。

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

- ✅ 已完成：P0-2（检索对比）、P1-1（服务层模型驱动 executor）、P0-1（Docker Compose 端到端验证，含 Dockerfile/compose 修复）。
- 剩余：P1-2（推标签）、P2-1（上游同步，当前 upstream 无新提交）、P2-2（CI 扩展）、P2-3（质量基线）。
- 建议顺序：**P1-2 → P2-2 → P2-3（持续）**。

## 4. 完成定义

- 每项验收标准可执行、可复现；评测数字真实不编造（`PROJECT_SPEC` §16）；改动后质量基线全绿。
