# 评测报告 — online-default-2026-08-05
- 实验 ID：`exp_dd8d1760`
- 数据集：`default` v2026-08-05
- 策略：raw, plan_gates, plan_gates_reviewer
- 配置版本：1.0
- 创建时间：2026-08-05T07:33:24.777301+00:00

## 汇总指标（按策略）
| 策略 | 完成率 | 通过/总数 | 基线失败 | 策略失败 | Agent 未修复 | 平均Token | 平均工具失败 | 平均成本 | 平均耗时 |
|---|---|---|---|---|---|---|---|---|---|
| raw | 100.00% | 8/8 | 0 | 0 | 0 | 13240.0 | 0.88 | $0.071533 | 30349.4ms |
| plan_gates | 75.00% | 6/8 | 0 | 0 | 2 | 28608.9 | 0.5 | $0.166870 | 63913.8ms |
| plan_gates_reviewer | 75.00% | 6/8 | 0 | 0 | 2 | 27740.6 | 0.75 | $0.157719 | 83273.0ms |

## 失败案例
- `billing-003` [plan_gates] **Agent 未修复/被拒（模型跑完后门禁或评审未通过）** — hard gates failed: ['required_commands']
- `billing-005` [plan_gates] **Agent 未修复/被拒（模型跑完后门禁或评审未通过）** — hard gates failed: ['required_commands']
- `billing-003` [plan_gates_reviewer] **Agent 未修复/被拒（模型跑完后门禁或评审未通过）** — hard gates failed: ['required_commands']
- `billing-005` [plan_gates_reviewer] **Agent 未修复/被拒（模型跑完后门禁或评审未通过）** — reviewer not approved (verdict=request_changes, blockers=0)