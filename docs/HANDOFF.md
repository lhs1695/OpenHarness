# HANDOFF — 跨会话交接

> 每次会话结束/里程碑结束更新本文件。新会话开始先读 `PROJECT_SPEC.md`、`docs/ARCHITECTURE.md`、`docs/PLANS.md`、`docs/UPSTREAM_MAP.md` 与本文件。

## 上次更新
- 2026-08-05（M1 实现完成，待独立审查）

## 当前状态

- **里程碑**：M0 ✅；M1 实现完成（13 单测 + 1 在线垂直链路通过、ruff/mypy clean），待独立审查后 merge 回 develop。
- **分支/worktree**：
  - `main` @ `af94671`（可发布，含 setup 文档）
  - `develop` @ `f65db21`（含 M0 审计 + 架构修订，已推送 origin）
  - `milestone/m1-adapter` @ 当前（M1 适配层实现，**尚未 merge 回 develop**）
  - 上游基础标签 `upstream-base-0.1.9` @ `9b2efd7`（未推送）
- **M1 产物**：`src/forgeflow/`（domain/task + integrations/openharness/{adapter,event_mapper,exceptions} + py.typed）、`tests/forgeflow/`（unit ×2 + integration ×1 + fixture 仓库）、`pyrightconfig.json`。
- **M1 对 pyproject.toml 的改动**（ADR 0001 已声明）：wheel 加 `src/forgeflow`；`mcp<2.0.0`；dev 加 `tzdata`；pytest `online` marker + `addopts = "-m \"not online\""`。

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

## 下一步（M2）

1. M1 独立审查（§17.4）→ merge `milestone/m1-adapter` 回 `develop` → 清理 m1 worktree。
2. 从 `develop` 建 `milestone/m2-control-plane` worktree。
3. 按 `docs/PLANS.md` M2：`domain/{policy,risk}` + `orchestration/{state_machine,budgets}` + 状态机/风险/预算单测。

## 待办/风险

- 未推送任何内容到 `upstream`（HKUDS/OpenHarness）。所有推送仅到 `origin`（自己的 fork）。
- `milestone/m1-adapter` 分支与 `upstream-base-0.1.9` 标签尚未推送。
- `test_autopilot`、`test_cron_scheduler` 等失败待 Linux CI 复验（见 BASELINE §4）。
- 在线垂直链路依赖 DeepSeek 端点与凭据；模型输出格式为 best-effort 解析（M8 评测再收紧）。
