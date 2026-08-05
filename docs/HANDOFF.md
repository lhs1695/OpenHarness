# HANDOFF — 跨会话交接

> 每次会话结束/里程碑结束更新本文件。新会话开始先读 `PROJECT_SPEC.md`、`docs/ARCHITECTURE.md`、`docs/PLANS.md`、`docs/UPSTREAM_MAP.md` 与本文件。

## 上次更新
- 2026-08-05（M8 实现完成，待独立审查）

## 当前状态

- **里程碑**：M0 ✅；M1–M7 ✅（已 merge）；M8 实现完成（152 单测 + CLI 评测、ruff/mypy clean），待独立审查后 merge 回 develop。
- **分支/worktree**：
  - `main` @ `af94671`（可发布，含 setup 文档）
  - `develop` @ `c5a7453`（含 M0–M7，已推送 origin）
  - `milestone/m8-eval` @ 当前（M8 评测实现，**尚未 merge 回 develop**）
  - 上游基础标签 `upstream-base-0.1.9` @ `9b2efd7`（未推送）
- **M8 产物**：`evaluation/{datasets,metrics,experiment,strategies,runner,reports,fixtures,__main__}.py` + `cart-service` fixture；CLI `python -m forgeflow.evaluation.runner`。
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

## 下一步（M9）

1. M8 独立审查（§17.4）→ merge `milestone/m8-eval` 回 `develop` → 清理 m8 worktree → push develop。
2. 从 `develop` 建 `milestone/m9-feedback` worktree。
3. 按 `docs/PLANS.md` M9：Trace → 脱敏 → 清洗 → 切分 → 成功/失败分类 → 偏好对/经验样本 → Dataset Registry；真实样本可查看、可溯源；"历史经验检索前后"对比实验。

## 待办/风险

- 未推送任何内容到 `upstream`（HKUDS/OpenHarness）。所有推送仅到 `origin`（自己的 fork）。
- `milestone/m8-eval` 分支与 `upstream-base-0.1.9` 标签尚未推送。
- **Docker daemon/WSL2 本机未运行**：`docker compose up` 需先启动 Docker Desktop；compose 文件已通过 `config --quiet` 语法校验。
- `test_autopilot`、`test_cron_scheduler` 等失败待 Linux CI 复验（见 BASELINE §4）。
- 在线垂直链路依赖 DeepSeek 端点与凭据；模型驱动的策略区分（raw / plan_gates / plan_gates_reviewer）与端到端演示在 M9/M10 验证；M8 的 CLI 评测输出中文在 Windows 控制台显示乱码（内容为 UTF-8，正常）。
- **venv 陷阱**：换 worktree 后若 editable 指向已删除的旧 worktree，需 `pip uninstall openharness-ai` + 清理 `site-packages/openharness` + 重装 `pip install -e ".[dev,service]" --no-build-isolation`。
