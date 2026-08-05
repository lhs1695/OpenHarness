# HANDOFF — 跨会话交接

> 每次会话结束/里程碑结束更新本文件。新会话开始先读 `PROJECT_SPEC.md`、`docs/ARCHITECTURE.md`、`docs/PLANS.md`、`docs/UPSTREAM_MAP.md` 与本文件。
> 当前状态快照（给新读者，不含交接清单）见 `docs/STATUS.md`。

## 上次更新
- 2026-08-05（Agent 驱动在线评测完成 + 复盘/简历补齐）

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
