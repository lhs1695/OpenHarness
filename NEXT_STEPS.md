# NEXT_STEPS — 下一轮对话提示词与后续任务

> 本文件两部分合一：
> 1. **§1 是可直接复制粘贴给 Claude Code 的下一轮提示词**；
> 2. **§2–§4 是项目整体问题排查与维护的必须后续任务清单**（在线评测、补文档、Docker 验证、上游同步、已知问题、质量基线）。
>
> 上一轮交接状态：ForgeFlow M0–M10 全部完成并 merge 回 `develop`（@ `ac23ef2`，已推送 origin）。
> 本轮交接状态（2026-08-05）：Agent 驱动在线评测已实现并跑出真实三策略对比；`docs/RETROSPECTIVE.md` 与 `docs/RESUME.md` 已补齐（真实数字见 §2）。

---

## §1 下一轮对话提示词（复制本块给 Claude Code）

```text
你是 ForgeFlow 项目的下一位开发会话。上一位会话把项目交接给你，请按下列顺序执行。

## 开始前必读
- PROJECT_SPEC.md            （规格与里程碑验收标准）
- docs/ARCHITECTURE.md       （架构，含 Mermaid 图）
- docs/STATE_MACHINE.md      （状态机，含 Mermaid 图）
- docs/PLANS.md              （里程碑进度：M0–M10 已完成）
- docs/UPSTREAM_MAP.md 与 docs/UPSTREAM_CONTRIBUTIONS.md（上游边界）
- docs/EVALUATION.md         （评测与数据回流方法学）
- docs/HANDOFF.md 与 NEXT_STEPS.md（交接与任务清单）

## 环境
- 从 `develop` 派生新 worktree：
  `git worktree add -b feat/next-step .claude/worktrees/next-step develop`
  然后在 worktree 内：`python -m pip install -e ".[dev,service]" --no-build-isolation`
- 如 `import openharness` 失败（editable 指向已删旧 worktree）：先
  `pip uninstall openharness-ai`，删除 `site-packages/openharness`，再重装。
- 跑测试前清 `ANTHROPIC_AUTH_TOKEN`/`ANTHROPIC_BASE_URL` 等真实凭据。
- 在线测试用 `pytest -m online`（需 DeepSeek 凭据，已在 `~/.openharness/settings.json` 配置）。

## 本轮任务（按优先级，一项完成再下一项）
1. [最高优先] 实现 Agent 驱动在线评测
   - ✅ 已完成：`evaluation/strategies_online.py` 实现 raw / plan_gates / plan_gates_reviewer 三个在线策略，
     在隔离 worktree 里让真实 Agent 修复 `billing-service` 幂等 bug，CLI `--online` 启用；
     runner/metrics/reports 增加 `agent_failed` 失败分类与平均工具失败列；在线策略带墙钟超时（规划/实现/评审）。
   - 结果：`evals/reports/2026-08-05-online-default.md` —— raw **100%（8/8）**、plan_gates **75%（6/8）**、
     plan_gates_reviewer **75%（6/8）**；6 个 billing 基线失败案例翻转。
2. 写 `docs/RETROSPECTIVE.md`（一页项目复盘）：✅ 已完成（含真实评测数字与踩过的坑）。
3. 写 `docs/RESUME.md`（简历描述）：✅ 已完成，用真实数字填 `PROJECT_SPEC.md` §20 模板（[X]=8 案例、[A]=25%→[B]=75%（raw 100%）、[C]≈43% 工具失败下降）。
4. 可选：`docker compose up` 验证（需启动 Docker Desktop/WSL2，见 `docs/NEXT_PHASE.md` P0-1）；推送 `upstream-base-0.1.9` 标签到 origin。
   - ✅ 经验检索 before/after 已完成：plan_gates 75% → **87.5%**（`evals/reports/2026-08-05-online-default-retrieval.md`；`--feedback-dataset evals/data/seed-experience.json`）。

## 规则
- **不改 `src/openharness/` 任何源文件**；新增能力都放 `src/forgeflow/`。
- 新行为必须有测试；只对改动文件跑 `ruff`/`mypy`（命令见 §3）。
- 在线评测需真实凭据，结果与 DeepSeek 端点/模型相关——换模型必须重跑才可复现。
- 完成一项就更新 `docs/HANDOFF.md` 与本文件；结束前汇报：改了什么、真实数字、遗留风险。
```

---

## §2 项目现状（关键事实）

- **里程碑**：M0 审计 → M1 适配层 → M2 控制平面 → M3 隔离执行 → M4 质量门禁 → M5 审批/Reviewer → M6 服务化 → M7 Trace → M8 评测 → M9 数据回流 → M10 包装 —— **全部完成**。
- **Git**：`main` @ `af94671`（可发布）；`develop`（含 M0–M10 + 本轮在线评测，已推送 origin）；`upstream-base-0.1.9` 标签 @ `9b2efd7`（未推送）。**原仓库 HKUDS/OpenHarness 从未推送**。
- **上游边界（可核验）**：`src/openharness/` **0 个源文件被修改**；上游文件改动仅 `pyproject.toml`（wheel 加 `src/forgeflow`、`mcp<2.0.0`、`tzdata`、`online` marker、`service` extra）与 `README.md`（替换为 ForgeFlow 版）。
- **代码量**：`src/forgeflow/` 55 个源文件；ForgeFlow 测试 **190 passed / 1 skipped / 6 deselected（online）**；全量 **1302 passed / 14 failed**（14 项为 Windows 平台预存失败）。
- **评测基线**：`default` 数据集 `plan_gates` 本地策略完成率 **25%（2/8）**（2 个 cart verify 通过，6 个 billing 基线失败）。存档 `evals/reports/2026-08-05-default-plan_gates.md`。
- **在线评测（2026-08-05）**：`default` × raw/plan_gates/plan_gates_reviewer（DeepSeek 真实调用）→ 完成率 **100% / 75% / 75%**；6 个 billing 基线失败案例翻转；plan_gates 平均工具失败 0.50 次/案例（较 raw 0.88 降约 43%）。存档 `evals/reports/2026-08-05-online-default.md`。
- **经验检索 before/after（2026-08-05）**：plan_gates 带种子经验（`--feedback-dataset evals/data/seed-experience.json`）→ **87.5%**（7/8），对比不带 75%。存档 `evals/reports/2026-08-05-online-default-retrieval.md`。
- **服务层模型驱动 executor（P1-1，2026-08-05）**：`ModelDrivenTaskExecutor` + `FORGEFLOW_EXECUTOR=model` 让服务任务走真实 Agent（复用 plan_gates 策略）；离线+服务级测试 6 passed、在线冒烟通过。

## §3 质量命令与环境速查

```bash
# ForgeFlow 测试（离线，默认跳过 online）
pytest tests/forgeflow -q
# 在线测试（需凭据）
pytest -m online tests/forgeflow/integration/test_vertical_chain.py
pytest -m online tests/forgeflow/integration/test_reviewer_online.py
# lint / 类型
ruff check src/forgeflow tests/forgeflow
MYPYPATH=src mypy src/forgeflow --explicit-package-bases --python-version 3.11
# 评测 CLI（--output 写 UTF-8 报告）
python -m forgeflow.evaluation.runner --dataset default --strategies plan_gates --output evals/reports/x.md
```

**环境坑（遇到即查）**：
1. 换 worktree 后 `import openharness` 失败 → editable 指向已删旧 worktree：`pip uninstall openharness-ai` + 删 `site-packages/openharness` + 重装 `pip install -e ".[dev,service]" --no-build-isolation`。
2. 跑测试前清全部 `ANTHROPIC_*`（含 `ANTHROPIC_BASE_URL`，它污染 provider 检测测试）。
3. `mcp` 必须 `<2.0.0`；Windows 需 `tzdata`；mypy 目标 3.11（本机 venv 是 3.12）。
4. 测试文件 basename 不能与上游 `tests/` 冲突（已踩过 `test_adapter.py`、`test_registry.py`，注意 `test_*_registry.py` 这类）。
5. Windows 控制台中文乱码 → 用 CLI `--output` 写 UTF-8 文件，或设 `PYTHONIOENCODING=utf-8`。
6. Docker/WSL2 本机未运行 → `docker compose up` 前先启动 Docker Desktop。

## §4 必须做的后续任务（问题排查与维护）

### 4.1 Agent 驱动在线评测（最高优先）—— ✅ 已完成（2026-08-05）
- **结果**：三策略在线对比报告 `evals/reports/2026-08-05-online-default.md`；`default` 数据集完成率 raw **100%（8/8）**、plan_gates **75%（6/8）**、plan_gates_reviewer **75%（6/8）**。
- **代码**：`evaluation/strategies_online.py`（raw / plan_gates / plan_gates_reviewer，CLI `--online`，含墙钟超时）；runner `--online`；metrics/reports 增加 `agent_failed` 与平均工具失败列。
- **如实记录**：billing-003（负金额）与 billing-005（重构）未被门禁策略修复；billing-005 被 Reviewer 拒绝；门禁策略完成率低于无约束 raw——不夸大。
- **踩坑**：门禁读文件默认 GBK（中文 Windows）导致首轮 plan_gates 全挂 → 已修 `read_text(encoding="utf-8", errors="replace")` + 回归测试；Agent 无墙钟超时导致挂起 → 已加（规划 10min/实现 15min/评审 5min）。

### 4.2 补写 `docs/RETROSPECTIVE.md`（一页项目复盘）—— ✅ 已完成
- 内容：目标 vs 达成、关键设计决策、踩过的坑（含 GBK/超时/上线前的坑）、局限与未完成、下一步。含真实评测数字。

### 4.3 补写 `docs/RESUME.md`（简历描述）—— ✅ 已完成
- 用真实评测数字填 `PROJECT_SPEC.md` §20 模板：8 个可复现任务、25%→75%（raw 100%）、工具失败降约 43%。

### 4.4 Docker Compose 验证
- 启动 Docker Desktop（WSL2）后 `docker compose up --build`，验证 postgres/redis/api/worker 四服务；`GET localhost:8000/api/v1/tasks` 可用。
- 若 WSL2 不可用：记录为环境限制，不阻塞（M6 验收已用 `config --quiet` 语法校验兜底）。

### 4.5 上游同步（只在里程碑间隙做）
- `git fetch upstream` → 独立 `sync/upstream-<sha>` 分支 → 先跑上游测试再跑 ForgeFlow 回归 → 更新 `docs/UPSTREAM_MAP.md`。
- 只同步安全/兼容/严重 Bugfix；不同步 UI/聊天渠道等无关内容。

### 4.6 已知问题清单（持续维护）
- 上游全量 14 个 Windows 失败（fcntl/symlink/原子重命名/控制台/进程管理）——**预存平台问题**，非本项目引入；建议在 Linux CI（`.github/workflows/ci.yml`）复验。
- 上游 `ruff`/`mypy` 全树本就不通过（709 / 1188）——质量门禁只对改动文件做检查。
- 在线测试（`online` marker）需真实凭据，默认跳过。

### 4.7 代码质量维护基线
- 每个 milestone/改动后跑：`pytest tests/forgeflow`、`ruff`、`mypy`（§3 命令）。
- ForgeFlow 新代码保持 mypy-clean（54 个文件基线）；新增测试不与上游 basename 冲突。
- 评测数字如有变化，同步更新 `docs/EVALUATION.md` 的"实测报告"与 README。

---

> 完成本节 §1 任务后：更新 `docs/HANDOFF.md`（上次更新/当前状态/下一步）、本文件（勾选已完成项），并汇报真实数字与遗留风险。
