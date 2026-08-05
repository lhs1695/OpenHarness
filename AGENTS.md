# ForgeFlow 开发规则（Codex）

ForgeFlow 是基于 OpenHarness 的研发任务交付与质量闭环平台。详细规格见 `PROJECT_SPEC.md`，本文件只放必须遵守的简短规则。

## 开始工作前

- 阅读 `PROJECT_SPEC.md`。
- 阅读 `docs/ARCHITECTURE.md`、`docs/PLANS.md`、`docs/UPSTREAM_MAP.md`、`docs/HANDOFF.md`（如存在）。
- 一次只做一个已批准里程碑，使用独立 Worktree。

## 规则

- 保留上游 License 与归属；`docs/UPSTREAM_MAP.md` 维护"复用/适配/扩展/修改"四栏，明确区分上游能力与 ForgeFlow 贡献。
- 优先使用 Adapter 和扩展点接入，避免侵入式修改上游；确需修改的点以 `patches/` 留存并在 ADR 声明。
- 不进行无关重构；不静默修改公共接口。
- 新行为必须有测试；使用明确异常类型、类型标注和结构化日志。
- 禁止编造测试、性能、延迟、成本或质量结果。
- 禁止绕过 Workspace、命令、审批或 Secret 保护。
- 里程碑结束前更新 `docs/HANDOFF.md`。
- 规格与真实源码冲突时停止并报告，不擅自改设计。

详细协作规范见 `PROJECT_SPEC.md` 第 16 节。
