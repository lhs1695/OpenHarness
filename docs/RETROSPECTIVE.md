# RETROSPECTIVE — ForgeFlow 项目复盘

> 一页复盘。所有数字来自真实构建/测试/评测，禁止编造（`PROJECT_SPEC.md` §16）。
> 在线评测报告见 `evals/reports/2026-08-05-online-default.md`。

## 1. 目标 vs 达成

**目标**（`PROJECT_SPEC.md` §1–§13）：基于 OpenHarness（上游通用 Agent Runtime）做**不侵入上游核心**的二次开发，构建"研发任务交付与质量闭环平台"——任务分级、仓库策略、风险评分、执行预算、人工审批、质量门禁、隔离执行、全链路 Trace、评测与数据回流，形成从需求输入到 Patch/Draft PR 的闭环。

**达成**：

| 维度 | 数字 |
|---|---|
| 里程碑 | M0 审计 → M1 适配层 → M2 控制平面 → M3 隔离执行 → M4 质量门禁 → M5 审批/Reviewer → M6 服务化 → M7 Trace → M8 评测 → M9 数据回流 → M10 包装，**全部完成并 merge 回 `develop`** |
| 代码量 | `src/forgeflow/` **55 个源文件**，mypy strict clean |
| 测试 | ForgeFlow **181 passed / 1 skipped / 5 deselected（online）**；上游 `src/openharness/` **0 个源文件被修改** |
| 服务 | FastAPI + PostgreSQL/Redis + Celery + SSE + Docker Compose + GitHub Actions CI |
| 评测 | 确定性本地策略基线完成率 **25%（2/8）**；Agent 驱动在线策略完成率见 §4 |

**核心结论**：平台主体按规格落地，上游边界干净（可核验的 0 修改 + `docs/UPSTREAM_MAP.md` 四栏），评测体系真实可复现。

## 2. 关键设计决策

1. **Adapter + 扩展点接入（ADR 0001）**：业务层只依赖 `EngineLike`/`RuntimeSession` 协议，`openharness.*` 类型不泄漏到 ForgeFlow 业务层；可注入 fake 做离线测试，也便于在线策略复用一个接缝。
2. **5 条接缝**：引擎（M1）、执行后端（M3）、质量门禁（M4）、Reviewer（M5）、评测策略（M8）——在线策略复用同一 `EvalStrategy` 协议，本地确定性策略与模型驱动策略同构可替换。
3. **状态机表驱动 + 幂等**：`transition(state,event)` 纯函数 + `TaskStateMachine.apply` 幂等 no-op，配合 `command_id` 幂等（API/Celery 重复投递不重复执行）。
4. **隔离执行默认 git worktree**：每个任务/评测案例一个独立 worktree，改动互不污染；命令结构化参数 + 超时 `taskkill /T /F` 进程树终止；路径越界校验（`PathEscapeError`）。
5. **质量门禁确定性优先**：5 个纯门禁（禁止路径/文件数/测试掩盖/密钥扫描/必需命令），硬门禁失败即任务失败——"能失败"是可评测的前提。
6. **Trace 全链路 + 脱敏 + 回流**：统一 `SpanEvent`，持久化前 `redact`；失败分类（pass/baseline/policy/error/**agent_failed**）让评测报告"只列平均分"变为"逐案例可解释"。

## 3. 踩过的坑（记录在案，供后续会话）

1. **editable 安装指向已删 worktree**：换 worktree 后 `import forgeflow` 失败 → `pip uninstall openharness-ai` + 删 `site-packages/openharness` + `pip install -e ".[dev,service]" --no-build-isolation`。
2. **测试文件 basename 冲突**：`test_adapter.py`/`test_registry.py` 与上游 `tests/` 冲突，改名 `test_plan_adapter.py`/`test_feedback_registry.py`。
3. **`mypy` plain 命令报模块重复**：editable + `py.typed` 需 `MYPYPATH=src ... --explicit-package-bases --python-version 3.11`。
4. **Windows 平台差异**：无符号链接权限（skip）、`taskkill /T /F` 进程树、`tzdata` 依赖、控制台中文乱码（CLI `--output` 写 UTF-8）。
5. **DeepSeek 规划 max_turns=6 不够**：在线垂直链路测试曾 `MaxTurnsExceededError`——在线策略把规划放宽到 25 轮、实现 40 轮、评审 8 轮，并加墙钟超时兜底（Agent 无超时会挂起，见 §3.8）。
6. **评测 worktree 冲突**：同一案例跨策略复用同一 slug 会互相污染 → 在线策略的 worktree slug 带 `(case, strategy, run-token)` 三要素。
7. **门禁读文件默认 GBK（中文 Windows）**：`QualityGateRunner._read_changed_contents` 用 `read_text()` 默认编码，Agent 写出含中文注释的 UTF-8 文件时抛 `UnicodeDecodeError` → 在线评测首轮 plan_gates 几乎全挂（raw 不走门禁读文件所以 8/8 通过）。修复为 `read_text(encoding="utf-8", errors="replace")` + 回归测试。
8. **Agent 无墙钟超时会挂死评测**：一次重跑卡在单个 plan_gates 案例 58 分钟（疑似 DeepSeek 请求挂起），进程最后被杀。修复：为规划/实现/评审三个模型阶段加墙钟超时（10min/15min/5min，`asyncio.wait_for`）+ 超时回归测试。

## 4. 评测（真实数字）

**基线**（确定性本地 `plan_gates`，无模型）：`default` 数据集（8 案例：6 bugfix + 2 verify）完成率 **25%（2/8）**——cart-001/002 通过，billing-001..006 因幂等 bug 测试失败判基线失败。存档 `evals/reports/2026-08-05-default-plan_gates.md`。

**在线**（Agent 驱动三策略，DeepSeek，真实调用，2026-08-05）：存档 `evals/reports/2026-08-05-online-default.md`。

| 策略 | 完成率 | 通过/总数 | Agent 未修复 | 平均Token | 平均工具失败 | 平均成本 | 平均耗时 |
|---|---|---|---|---|---|---|---|
| raw（直接修复） | **100%** | 8/8 | 0 | 13,240 | 0.88 | $0.072 | 30.3s |
| plan_gates（计划+门禁） | **75%** | 6/8 | 2 | 28,609 | 0.50 | $0.167 | 63.9s |
| plan_gates_reviewer（+只读评审） | **75%** | 6/8 | 2 | 27,741 | 0.75 | $0.158 | 83.3s |

- 6 个 billing 基线失败案例：raw 全部翻转为通过；plan_gates / plan_gates_reviewer 翻转 4 个，`billing-003`（负金额拒绝）与 `billing-005`（索引化重构）门禁失败未翻转。
- plan_gates_reviewer 中 `billing-005` 的修复被独立 Reviewer 拒绝（request_changes）——只读评审确实拦下了一次修改。
- **计划+门禁的代价与收益**：完成率从 raw 的 100% 降到 75%（约 2 倍 Token 成本），但平均工具失败从 0.88 降到 0.50 次/案例（**降低约 43%**）——在更安全的执行约束下用更少的无效工具调用换取了略低的原始通过率。
- **经验检索 before/after（P0-2）**：注入种子经验后 plan_gates 完成率 75% → **87.5%**（billing-003 被修复，billing-005 仍未过）——检索机制有效但非万能，见 `evals/reports/2026-08-05-online-default-retrieval.md` 与 `docs/EVALUATION.md` §3.5.2。

## 5. 局限与未完成

- **认证/登录**：OAuth 订阅流未在 ForgeFlow 层包装；当前在线评测走 API-key（DeepSeek）。
- **Docker 沙箱**：`settings.sandbox.docker` 未作为评测默认执行后端；compose `up` 需本机 Docker Desktop/WSL2 启动后验证（`config --quiet` 已通过）。
- **真实 PR 提交**：`DeliveryService.create_draft_pr` 仅允许测试仓库，未做真实 GitHub 远端提交。
- **模型后训练**：M9 数据回流只产出可溯源经验样本，**未声称做过模型训练**。
- **上游 14 个 Windows 预存失败**：fcntl/symlink/原子重命名等，非本项目引入，建议 Linux CI 复验。

## 6. 下一步

1. ✅ 在线评测报告已固化到 `docs/EVALUATION.md` §3.5（before/after 对比 + 三策略）。
2. ✅ `docs/RESUME.md` 已用真实数字填 `PROJECT_SPEC.md` §20 模板。
3. 可选：启动 Docker Desktop 验证 `docker compose up --build` 四服务；推送 `upstream-base-0.1.9` 标签；经验检索 before/after 对比实验（在线策略可跑，`retrieval_comparison` 上下文注入未接入）。
