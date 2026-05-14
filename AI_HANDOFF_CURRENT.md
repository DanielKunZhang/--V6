# AI Handoff Current Snapshot

- Last updated: 2026-05-14
- Purpose: 给新接入的 AI 快速继承当前工作，避免重新翻完整聊天记录。

## 先说结论

聊天平台里的完整对话不应被当作长期记忆源。长期可继承的上下文应该沉淀在本地文件和 GitHub 中。

新 AI 接入时，优先读取这些文件：

1. `/Users/zhangkun/WorkBuddy/程序化/量化程序/AI_HANDOFF_CURRENT.md`（本文件）
2. `/Users/zhangkun/WorkBuddy/程序化/量化程序/AI_COLLAB_LOG.md`（⭐ 双向协作日志，最近的决策和变更都在这里）
3. `/Users/zhangkun/WorkBuddy/程序化/量化程序/V6_STRATEGY_LAB.md`
4. `/Users/zhangkun/WorkBuddy/程序化/量化程序/MICRO_FUTURES_LAB.md`（若接手 micro 期货独立实验线）
5. `/Users/zhangkun/WorkBuddy/程序化/量化程序/V6_PRODUCTIONIZATION_SOP.md`
6. `/Users/zhangkun/Desktop/AI个人投资公司/知识库_v1/README.md`
7. `/Users/zhangkun/Desktop/AI个人投资公司/投资系统全景图_SYSTEM_OVERVIEW.html`
8. `/Users/zhangkun/WorkBuddy/程序化/量化程序/AI_INVESTMENT_COMPANY_12M_UPGRADE_ROADMAP.md`
9. `/Users/zhangkun/WorkBuddy/程序化/量化程序/CENTRAL_RISK_BOARD_SPEC.md`

## AI 协作同步机制

Claude 和 GPT 通过 `AI_COLLAB_LOG.md` 共享协作状态，避免知识分叉。

同步规则：
- Claude：每次会话结束前将关键产出写入 `AI_COLLAB_LOG.md`
- GPT 产出：用户运行 `python collab_sync.py add-gpt "内容"` 追加
- GPT 读取：每次新会话时上传 `AI_COLLAB_EXPORT_FOR_GPT.md`（运行 `python collab_sync.py export` 生成）

collab_sync.py 工具位置：`/Users/zhangkun/WorkBuddy/程序化/量化程序/collab_sync.py`

## 投资系统当前定位

用户目标是建设 AI 一人投资公司，同时做：

- 价值投资主仓：好生意、好人、好价格，集中但有仓位纪律。
- 量化投资 V6：美股动量/防守切换策略，先小额实盘 pilot。
- Radar / V6-B：动态机会池，不直接交易，先做回测和 point-in-time 验证。
- Micro Futures Lab：`MNQ / MES` 微型期货独立实验线，目标是验证未来是否能成为小资金高弹性进攻 sleeve，但当前不属于 V6。

当前组合治理重点：

- 未来 3-6 个月主要任务是把组合仓位调顺。
- PDD 从约 20% 往 10%-12% 降。
- 腾讯要纳入 RSU 和港股通后的真实总敞口管理。
- Radar 不再用情绪化彩票思路，未来更偏 V6-B 动态资源池。
- Micro Futures Lab 与 V6 分开记账、分开评估、分开验收，不能混算绩效。

## V6 当前状态

V6 的长期形态：

```text
V6 = V6-A baseline + V6-B 动态资源池 + Allocator 风控分配 + 报告/复盘/kill switch
```

当前已完成：

- V6-A 真实账户 5,000 USD 手动 pilot 已启动。
- V6-A 使用 `ATTACK_EQUAL_REPLAY` baseline。
- V6-A 有独立 real managed state，不能误卖长期价值投资持仓。
- 每日中文日报已启用，定时任务每天北京时间 08:30 运行。
- 每日任务只做 reconciliation、plan-only 检查、发日报，不自动下单。
- 已补三份正式治理工件：
  - `v6_strategy_lab/reports/2026-05-13_v6a_execution_quality_board.md`
  - `v6_strategy_lab/reports/2026-05-13_v6b_supply_chain_diffusion_map_v1.md`
  - `v6_strategy_lab/reports/2026-05-13_v6_allocator_governance_spec_v1.md`

V6-A real managed state：

```text
backtest_results/v6a_state/v6a_managed_positions_real_281756481449956811.json
```

截至 2026-05-12，该 state 记录：

```text
US.AMZN  4
US.AVGO  2
US.BIL   6
US.GLD   1
US.GOOGL 2
pending_orders: 0
```

真实 pilot 初始投入约 3,714.11 USD。截至 2026-05-12 12:22，当前市值约 3,693.63 USD，浮亏约 20.45 USD，约 -0.55%。

## V6 运行规则

当前 pilot 周期暂定 2 周。

这 2 周内：

- 日报提醒，不自动交易。
- 如果出现 BUY/SELL 调仓信号，用户确认后再执行。
- 执行前必须跑 guarded precheck。
- 执行后必须立刻跑 reconciliation。

V6-A 退出机制：

- 策略层有退出：目标权重变化、标的掉出、risk-off 防守切换。
- 工程层会生成 SELL。
- SELL 只能卖 V6 managed state 记录的仓位。
- 当前没有开启无人值守自动 SELL。

## 全投资体系早间监控（morning_brief）

`morning_brief.py` 是覆盖整个投资体系的早间运营入口，**不只是 V6**。

功能覆盖：
- [V6] reconciliation 状态 + managed positions + 换仓信号
- [价值投资] 全资产口径持仓权重监控（超目标/建仓中/正常 三色告警）
- [估值] 事件日历（events_calendar.json）
- [Radar] K线额度状态
- [待办] AI_COLLAB_LOG.md 近 14 天待办

持仓数据源（全资产口径 ~38.9万USD）：
```text
/Users/zhangkun/Desktop/AI个人投资公司/26年阶段性组合策略计划.html
```
用户定期手动更新此文件，morning_brief 自动解析 `<section id="targets">` 表格。
包含：富途账户 + 腾讯RSU + A股 + 港股通。

运行：
```bash
python3 morning_brief.py              # 生成 + 发送邮件至 quanyi_zk@163.com
python3 morning_brief.py --no-email   # 只打印，不发邮件
```

launchd 任务（北京时间 09:00 自动运行）：
```text
com.dingcle.morning-brief
plist: /Users/zhangkun/Library/LaunchAgents/com.dingcle.morning-brief.plist
```

事件日历维护：
```text
/Users/zhangkun/WorkBuddy/程序化/量化程序/events_calendar.json
```

## 双 AI 对照锁定的 V6 优化方向（2026-05-12）

Claude 和 GPT 独立分析交叉验证后锁定，作为后续所有 V6 工程实现的行动纲领：

1. **V6-A 执行质量和真实摩擦验证做满** — 收集真实滑点、换手、摩擦数据，建立可信 live OOS 记录
2. **V6-B 做成真正的动态 universe refresh engine** — 不只是 Radar 清单，要有完整回测+OOS+可交易性核查
3. **扩展低相关 sleeve / challenger** — 不只押一个 alpha 来源，机构强大来自多因子低相关组合
4. **Allocator + Regime 做成正式治理层** — 负责权重分配，不负责追涨，必须有 regime 依据

> 定位共识：做"在某个细分中频方向里很强"的系统，不默认全市场全周期顶级大厂模型。真正护城河是 **Engine + Universe + Allocator + 风控工程 + 协作知识库** 整套持续迭代系统。详见 `V6_STRATEGY_LAB.md` 的"双 AI 对照锁定"章节。

## 2026-05-14 方向升级补充

当前总路线已进一步固定：

- 不是追求“像 Point72 一样什么都做”
- 而是做成“少数领域极强、流程像机构、风险受控、可持续复盘”的小型投资公司

新增两份长期方向工件：

- `AI_INVESTMENT_COMPANY_12M_UPGRADE_ROADMAP.md`
- `CENTRAL_RISK_BOARD_SPEC.md`

后续 AI 在讨论系统升级时，应默认服从这两个方向文件。

## V6 近期优先级（2026-05-12 确认）

以下 4 件事是当前 V6 迭代重点（Claude + GPT 共同确认）：

1. **换手率测算**：replay 历史信号，统计年化换手率和单次换仓成本
2. **Pilot 第 2 周末执行质量复盘**（2026-05-26）：评估滑点/舍入/成交时间
3. **K 线额度恢复后启动 V6-B standalone 回测**（~2026-06-01）：AMD/MU/TSM/ANET/WDC/INTC
4. **文档化 4 个自动化前置场景**（见下节）

今天已把这 4 件事背后的治理层先补齐到文档：

- V6-A：执行质量看板和 2026-05-26 go/no-go 口径
- V6-B：供应链扩散地图 v1 和候选优先级
- Allocator：正式治理规则、hard block 和人工 override 边界

## V6 自动化前置场景（待文档化）

在 V6 进入无人值守自动执行之前，以下 4 个异常场景需要明确处理方案：

| 场景 | 触发条件 | 期望行为 |
|------|---------|---------|
| OpenD 挂了 | guarded runner 无法连接 | 跳过执行，告警邮件，次日重试 |
| 订单未成交 | 下单后 N 分钟无成交 | 发告警，等待人工处理，不重复下单 |
| 账户余额不足 | 可用资金不够覆盖买入 | 仅执行有资金覆盖的 SELL，BUY 跳过并告警 |
| 滑点超预期 | 成交价偏离信号价 > X% | reconciliation 标记，日报显示，不自动回撤 |

## 常用 V6 命令

V6-A plan-only 检查：

```bash
python3 v6a_guarded_runner.py --tag v6a_check_YYYYMMDD
```

V6-A 真实手动执行：

```bash
python3 v6a_guarded_runner.py \
  --tag v6a_real_execute_YYYYMMDD \
  --execute-real \
  --confirm EXECUTE_V6A_REAL_5000
```

真实订单 reconciliation：

```bash
python3 v6a_real_reconciliation.py --tag v6a_reconcile_YYYYMMDD
```

生成日报并发送：

```bash
python3 v6_reporting.py --period daily --send-email
```

每日自动 runner：

```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 v6_daily_report_runner.py
```

launchd 任务：

```text
com.dingcle.v6.daily-report
```

任务时间：北京时间 08:30。

## GitHub

V6 repo：

```text
git@github-special:DanielKunZhang/--V6.git
```

当前分支：

```text
v6-governance-and-reporting
```

最近关键提交：

```text
929a20d fix: use project Python for V6 daily launch agent
638344b feat: localize V6 reports and add daily plan check
dc58870 feat: add V6 daily report automation
3473776 feat: add V6A sim managed-state loop
```

## 新 AI 接入 SOP

新 AI 接入后先做：

1. 读取本文件。
2. 读取 `V6_STRATEGY_LAB.md` 和 `V6_PRODUCTIONIZATION_SOP.md`。
3. 读取 `26年阶段性组合策略计划.html` 和 `投资系统全景图_SYSTEM_OVERVIEW.html`。
4. 检查 `git status --short`，不要改动无关 dirty files。
5. 查询 V6 real managed state，不要用账户总持仓替代 V6 持仓。
6. 所有真实交易前必须先给用户展示 precheck 结果，并等待明确确认。

## 严禁事项

- 不要把富途真实账户总持仓当成 V6 持仓。
- 不要自动卖出长期价值投资仓位。
- 不要把 V6-B 当成已经验证过的实盘策略。
- 不要因为单日盈亏修改 V6 engine。
- 不要把聊天记录当作唯一知识源，关键结论必须落地到文件。
