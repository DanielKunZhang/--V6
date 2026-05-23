# Optionality Overlay 有限亏损表达层 SOP v1

更新日期：2026-05-23

## 定位

Optionality Overlay 不是第四套独立信号源，不是短线团队式 all-in 模块，也不是 V6 / V6AB / A股 Radar 的自动期权交易系统。

它只是三类已有研究来源的“有限亏损表达工具”：

1. 主仓 / 进攻价值投研究：估值、财报、产品周期、监管、关键事件窗口。
2. V6 / V6AB / V6-B：系统识别到强主线，但正股估值、拥挤度或波动结构不适合直接追高。
3. A股 Radar：只能做跨市场研究迁移，必须先在目标市场验证，不能把 A股主题直接映射成美股期权交易。

## 允许输出

每个候选只能输出三种结论之一：

| 输出 | 含义 | 可执行动作 |
|---|---|---|
| `NO_OPTION` | 期权表达不符合赔率、时效、流动性或纪律 | 不做，归档 |
| `WATCH_OPTION` | 有右尾线索，但证据、估值或事件窗口不足 | 加入观察，不交易 |
| `DEFINED_RISK_REVIEW` | 允许人工复核有限亏损结构 | 只允许人工审查，不自动下单 |

禁止输出 `BUY_OPTION`、`ALL_IN`、`AUTO_TRADE` 或任何等价表达。

## 入队来源

### 主仓 thesis 的事件窗口

例子：PDD 财报前后 thesis 重新验证；NVDA 财报后 thesis 上修但正股价格明显高于合理区间；AMZN / MSFT / CRCL 估值合理但事件波动很大；泡泡玛特业绩、海外验证、IP 生命周期关键节点。

要求：必须先完成或更新主仓估值 / thesis，Optionality 只能作为表达方式，不反过来驱动 thesis。

### V6 / V6AB / V6-B 强主线但正股表达不理想

例子：V6AB 识别 AI infra / HBM / 光模块等强主线，但正股估值和拥挤度不适合直接追高；V6-B / 美股 Radar 出现强证据主题，但不满足正股买入纪律。

要求：系统只能生成候选与复核提醒，不能自动交易期权，不能改变 V6AB 当前模拟盘 `V6AB_SIM_CANDIDATE_V2_DYNAMIC_B_SIZING`。

### A股 Radar 的跨市场研究迁移

A股没有美式个股期权表达，A股 Radar 也不是美股期权信号源。它只能产生主题研究线索、港股 / 美股 / ETF 映射候选、目标市场二次验证任务或 attack sleeve 候选记录。

要求：只有当目标市场也出现公司基本面、订单、财报、资金流或价格结构验证后，才允许进入 `WATCH_OPTION`。

## 强制风控字段

进入 `DEFINED_RISK_REVIEW` 前，必须写清：

1. `ticker`：标的。
2. `source_system`：来源系统，必须是 Core Thesis / V6AB / V6-B / A-share Radar Transfer 等。
3. `thesis`：为什么存在右尾。
4. `event_window`：事件窗口或复核日期。
5. `max_loss_plan`：最大可亏损金额或组合净值比例。
6. `invalidation`：什么发生就证明 thesis 错了。
7. `exit_plan`：盈利、亏损、时间价值衰减、事件结束后的退出规则。
8. `liquidity_check`：期权链流动性、价差、期限是否可接受。

缺任一字段，只能是 `WATCH_OPTION`，不能进入 `DEFINED_RISK_REVIEW`。

## 仓位纪律

Optionality Overlay 的设计目标是把“想追高正股”的冲动约束成有限亏损，而不是放大风险。

原则：

- 单笔必须 defined-risk。
- 最大亏损必须事前接受，不能事后补仓摊平。
- 不允许因为朋友团队、短线团队、社媒热度而跳过 thesis / max loss / exit plan。
- 不允许把 option premium 当成可以随意归零的彩票预算。
- 未形成 10-20 笔完整复盘样本前，不讨论半自动化，更不讨论自动化。

## Daily Email 接入

Daily email 只负责提醒：

- 哪些候选需要估值报告输出 Optionality Review。
- 哪些 `WATCH_OPTION` 需要补证据。
- 哪些 `DEFINED_RISK_REVIEW` 到达事件窗口，需人工检查 max loss / invalidation / exit plan。

Daily email 不负责下单、推荐 all-in、替代人工确认，也不改变 V6 / V6AB / A股 Radar 的原有交易规则。

## 复盘要求

每笔 `DEFINED_RISK_REVIEW` 后续必须记录是否执行、实际最大风险、进入时 thesis 是否清晰、是否因为 FOMO 进入、结果是否来自 thesis 验证，以及是否应进入长期规则。

这个复盘样本是未来是否升级 Optionality Overlay 的唯一依据。
