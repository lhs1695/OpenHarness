# BASELINE — 上游版本基线与环境记录

> 审计日期：2026-08-05。审计环境：Windows 11（Win11 Home China 10.0.26200）+ git-bash。

## 1. 版本基线

| 项 | 值 |
|---|---|
| 包名 / 版本 | `openharness-ai` 0.1.9 |
| Fork 仓库 | `origin` = https://github.com/lhs1695/OpenHarness.git |
| 上游仓库 | `upstream` = https://github.com/HKUDS/OpenHarness.git |
| 本地 `main` / `develop` HEAD | `af94671a9db4dfd4d7dcd112b5b9979cc4096948`（含 ForgeFlow setup commit） |
| 上游基础 commit | `upstream/main` = `9b2efd795c6aa09f88b0c257d269a9e518da6ae7` |
| 上游 tag `v0.1.9` | `a0f8552c69d6d0b25d613af288823212a8b6b59a` |
| 新标签 `upstream-base-0.1.9` | `9b2efd7`（指向上游基础 commit，规格 §15） |
| Python 要求 | `requires-python = ">=3.10"`（pyproject.toml） |
| 本机 venv Python | **3.12.10**（`D:\workspace\OpenHarness-dev\.venv`） |
| 构建后端 | hatchling |
| 依赖管理 | `pip install -e ".[dev]"` |
| 重要依赖 | anthropic>=0.40, openai>=1.0, mcp>=1.0.0（**需固定 <2.0.0**，见 §5）, pydantic>=2, typer, textual, rich, pyyaml, questionary 等 |
| Dev 依赖 | pytest, pytest-asyncio, pytest-cov, ruff, mypy（strict）, pexpect |

## 2. 入口命令（pyproject `[project.scripts]`）

- `openharness` / `oh` / `openh` → `openharness.cli:app`（`src/openharness/cli.py`）
- `ohmo` → `ohmo.cli:app`

## 3. 安装 / 启动 / 测试实际结果

### 3.1 安装
- 已确认 `openharness-ai 0.1.9` 以 **editable** 方式安装于根 venv（`pip list --editable` → `D:\workspace\OpenHarness-dev`）。
- 已安装 `mcp==1.29.0`（< 2.0.0，符合环境要求）、`tzdata==2026.3`。
- pip 源：清华镜像 `https://pypi.tuna.tsinghua.edu.cn/simple/`。

### 3.2 启动
- 审计阶段**不发起真实模型调用**，未做交互式启动；入口解析见 §2 与 `CALL_FLOW.md`。

### 3.3 测试（`pytest -q`）

```
16 failed, 1132 passed, 11 skipped, 14 warnings in 139.05s
```

**失败清单与分类**（详见 §4）：

| 测试 | 观察到的错误 | 分类 |
|---|---|---|
| `test_swarm/test_lockfile.py::test_exclusive_file_lock_creates_lock_file_on_posix` | `No module named 'fcntl'` | **POSIX-only 测试**，Windows 必然失败 |
| `test_sandbox/test_path_validator.py::test_symlink_escape_blocked` | `OSError [WinError 1314]` 创建符号链接无权限 | **Windows 权限**（需管理员/开发者模式） |
| `test_swarm/test_team_lifecycle.py` ×3（add_member_persists / add_member_replaces_existing / remove_member） | `FileExistsError [WinError 183]` 原子重命名 team.json | **Windows 原子写行为** |
| `test_utils/test_shell.py::test_create_shell_subprocess_defaults_stdin_to_devnull` | 断言 cmd.exe == /usr/bin/bash | **POSIX 假设**（shell 解析差异） |
| `test_ui/test_modes.py::test_input_session_updates_prompt_modes` | `NoConsoleScreenBufferError: Found xterm-256color` | **非控制台环境**（git-bash 下运行 TUI） |
| `test_ohmo/test_gateway.py::test_stop_gateway_process_kills_matching_workspace_processes` | 断言进程列表为空 | **Windows 进程管理** |
| `test_auth/test_external.py::test_cli_provider_use_activates_codex_profile` | `assert 'https://api.deepseek.com/anthropic' is None` | **环境相关**（ANTHROPIC_BASE_URL 被真实配置覆盖，见 §5） |
| `test_ui/test_react_backend.py::test_backend_host_command_does_not_reset_cli_overrides` | `assert 'deepseek' == 'openai-compatible'` | **环境相关**（同上） |
| `test_swarm/test_registry.py` ×2（registers_subprocess_and_in_process / get_executor_in_process） | `Backend 'in_process' is not registered. Available: ['subprocess']` | **依赖环境开关**（in_process 后端受 `OPENHARNESS_TEAMMATE_MODE` 控制） |
| `test_autopilot/test_verification.py::test_run_verification_end_to_end_without_shell` | `assert 'error' == 'success'` | **待确认**（端到端验证，无 shell 路径） |
| `test_services/test_cron_scheduler.py::TestExecuteJob` ×2 | `assert 'error' == 'success'/'failed'` | **待确认**（作业执行返回 error，可能 shell/环境相关） |

**建议**：
- 在线/真实 API 测试应加 `online` marker（如 `test_real_large_tasks.py`、`test_hooks_skills_plugins_real.py` 等），离线默认跳过。
- 以上 16 项失败疑似均为平台/环境相关，**需在 Linux CI 复验**以确认非真实 bug。

### 3.4 Lint（`ruff check .`）

```
Found 709 errors（369 fixable with --fix）
```

规则分布前几项：`I001`(175)、`BLE001`(145)、`RUF012`(40)、`UP017`(37)、`ASYNC221`(29)、`UP037`(28)、`UP041`(26)、`UP035`(21)、`UP045`(15)、`PLW1510`(15)、`S110`(14)、`RET501`(13)、`PLR1711`(13)、`RUF059`(12)、`DTZ003`(12)。

- 结论：**上游 `ruff check .` 全树不通过**（多为 import 排序与盲捕获）。ForgeFlow 质量门禁应**只对改动文件**做 ruff，不能要求全树通过。

### 3.5 类型检查（`mypy src --python-version 3.11`）

```
Found 1188 errors in 189 files (checked 230 source files)
```

- 大量 `Skipping analyzing ... missing library stubs or py.typed marker`（对包内子模块），以及 channel 实现、mcp 客户端等的类型错误。
- 结论：**上游 mypy strict 全树不通过**。ForgeFlow 自身代码应保持 mypy-clean，但对共享树不能以"全树 mypy 通过"作为验收门槛。
- 注意：本机 venv 为 Python 3.12.10，pyproject 中 mypy `python_version = "3.11"`，运行需显式 `--python-version 3.11`（否则 mypy 用解释器版本 3.12）。

## 4. 测试失败分类小结

- **Windows / POSIX 假设（≥8 项）**：fcntl、symlink 权限、原子重命名、shell 解析、控制台缓冲、进程管理。
- **环境变量污染（2 项）**：`ANTHROPIC_BASE_URL` 与本地 settings 使 provider 检测断言失败。
- **环境开关（2 项）**：`OPENHARNESS_TEAMMATE_MODE` 未开启 in_process 后端。
- **待确认（3 项）**：autopilot verification、cron_scheduler ×2。

## 5. 环境注意事项（三个已知 quirks + 一个新增）

1. **清凭据**：运行测试/启动前必须 `unset ANTHROPIC_AUTH_TOKEN`（本机确有真实凭据存在 `~/.openharness/`）。
2. **mcp 版本**：`mcp` 必须 `<2.0.0`（当前 `1.29.0`）；pyproject 里 `mcp>=1.0.0` 过宽，需在 M1 固定。
3. **tzdata**：Windows 需要 `tzdata`（zoneinfo）。
4. **新增：ANTHROPIC_BASE_URL / ANTHROPIC_REASONING_MODEL 也会影响 provider 检测测试**。本机 shell 已配置 `ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic`，测试环境应同时清掉 `ANTHROPIC_BASE_URL` 等变量，或用隔离的 `OPENHARNESS_CONFIG`/HOME 运行。
5. `~/.openharness/settings.json`（7237B）与 `credentials.json` 存在于本机，含真实配置；**任何 ForgeFlow 代码不得读取/提交这些文件**（已在 `.gitignore` 的 `.openharness/` 覆盖）。

## 6. 目录说明

- `docs/` 已有跟踪内容：`SHOWCASE.md`、`autopilot/`（静态站点产物）——M0 只新增 `docs/audit/`，不重建 `docs/`。
- `.gitignore` 本次追加 `.claude/worktrees/`（此前为 untracked 噪音）。

## 7. 审计范围声明

- 本次审计覆盖 `src/openharness/` 全部 31 个顶层模块（240+ 源文件），未修改任何业务代码。
- 所有结论均引用真实文件/类/函数/行号；未核实项在相应文档明确标记。
