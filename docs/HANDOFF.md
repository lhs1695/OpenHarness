# HANDOFF — 跨会话交接

> 每次会话结束/里程碑结束更新本文件。新会话开始先读 `PROJECT_SPEC.md`、`docs/ARCHITECTURE.md`、`docs/PLANS.md`、`docs/UPSTREAM_MAP.md` 与本文件。

## 上次更新
- 2026-08-05（M0 完成并审查通过，架构修订完成）

## 当前状态

- **里程碑**：M0 完成 ✅；M1 待开始（`docs/PLANS.md` 有 M1 详细计划）。
- **分支/worktree**：
  - `main` @ `af94671`（可发布，含 setup 文档）
  - `develop` @ `af94671`（集成分支）
  - `milestone/m0-audit` @ 当前（含 M0 审计 + 架构修订文档，**尚未 merge 回 develop**）
  - 上游基础标签 `upstream-base-0.1.9` @ `9b2efd7`（未推送）
- **M0 产物**：`docs/audit/{BASELINE,MODULE_MAP,CALL_FLOW,EXTENSION_POINTS,RISK_REGISTER}.md`、`docs/UPSTREAM_MAP.md`。
- **架构修订产物**：`docs/ARCHITECTURE.md`、`docs/STATE_MACHINE.md`、`docs/PLANS.md`、`docs/adr/0001-integration-strategy.md`、`docs/HANDOFF.md`。

## 关键事实（新会话必须知道）

- 本机 `~/.openharness/` 有真实凭据；跑测试清全部 `ANTHROPIC_*` 环境变量（含 `ANTHROPIC_BASE_URL`）。
- 上游全树 ruff/mypy 本就不通过（ruff 709 / mypy 1188）；质量门禁只对改动文件做检查。
- 环境：Windows + git-bash；pip 清华镜像；`mcp<2.0.0`；`tzdata`；根 `.venv` 为 Python 3.12.10（mypy 需显式 `--python-version 3.11`）。
- 集成策略：adapt-and-extend，5 条接缝（ADR 0001）。不改上游核心。

## 下一步（M1）

1. 把 `milestone/m0-audit` merge 回 `develop`（若尚未做）。
2. 从 `develop` 建 `milestone/m1-adapter` worktree。
3. 按 `docs/PLANS.md` M1 落地：`src/forgeflow/` 适配层 + 垂直链路测试 + `pyproject.toml` 声明改动。
4. 只对 ForgeFlow 代码跑 ruff/mypy；`online` 测试打 marker。

## 待办/风险

- 未推送任何内容到 `upstream`（HKUDS/OpenHarness）。所有推送仅到 `origin`（自己的 fork）。
- `milestone/m0-audit` 分支与 `upstream-base-0.1.9` 标签尚未推送。
- `test_autopilot`、`test_cron_scheduler` 等失败待 Linux CI 复验（见 BASELINE §4）。
