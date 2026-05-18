# Review Cadence Policy

目的：把投资系统的复盘节奏固定下来，Daily Board 每天只提醒该做的事，避免主仓被短线噪音污染，也避免 Radar/V6 漏复盘。

## 总原则

- Daily Board 是唯一正式待办入口。
- `events_calendar.json` 是唯一正式日期事件源。
- `morning_brief.py` / `central_risk_board.py` 负责把事件、周期规则、决策日志合并成“今日动作清单”。
- 核心价值仓不做每日复盘，只做事件驱动复盘。

## 复盘节奏

| 系统 | 复盘频率 | Daily Board 提醒方式 | 触发关键词 |
|---|---|---|---|
| A股 Radar | 训练期交易日日更 | 交易日低优先级提醒；有事件时高优先级 | `复盘 A股Radar` |
| A股 Radar 新候选扫描 | 每周五 | 周五低优先级提醒；只生成 AddToRadar 候选 | `扫描 A股Radar 新候选` |
| V6-A | 每日自动巡检，人工节点复盘 | 异常/节点事件进入事件日历 | `复盘 V6-A` |
| V6-B / 美股 Radar | 周更或事件复盘 | 周五低优先级提醒；earnings/信号触发时事件提醒 | `复盘 V6-B` |
| 主仓价值投资 | 事件驱动，不日更 | 财报、估值触发、thesis 变化、仓位偏离时提醒 | `复盘 PDD` / `复盘 NVDA` 等 |
| X Radar | 每日可扫描，不等于复盘 | 交易日若未整理，低优先级提醒 | `X Radar 扫描` |
| Friend Alpha | 样本到门槛再复盘 | 20/50 样本时提醒 | `复盘 Friend Alpha` |

## 当前 Daily Board 已实现规则

`morning_brief.py::collect_workflow_actions()` 当前会合并：

- `events_calendar.json` 中未来 3 天事件
- `decision_log.csv` 中到期或临近的 PLANNED / EXECUTED / CLOSED 条目
- Friend Alpha 20/50 样本门槛
- A股 Radar 交易日日更提醒
- A股 Radar 周五新主题/新标的扫描提醒
- 美股 Radar / V6-B 周五周复盘提醒
- 交易日 X Radar 扫描提醒
- 非交易日维护提醒

## 禁止事项

- 不把主仓每日涨跌做成每日复盘任务。
- 不把 X Radar 内容直接变成交易动作。
- 不把 A股 Radar 的短线逻辑用于腾讯、PDD、NVDA 等主仓。
- 不绕过 Daily Board 在子系统里私自维护正式待办。
- A股 Radar 周五扫描默认结论是 `NoNewCandidate`；不是每周必须新增，只有满足主题共振、量价强度和相对优势标准时才输出 `AddToRadarCandidate`。
