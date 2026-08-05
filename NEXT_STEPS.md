# NEXT_STEPS — 下一轮对话提示词与后续任务

> 本文件两部分合一：
> 1. **§1 是可直接复制粘贴给 Claude Code 的下一轮提示词**；
> 2. **§2–§4 是项目整体问题排查与维护的必须后续任务清单**（在线评测、补文档、Docker 验证、上游同步、已知问题、质量基线）。
>
> 上一轮交接状态：ForgeFlow M0–M10 全部完成并 merge 回 `develop`（@ `ac23ef2`，已推送 origin）。

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
   - 在 `src/forgeflow/evaluation/strategies.py` 的 `EvalStrategy` 接缝上实现三个**在线策略**，
     它们真的在隔离 worktree 里让 Agent 修复 `billing-service` 的幂等 bug：
     - `raw`：直接用 OpenHarness Agent（QueryEngine + 工具）修复，跑仓库测试；
     - `plan_gates`：先用 Adapter（`run_plan`）出计划，再让 Agent 修复，跑必需命令 + 质量门禁；
     - `plan_gates_reviewer`：`plan_gates` + 只读 Reviewer（`quality/reviewer.py`）。
   - 复用：`execution/worktree.py`（隔离 worktree）、`quality/reports.py`（门禁 runner）、
     `quality/reviewer.py`、`evaluation/metrics.py`（指标）。
   - 预期：`default` 数据集 6 个 billing 基线失败案例在 Agent 修复后**翻转为通过**，
     得到 raw / plan_gates / plan_gates_reviewer 三策略的真实完成率对比。
   - 数字必须真实，禁止编造（PROJECT_SPEC §16）。把报告存 `evals/reports/`。
2. 写 `docs/RETROSPECTIVE.md`（一页项目复盘）：目标 vs 达成、关键设计、踩过的坑、局限、下一步，含真实数字。
3. 写 `docs/RESUME.md`（简历描述）：用真实评测数字填 `PROJECT_SPEC.md` §20 模板的 [X]/[A]/[B]/[C]。
4. 可选：`docker compose up` 验证（需启动 Docker Desktop/WSL2）；推送 `upstream-base-0.1.9` 标签到 origin。

## 规则
- **不改 `src/openharness/` 任何源文件**；新增能力都放 `src/forgeflow/`。
- 新行为必须有测试；只对改动文件跑 `ruff`/`mypy`（命令见 §3）。
- 完成一项就更新 `docs/HANDOFF.md` 与本文件；结束前汇报：改了什么、真实数字、遗留风险。
```

---

## §2 项目现状（关键事实）

- **里程碑**：M0 审计 → M1 适配层 → M2 控制平面 → M3 隔离执行 → M4 质量门禁 → M5 审批/Reviewer → M6 服务化 → M7 Trace → M8 评测 → M9 数据回流 → M10 包装 —— **全部完成**。
- **Git**：`main` @ `af94671`（可发布）；`develop` @ `ac23ef2`（已推送 origin）；`upstream-base-0.1.9` 标签 @ `9b2efd7`（未推送）。**原仓库 HKUDS/OpenHarness 从未推送**。
- **上游边界（可核验）**：`src/openharness/` **0 个源文件被修改**；上游文件改动仅 `pyproject.toml`（wheel 加 `src/forgeflow`、`mcp<2.0.0`、`tzdata`、`online` marker、`service` extra）与 `README.md`（替换为 ForgeFlow 版）。
- **代码量**：`src/forgeflow/` ~54 个源文件；ForgeFlow 测试 **168 passed / 1 skipped / 2 deselected**；全量 **1302 passed / 14 failed**（14 项为 Windows 平台预存失败）。
- **评测基线**：`default` 数据集 `plan_gates` 本地策略完成率 **25%（2/8）**（2 个 cart verify 通过，6 个 billing 基线失败）。存档 `evals/reports/2026-08-05-default-plan_gates.md`。

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

### 4.1 Agent 驱动在线评测（最高优先）
- **为什么**：当前评测只有确定性本地策略（基线失败是"未修复"信号）。简历模板（PROJECT_SPEC §20）的"任务成功率从 [A]% 提升到 [B]%"需要真实 Agent 评测数字。
- **怎么做**：见 §1 提示词任务 1。关键：在线策略要真的让 Agent 在隔离 worktree 里修改 `payment.py` 修复幂等 bug，然后跑测试 + 门禁。
- **验收**：三策略对比报告入 `evals/reports/`；数字真实可复现；billing 案例从失败翻转为通过（或如实记录为何未翻转）。

### 4.2 补写 `docs/RETROSPECTIVE.md`（一页项目复盘）
- 内容：目标 vs 达成、关键设计决策、踩过的坑（§3 环境坑）、局限与未完成（认证、Docker 沙箱、真实 PR 提交）、下一步。含真实数字。

### 4.3 补写 `docs/RESUME.md`（简历描述）
- 用真实评测数字填 `PROJECT_SPEC.md` §20 模板；**数字必须来自 4.1 的实测**。

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
