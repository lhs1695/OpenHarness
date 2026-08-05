# 评测报告 — default-run
- 实验 ID：`exp_d902f636`
- 数据集：`default` v2026-08-05
- 策略：plan_gates
- 配置版本：1.0
- 创建时间：2026-08-05T12:37:28.238183+00:00

## 汇总指标（按策略）
| 策略 | 完成率 | 通过/总数 | 基线失败 | 策略失败 | Agent 未修复 | 平均Token | 平均工具失败 | 平均成本 | 平均耗时 |
|---|---|---|---|---|---|---|---|---|---|
| plan_gates | 75.00% | 6/8 | 0 | 0 | 1 | 23726.6 | 1.0 | $0.134768 | 186234.0ms |

## 失败案例
- `billing-003` [plan_gates] **Agent 未修复/被拒（模型跑完后门禁或评审未通过）** — hard gates failed: ['required_commands']
- `billing-004` [plan_gates] **意外错误** — _AgentPhaseTimeout: agent turn exceeded 900s wall-clock budget