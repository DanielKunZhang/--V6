# V6AB Mainline Risk Skill v1

日期：2026-05-22

## 定位

`v6ab_mainline_risk_skill.py` 是 V6AB 主线识别系统的风控与入场质量层。

它吸收的是短线 AI skills 报告里的方法论，不吸收任何单票结论。核心目标是避免系统只识别“主线正确”，却忽略“主线是否已经拥挤、赔率是否已经透支、公司在产业链中是否只是弱卡位”。

## 输入

- V6AB evidence ledger
- 本地价格缓存
- 主题定义中的 proxies / stocks
- evidence summary 中的估值、事件、供应链、客户集中、内部人、叙事透支等文本线索

## 输出字段

- `fact_precision_score`：事实精度。财报、订单、SEC、历史深度和机构验证高于纯叙事。
- `position_quality_score`：产业链卡位质量。上游瓶颈、定价权、平台、订单、认证加分；供应商依赖、客户集中、替代风险、烧钱、内部人减持扣分。
- `crowding_score`：拥挤度。主题内标的短中期涨幅、极端 drawup、YTD/叙事拥挤文本线索共同决定。
- `valuation_payoff_risk_score`：估值与赔率风险。估值过高、需要回调、叙事透支、目标价穿越等线索加分。
- `event_risk_score`：事件风险。财报、指引、订单、利用率、warrant、客户砍单等 binary event 线索加分。
- `payoff_risk_score`：拥挤、估值、事件风险合成。
- `entry_quality_score`：主线强度、事实精度、产业链卡位和赔率风险合成后的入场质量观察分。
- `entry_quality_action`：研究动作标签。

## 动作标签

- `BOOST_ELIGIBLE`：主线强、事实/卡位较好、赔率未明显透支。
- `WATCH`：有主线或事实基础，但还不够强。
- `CAPPED_BOOST_ONLY`：方向可能对，但赔率/拥挤/事件风险偏高，只能考虑 capped exposure。
- `RISK_REVIEW`：主线强但赔率风险或卡位问题过高，需要人工风险复核。
- `NO_ENTRY_EDGE`：没有足够入场优势。

## 边界

当前 v1 只输出研究诊断，不改变：

- `theme_allowlist`
- `boost_allowlist`
- `override_allowlist`
- V6AB paper sim

任何把该 skill 变成 gate 的尝试，必须先跑：

- PIT replay
- PIT classifier bridge backtest
- V2 comparison
- attribution
- promotion gate
- 2020 / 2022 / 2024-2026 stress periods

## 原则

V6AB 的目标不是追热点，而是识别当期绝对主线，并在赔率尚未明显透支、事实精度足够、产业链卡位合理时下注。

强主线 + 高事实精度 + 好卡位 + 赔率未透支，才有资格 BOOST。

强主线 + 高拥挤/估值透支/事件风险，只能 WATCH 或 capped BOOST。
