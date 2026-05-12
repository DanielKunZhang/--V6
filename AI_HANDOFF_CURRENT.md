# AI Handoff Current Snapshot

- Last updated: 2026-05-12
- Purpose: 给新接入的 AI 快速继承当前工作，避免重新翻完整聊天记录。

## 先说结论

聊天平台里的完整对话不应被当作长期记忆源。长期可继承的上下文应该沉淀在本地文件和 GitHub 中。

新 AI 接入时，优先读取这些文件：

1. `/Users/zhangkun/Desktop/AI个人投资公司/投资系统全景图_SYSTEM_OVERVIEW.html`
2. `/Users/zhangkun/Desktop/AI个人投资公司/26年阶段性组合策略计划.html`
3. `/Users/zhangkun/Desktop/AI个人投资公司/知识库_v1/README.md`
4. `/Users/zhangkun/Desktop/AI个人投资公司/知识库_v1/00_System/总索引.md`
5. `/Users/zhangkun/WorkBuddy/程序化/量化程序/V6_STRATEGY_LAB.md`
6. `/Users/zhangkun/WorkBuddy/程序化/量化程序/V6_PRODUCTIONIZATION_SOP.md`
7. `/Users/zhangkun/WorkBuddy/程序化/量化程序/V6_GITHUB_AND_REPORTING_SOP.md`
8. `/Users/zhangkun/WorkBuddy/程序化/量化程序/AI_HANDOFF_CURRENT.md`

## 投资系统当前定位

用户目标是建设 AI 一人投资公司，同时做：

- 价值投资主仓：好生意、好人、好价格，集中但有仓位纪律。
- 量化投资 V6：美股动量/防守切换策略，先小额实盘 pilot。
- Radar / V6-B：动态机会池，不直接交易，先做回测和 point-in-time 验证。

当前组合治理重点：

- 未来 3-6 个月主要任务是把组合仓位调顺。
- PDD 从约 20% 往 10%-12% 降。
- 腾讯要纳入 RSU 和港股通后的真实总敞口管理。
- Radar 不再用情绪化彩票思路，未来更偏 V6-B 动态资源池。

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
