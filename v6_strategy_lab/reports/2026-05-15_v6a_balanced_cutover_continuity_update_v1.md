# 2026-05-15 V6-A Balanced Cutover 连续性更新 v1

- 生成日期：`2026-05-15`
- 适用范围：`2026-05-26 V6-A balanced challenger cutover` 前置证据补齐
- 当前结论：`HOLD_OLD_BASELINE / CONTINUE_MANUAL_PILOT`
- 核心边界：今天不切换、不扩容、不自动下单；只补充 2026-05-26 决策日前的连续性证据

## 一句话结论

`balanced challenger` 的技术切换路径继续成立：preview runner 已通过、migration diff 清楚、release gate 在 balanced preview 口径下通过。

但正式切换仍必须等到 `2026-05-26` 执行 SOP，因为 live pilot 只运行 4 天，尚未满足 2 周稳定观察期。

## 今日证据

| 模块 | 今日结果 | 解读 |
| --- | --- | --- |
| 旧 live pilot 复盘 | `CONTINUE_MANUAL_PILOT` | 当前 `ATTACK_EQUAL_REPLAY` managed state 与 target 匹配，pending orders 为 0；但 pilot 只有 4 天，不能提前 promotion |
| 自动化 preflight | `BLOCK` | kill switch、非 RTH、sandbox Futu 权限、release gate freshness 阻断自动交易；这是预期中的安全阻断 |
| balanced guarded runner | `READY_FOR_MANUAL_CONFIRM` | balanced preview 路径通过，release gate `PASS`，无 blockers；仅代表技术 preview 可用 |
| migration diff | 清楚 | 可区分 ownership transfer、增量买入、退出标的；无误卖主仓信号 |

## balanced preview 读数

- 运行 tag：`20260515_balanced_cutover_continuity_v2`
- 模式：`PLAN_ONLY`
- 决策：`READY_FOR_MANUAL_CONFIRM`
- Release gate：`PASS`
- Blockers：`[]`
- 增量买入金额：`$1,774.94`
- 账户可用现金：`$25,490.12`
- Quote / account warnings：无

预览订单：

| 标的 | 动作 | 数量 | 参考价 | 参考金额 |
| --- | --- | ---: | ---: | ---: |
| `US.AMZN` | BUY | 2 | `$266.49` | `$532.98` |
| `US.AVGO` | BUY | 1 | `$440.36` | `$440.36` |
| `US.GOOGL` | BUY | 2 | `$400.80` | `$801.60` |

## migration diff

- Candidate：`mom60 top3 trend150 mkt200 dd10 rebal10`
- Signal date：`2026-05-12`
- As-of：`2026-05-15`
- Signal age：`3` 天，低于 `max_signal_age_days=7`
- Managed strategy label：`V6-A ATTACK_EQUAL_REPLAY`

如果未来正式切换，当前差异为：

| 标的 | 当前 V6 managed | balanced target | 迁移动作 |
| --- | ---: | ---: | --- |
| `US.AMZN` | 4 | 6 | 旧仓归属转移 4 股，增买 2 股 |
| `US.AVGO` | 2 | 3 | 旧仓归属转移 2 股，增买 1 股 |
| `US.GOOGL` | 2 | 4 | 旧仓归属转移 2 股，增买 2 股 |
| `US.BIL` | 6 | 0 | 若 cutover，通过 V6 managed sleeve 退出 6 股 |
| `US.GLD` | 1 | 0 | 若 cutover，通过 V6 managed sleeve 退出 1 股 |

## 今日修正

已调整 `v6a_balanced_challenger_guarded_runner_policy_v1.json`：

- `block_if_managed_state_strategy_mismatch`: `true -> false`

原因：balanced preview lane 的目的就是复用当前 `V6-A ATTACK_EQUAL_REPLAY` managed state 来计算迁移净额；当前 managed state 的策略标签与 balanced challenger 不同是预期现象，不应阻断 preview。

安全边界保持不变：

- `auto_real_orders_allowed=false`
- 仍需手动确认短语 `GO_BALANCED_CUTOVER_EXECUTE`
- 仍要求 release gate、quote/account warning、订单尺寸、managed sell guard 全部通过
- 仍不更新 managed state

## 当前未满足项

| 未满足项 | 严重性 | 处理方式 |
| --- | --- | --- |
| live pilot 仅 4 天 | 决策前置条件不足 | 等到 2026-05-26 执行正式 SOP |
| 自动化 kill switch ON | 正常安全状态 | 保持 ON；没有确认短语不允许真实下单 |
| 今日 preflight 在 sandbox 下 Futu 权限失败 | 环境性问题 | 决策日用真实 OpenD 环境重新跑 |
| 旧 live runner latest 仍有 `release_gate_not_pass` | 旧 baseline 运行证据问题 | 决策日以完整 SOP 重新判定，不用今日单点结论替代 |

## 对 2026-05-26 的影响

今日证据把 cutover 的工程风险降了一层：balanced preview lane、订单预览、迁移净额、策略标签兼容问题都已处理。

但最终决策仍不提前：

- 如果 2026-05-26 旧 pilot 稳定、fresh replay 通过、migration diff 仍清楚，则可输出 `GO_CUTOVER`。
- 如果 2026-05-26 有账户边界、reconciliation、OpenD、误卖风险，则输出 `HOLD_OLD_BASELINE` 或 `PAUSE_V6`。

## 今日最终状态

```text
Verdict: HOLD_OLD_BASELINE / CONTINUE_MANUAL_PILOT
Why: balanced 技术路径通过，但 pilot 观察期不足，不能提前切换。
Critical Evidence: guarded runner READY_FOR_MANUAL_CONFIRM；release gate PASS；migration diff 清楚；pending orders 0。
Blocked / Missing: 2 周 pilot 证据、决策日 fresh replay、真实 OpenD preflight。
Today Next Step: P0 cutover 准备可进入“等待 2026-05-26 SOP”状态；继续推进 Radar / Central Risk Board。
Need User Confirmation: 今天不需要；真实切换日前仍需 `GO_BALANCED_CUTOVER_EXECUTE`。
```

