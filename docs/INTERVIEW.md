# INTERVIEW — 20 个面试问题（含答题方向）

> 面向 Python 后端 / Agent 工程岗位。答题时强调：上游 vs 个人贡献边界、确定性优先、真实评测不编造。

## 架构与集成

1. **ForgeFlow 解决什么业务问题？为什么不从零写 Agent？**
   研发任务规范化交付 + 质量闭环；Agent 基础设施（循环/工具/记忆）OpenHarness 已有，重写是浪费且难维护。
2. **"复用而非重写"具体怎么落地？**
   `src/forgeflow/` 全部新增，`src/openharness/` 零改动；通过 5 条无侵入接缝（`render_event`/`submit_message`、`ToolRegistry`、`AgentDefinition`、`SessionBackend`、Hooks）接入。
3. **为什么把业务层与上游隔离？**
   `integrations/openharness/` 是唯一 import 上游内部类的地方；业务层只见 ForgeFlow 类型，便于 Mock、换 Provider、上游可同步。
4. **适配层的最小接口是什么？怎么测？**
   `OpenHarnessAdapter.run_plan(task, engine)` 用注入的 `EngineLike`；单测注入 FakeEngine 产 `StreamEvent`，无需真实模型。
5. **为什么事件流选 `StreamEvent` 而不是自己再造？**
   上游已含模型/工具/Token 事件（`engine/stream_events.py`），`render_event` 回调即可零侵入消费，避免重复造轮子。

## 状态机与幂等

6. **状态机为什么是纯函数 + 表驱动？**
   `transition(state, event)` 无 I/O、合法转移用表定义；调用方负责副作用，便于单测与持久化。
7. **"同一命令重复执行不重复改变状态"怎么实现？**
   `TaskStateMachine.apply` 记录上一条 `(from, event, to)`；同事件再发且状态未变 → 幂等 no-op。
8. **取消一个长任务怎么保证真停？**
   编排器持有 asyncio 任务，`cancel` → `task.cancel()`；`_run` 捕获 `CancelledError` 置 `CANCELLED`；执行层 `taskkill /T /F` 杀进程树。
9. **审批幂等怎么做的？**
   `ApprovalManager.resolve` 以 approval_id 为键，首次解决后重复/冲突返回同一结果，不重复审计。
10. **超预算怎么处理？**
    `budgets.check_budget` 五维（步数/模型/工具/Token/时长）→ 超限状态机进 `BUDGET_EXCEEDED` 保存现场。

## 评测与数据回流

11. **评测为什么优先确定性指标？**
    完成率/测试通过率/禁止路径等可由真实结果算出；LLM Judge 只作补充（计划合理性等），避免不可复现的"漂亮数字"。
12. **"基线失败"和"策略失败"的区别？**
    基线失败=仓库测试未通过、未施加修复（正确信号，需 Agent 修复后翻转为通过）；策略失败=禁止路径等门禁真实违规。
13. **实验如何保证可重复、配置可追溯？**
    `ExperimentConfig` 带 `config_version` + `dataset_version`；`EvalRunner` 对同一数据集+策略矩阵结果一致（测试断言）。
14. **数据回流管道是什么？样本怎么溯源？**
    Trace → 脱敏 → 切分（按模型轮次）→ 成功/失败分类 → 偏好对 → `ExperienceSample`（含 task_id/run_id/provenance）。
15. **"历史经验检索前后"对比实验怎么做？**
    同一策略带/不带检索上下文跑同一数据集，比较完成率；`retrieval` 提供关键词重叠检索 + 上下文注入。诚实声明：尚未上线 Agent 驱动策略，未声称已后训练。

## 安全

16. **路径越界怎么防？**
    `resolve_workspace_path` 先 `resolve()` 绝对路径再校验是否在工作区根内；`..`、外部绝对路径、符号链接指向外部都抛 `PathEscapeError`。
17. **Secret 如何不落库？**
    `trace.redaction` 在持久化前对 span 摘要/metadata 递归脱敏；`secret_scan_gate` 作为硬门禁扫改动文件。
18. **Reviewer 凭什么保证只读？**
    工具白名单只含 `read_file/glob/grep/lsp` 等（无 bash/write/edit）+ PLAN 权限模式；在线真实 Review 已验证。

## 工程与边界

19. **你踩过哪些坑？**
    Windows 环境：mcp 2.x 破坏测试、tzdata、`ANTHROPIC_BASE_URL` 污染 provider 检测、editable 安装指向已删 worktree、`git diff HEAD` 不显示新文件、pytest basename 冲突、Windows 控制台中文乱码。
20. **哪些是你没做的（边界）？**
    V1 不做：认证、Docker 沙箱（V2）、真实 GitHub Draft PR 提交、模型微调、Kubernetes、自动合并。诚实说明，避免夸大。
