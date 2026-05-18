# AI 工作同步 CURRENT

- Last updated: `2026-05-18 17:18:23`
- Canonical file: `/Users/zhangkun/WorkBuddy/程序化/量化程序/AI_WORK_SYNC_CURRENT.md`
- 用途：这是唯一对外同步文件。给 GPT、Claude 或任何新 AI 时，优先上传/读取这一份。

## 使用规则

- 新 AI 先读本文件，不需要同时打开完整聊天记录。
- `AI_COLLAB_LOG.md` 是底层流水账，本文件是当前可执行摘要。
- 每次重要工作结束后，运行：

```bash
python3 collab_sync.py export-current
```

- 如果新增重大决策，先写入 `AI_COLLAB_LOG.md`，再刷新本文件。
- 如果投资系统文档有新的主线进展，也应同步到本文件。

## 当前 AI 协作分工

- `GPT`：负责方向、边界、原则、优先级、最终判断，以及把用户真实目标函数制度化。
- `Claude`：更适合工程执行、跑数、报告生成、查错和批判性审查。
- `高层判断规则`：Claude 对“根本冲突 / 方向偏离 / 投资哲学冲突”等高层判断不能直接作为最终结论，必须回到用户目标函数和主从关系，由 GPT 侧做最终解释和制度化。
- `协作口径`：Claude 负责挑战系统风险；GPT 负责判断这些风险是否构成方向偏离；用户最终确认目标函数。

## 当前最新系统同步

# 2026-05-16 系统工作同步：给其他 AI 冷启动

- 生成时间：`2026-05-16 14:09 CST`
- 用途：把今天关于 Radar / V6 / 文档体系的关键决策和落地结果同步给其他 AI，便于冷启动接手
- 当前主线：6月1日历史 K 线额度刷新前，先完成不依赖历史数据的系统建设

## 1. 用户当前投资系统目标

用户希望搭建一个“小型 AI 个人投资公司”，核心不是追求朋友短线团队那种极端收益，而是在可控风险下尽可能提高长期复利。

当前系统定位：

| 模块 | 角色 |
| --- | --- |
| 主仓价值投资 | 长期底盘，学习巴菲特/芒格/段永平，避免毁掉生活 |
| V6 | 相对安全地拉高组合年化收益，作为规则化资本池 |
| Radar | 发现市场主线、二阶/三阶扩散机会，提供进攻候选 |
| Overlay / 期权 | 只做小额、可全亏、验证后逐步制度化 |
| Central Risk Board | 全系统总闸门，决定能否扩容、交易或只研究 |

重要原则：

- 系统必须服务长期复利，而不是情绪化追涨。
- 每次新增功能都要评估是否符合主线、是否有系统增益、是否增加复杂度。
- 用户讨厌主目录混乱，支撑文档必须集中在 `系统优化升级依据/`。
- 所有文档默认中文。

## AI 核心长期复利候选池：给 Claude 初筛和估值

用户新增明确目标：希望在 AI 大爆发时代找到一只或少数几只类似“当年 AAPL 之于段永平”的长期核心复利标的，目标不是短线 AI 热点，而是能长期持有、吃长期大复利的高质量资产。

估值框架已升级为 `AI-Core SOP v2.6`：

`/Users/zhangkun/Desktop/AI个人投资公司/系统优化升级依据/AI核心候选估值框架_SOP_v2.6.md`

核心原则：底线用传统现金流，进攻用 AI 期权，但仓位必须由验证事实解锁。Claude 后续做 MSFT / AMZN / NVDA / META / ADBE 时必须使用 v2.6，而不是只用传统 SOP v2.5。

GPT/用户已确认 Claude 对 v2.6 的风险补丁，并正式纳入四项硬约束：

1. `V_option` 必须用概率加权情景法计算，或使用上限约束；不得只写叙事。
2. 正股仓位价格前提：`Watch Position ≤ V_base`，`Starter Core ≤ V_base×0.90`，`Core Build ≤ V_base×0.80`，`High Conviction ≤ V_floor×1.10`。
3. WACC 硬下限：美股大型科技 ≥9.0%，半导体/硬件 ≥9.5%，有地缘风险 ≥10.5%。
4. `V_option` 不能单独解锁高价正股买入。它只能提高观察优先级和长期上行判断；正股买入仍必须满足价格 ≤ `V_base`。若价格高于 `V_base`，最多进入 `Research Only` 或 `Defined-Risk Option Review`。

筛选标准必须高于普通 Radar 候选：

| 标准 | 要求 |
| --- | --- |
| 生意质量 | 极强护城河、网络效应、平台/生态/基础设施属性 |
| AI 受益方式 | 不是纯概念，必须能真实转化为收入、利润、现金流或定价权 |
| 长期 runway | 至少 5-10 年可持续增长空间 |
| 现金流真实性 | 优先 GAAP EBIT / FCFF / owner earnings，不用调整后故事替代真实现金流 |
| 管理层和资本配置 | 能持续投入 AI，同时不牺牲股东回报和纪律 |
| 估值纪律 | 好公司不等于好股票，必须给出 Bear/Base/Bull、击球区和仓位纪律 |
| 系统角色 | 只能进入主仓长期候选池或质量观察池，不直接变成交易指令 |

### 候选分层

第一梯队：最接近“AI时代长期核心复利股”的候选。

| Ticker | 初步定位 | Claude 任务 |
| --- | --- | --- |
| `MSFT` | 企业 AI 平台 + Azure + Office/Copilot + GitHub，最像稳健型 AI 核心 | 做 AI-Core SOP v2.6 完整估值，P0 |
| `GOOGL` | Search/YouTube/Cloud/Gemini/Waymo，高质量但当前估值报告显示偏贵 | 已完成首轮估值；后续只需更新监控和击球区 |
| `AMZN` | AWS + 广告 + 零售/物流网络 + AI 基础设施，复杂但 runway 大 | 做 AI-Core SOP v2.6 完整估值，P0 |
| `NVDA` | AI 直接受益最大龙头，用户已有持仓；但周期性和估值风险更高 | 做 AI-Core SOP v2.6 持仓复核版估值，P0，不默认加仓 |

第二梯队：高质量 AI 受益，但是否能做“唯一长期核心”需要更严格验证。

| Ticker | 初步定位 | Claude 任务 |
| --- | --- | --- |
| `META` | AI 提升广告效率、推荐系统和内容分发；现金流强但广告周期和 CapEx 纪律需跟踪 | 做 AI-Core SOP v2.6 完整估值，P1 |
| `ADBE` | 专业创作软件基础设施，AI 改造受益与被颠覆风险并存 | 做 AI-Core SOP v2.6：AI 颠覆压力测试 + 估值，P1 |
| `AVGO` | AI 网络/定制芯片/基础设施高质量供应商，偏 AI 基建复利 | 初筛 + 估值框架，P1 |
| `TSM` | 全球半导体制造核心瓶颈，AI 基建底层资产，但有地缘风险 | 初筛 + 地缘折扣估值，P1 |

第三梯队：高弹性或瓶颈股，不适合作为“段永平式唯一核心仓”，但可进入 Radar/V6-B。

| Ticker | 定位 |
| --- | --- |
| `ASML` | 半导体设备垄断型资产，周期和地缘需折扣 |
| `AMD` | AI 追赶者，高弹性但竞争和利润率不确定 |
| `MU` | HBM/存储瓶颈，周期性强，不主仓化 |
| `COHR / ALAB / CRDO / AAOI` | AI 互连/光模块/高速连接高弹性，适合 Radar/V6-B，不适合作长期唯一核心 |

### 已有结论

- `GOOGL`：首轮 SOP v2.5 估值已完成。当前约 `$396` 高于 `V_base $235` 约 69%，高于 `Bull Ceiling $320` 约 24%。结论：好公司，贵价，只研究不动作；`$250` 以下重评，`$190-220` 为击球区。
- `ADBE`：算 AI 时代优质候选，但更像“被 AI 改造的既有软件龙头”，不是最确定的 AI 基础设施/平台核心。它值得估值，但买入必须要求更高安全边际，补偿 AI 颠覆风险。
- `NVDA`：用户已有持仓，属于 AI 直接暴露。当前不因 FOMO 追高；需要做持仓复核，判断是否持有、减仓、等待回撤加仓。

### Claude 执行顺序

1. 先做 `MSFT` 完整 AI-Core SOP v2.6 估值。
2. 再做 `AMZN` 完整 AI-Core SOP v2.6 估值。
3. 再做 `NVDA` 持仓复核版估值，重点回答“已有仓位是否继续持有、什么价格可加仓、什么情况降仓”。
4. 然后做 `META`。
5. 最后做 `ADBE` 的 AI 颠覆压力测试和估值。

每份报告必须输出：

- `V_floor / V_base / V_option`。
- Bear / Base / Bull 估值。
- 反向 DCF：当前价格已经 price-in 到哪一年。
- AI 价值创造路径：AI 到底如何转化为收入、利润、现金流或定价权。
- AI CapEx 是维护成本、扩张资产还是投机性投入。
- 验证事实和反证事实。
- 当前价格相对 Base 和 Bull 的溢价/折价。
- 击球区。
- 是否适合作为主仓长期核心。
- 若适合，最大仓位上限。
- 若不适合，原因是估值、商业模式风险、AI 颠覆风险、周期性还是地缘风险。
- 期权表达评估：是否可用 cash-secured put / long-dated call / defined-risk spread / covered call 降成本或定义风险；也可以明确 `NO_OPTION`。
- 与当前已有核心仓位的机会成本比较，尤其是 PDD / 腾讯 / NVDA / 泡泡玛特。

禁止事项：

- 不因 13F 大佬持仓直接买。
- 不因用户喜欢某家公司直接降低安全边际。
- 不把高弹性 Radar 股误升为长期核心仓。
- 不把“AI 受益”当作估值溢价无限合理化。

## A股低频主线确认 Radar 同步：给 Claude 审核代码用

本节是最新增量。用户重新确认：A股 Radar 不能污染主仓哲学、V6节奏和生活节奏。因此本模块已从“短线实验仓”降级为“低频主线确认观察模块”。Claude 的任务是查错、指出工程风险、审查是否符合设计，不是重新定义系统方向。

### 定位

| 分支 | 定位 | 时间尺度 | 资金属性 | 是否替代 V6 |
| --- | --- | --- | --- | --- |
| `US_RADAR` | 美股产业主线、供应链扩散、V6-B universe 输入 | 数周到数月 | 研究/进攻候选 | 否 |
| `A_SHARE_SHORT` | A股资金主线、前置信号、确认信号、次日观察计划 | 1-5 个交易日 | 20日观察期，真实仓位0 | 否 |

A股 Radar 是低频主线确认观察模块，不替代主仓价值投资，不替代 V6，不自动交易。目标是验证能否在不打板、不排板、不盯盘、不早盘抢票的前提下，用工程化流程提前识别待涨板块、龙头/中军/补涨，并通过复盘持续降低滞后性和追高错误。

### 设计目标

1. 前一晚扫描主线，输出下个交易日最值得观察的 1-3 条 A股低频主线。
2. 对个股做龙头 / 中军 / 补涨 / 后排分类，不只给股票列表。
3. 同时保留 `pre_signal_score` 和 `confirm_score`，区分埋伏机会与确认机会。
4. 【动作】必须精细化为 `entry_trigger`、`no_buy_condition`、`position_size_rmb`，不能只写“可买/观察”。
5. 【退出】必须精细化为 `hard_stop`、`time_stop`、`theme_exit`、`take_profit`，不能只写“转弱退出”。
6. 没有计划不做盘中临时交易；没有复盘不形成下一次观察结论。
7. 当前先跑 20 个交易日纯观察，至少 30 个候选样本前不实盘；不扩资金、不自动交易、不主仓化。

### 当前模式和仓位

| 模式 | 含义 | 仓位 |
| --- | --- | --- |
| `AMBUSH` | 前置信号强，但主线尚未完全高潮；当前只记录模拟触发 | `0` |
| `CONFIRM` | 主线已确认；只等分歧回踩、突破回踩或中军确认；当前只记录模拟触发 | `0` |
| `WATCH_CONFIRM` | 主线有强度，但买点/数据/风险不满足交易 | `0` |
| `WATCH_ONLY` | 只记录表现，不交易 | `0` |

### 当前代码位置

核心脚本：

- `/Users/zhangkun/WorkBuddy/程序化/量化程序/a_share_short_radar_plan.py`
- `/Users/zhangkun/WorkBuddy/程序化/量化程序/a_share_short_radar_review.py`
- `/Users/zhangkun/WorkBuddy/程序化/量化程序/a_share_short_radar_evening_guide.py`

数据补给：

- `/Users/zhangkun/WorkBuddy/程序化/量化程序/a_share_tech_screener_v1_local/fetch_a_share_csv_from_futu.py`

本地输出：

- `/Users/zhangkun/WorkBuddy/程序化/量化程序/backtest_results/a_share_short_radar/latest_plan.md`
- `/Users/zhangkun/WorkBuddy/程序化/量化程序/backtest_results/a_share_short_radar/latest_plan.json`
- `/Users/zhangkun/WorkBuddy/程序化/量化程序/backtest_results/a_share_short_radar/latest_candidates.csv`
- `/Users/zhangkun/WorkBuddy/程序化/量化程序/backtest_results/a_share_short_radar/latest_themes.csv`

桌面主入口：

- `/Users/zhangkun/Desktop/AI个人投资公司/A股短线Radar下周一计划_LATEST.md`
- `/Users/zhangkun/Desktop/AI个人投资公司/A股短线Radar候选_LATEST.csv`
- `/Users/zhangkun/Desktop/AI个人投资公司/A股短线Radar主线评分_LATEST.csv`
- `/Users/zhangkun/Desktop/AI个人投资公司/A股短线Radar晚间操作指导_LATEST.html`

支撑文档：

- `/Users/zhangkun/Desktop/AI个人投资公司/系统优化升级依据/A股短线Radar实验仓_SOP_v1.md`
- `/Users/zhangkun/Desktop/AI个人投资公司/系统优化升级依据/A股短线Radar每日执行手册_v1.md`

### 当前运行命令

生成计划：

```bash
python3 a_share_short_radar_plan.py \
  --input-dir a_share_tech_screener_v1_local/outputs/a_share_short_radar_20260518 \
  --next-trade-date 2026-05-18 \
  --asof 2026-05-16 \
  --live-snapshot
```

生成晚间指导：

```bash
python3 a_share_short_radar_evening_guide.py --asof 2026-05-16
```

收盘复盘：

```bash
python3 a_share_short_radar_review.py
```

### 最新计划状态

截至 `2026-05-16` 最新计划：

| 主线 | 分数 | 结论 |
| --- | ---: | --- |
| 人形机器人 | `31/35` | 最强主线，可重点跟踪，但不追连续加速 |
| 半导体设备 | `27/35` | 次强主线，只做低吸或中军 |
| 氟化工 | `14/35` | 只复盘，不交易 |
| AI应用 | `8/35` | 放弃 |

最新候选重点：

| 标的 | 模式 | 当前动作 |
| --- | --- | --- |
| `SH.688017 绿的谐波` | `CONFIRM` | 只观察是否触发分歧回踩或突破回踩，不追高、不实盘 |
| `SZ.002371 北方华创` | `AMBUSH` | 半导体设备中军，只记录模拟埋伏条件 |
| `SH.688697 纽威数控` | `CONFIRM` 但仓位 0 | 仅快照，无完整 K 线，不交易 |
| `SZ.300276 三丰智能` | `CONFIRM` 但仓位 0 | 仅快照，无完整 K 线，不交易 |

补充资金口径：

- 当前 20 个交易日观察期真实仓位必须为 0。
- 如果观察期验证通过，且确认这套机制不需要惊心动魄地盯盘、不污染主系统和生活节奏，可以评估进入 `5万 RMB` 低频试运行。
- 不需要极端降到 1万 RMB；但未通过观察期前，仍不实盘。

### Claude 审核重点

1. `choose_mode` 是否会把 `CONFIRM` 标给数据不足但主题强的票，虽然仓位为 0；这是否会误导用户。
2. `position_size_for` 是否足够严格，是否存在 action 文案变化后误给仓位的风险。
3. `action_plan_for` 对 `WATCH_CONFIRM / WATCH_ONLY` 是否始终保证不交易。
4. `render_markdown` 是否优先展示有仓位动作的候选，而不是被观察票挤掉。
5. `compact_candidate_table` 和晚间邮件是否把 `action_detail / exit_detail` 作为主视图，而不是只展示笼统 action。
6. Futu Level A 快照覆盖价格后，均线/动量仍来自旧 K 线，这个混合口径是否提示充分。
7. 缺 K 线的票是否应该统一强制 `position_size_rmb = 0`，即使主题分和确认分很高。
8. 当前主题种子 `THEME_SEEDS` 仍偏手工，未来需要扩成全市场扫描器，否则仍有滞后性。
9. 复盘脚本是否能按“事前计划”评估，而不是按事后涨跌美化结论。
10. 邮件/桌面输出是否和本地 `backtest_results` 输出保持一致，避免新旧计划混用。
11. 新最高原则是否被代码体现：20个交易日观察期内真实仓位必须为0，不能因为候选触发计划而输出实盘建议。

## 2. 今天已完成的 6 项工作

### 2.1 完善 `radar_order_valuation_seed.csv`

文件位置：

`/Users/zhangkun/Desktop/AI个人投资公司/系统优化升级依据/radar_order_valuation_seed.csv`

当前已覆盖：

`AAOI / CRDO / ALAB / COHR / VECO / IREN / MRVL / NOK / AMD / MU / LITE / ASX / AMKR / WDC / TSLA / ROK / ETN / HON / IR`

用途：

- 给 Radar 候选加入订单、收入、市值、估值场景和估值现实结论。
- 解决“主线强但价格已经透支”的问题。
- 让每日驾驶舱能显示 `valuation_verdict` 和操作建议。

当前结论口径：

| verdict | 含义 |
| --- | --- |
| `UNDERPRICED_WITH_VISIBLE_ORDERS` | 订单/收入支撑明显，价格仍有赔率 |
| `FAIR_BUT_NEEDS_PULLBACK` | 基本合理，但需要等回调或新订单 |
| `PRICED_FOR_BASE_CASE` | 已反映中性预期，不追高 |
| `PRICED_FOR_BULL_CASE` | 已反映乐观预期，禁止直接追高 |
| `TOO_MUCH_NARRATIVE_NOT_ENOUGH_NUMBERS` | 叙事多于数字，只研究不交易 |

### 2.2 精炼 Radar 买点/卖点规则

已修改脚本：

`/Users/zhangkun/WorkBuddy/程序化/量化程序/investment_company_dashboard.py`

每日驾驶舱现在显示 `买点类型`：

| 买点类型 | 动作 |
| --- | --- |
| `NO_CHASE` | 禁止追高，只等回踩、横盘重启或放弃 |
| `PULLBACK_REVIEW` | 趋势强但涨幅偏大，只允许小仓试错 |
| `FORMAL_REVIEW` | 进入正式复核，不等于自动买 |
| `VALUATION_SUPPORTED_REVIEW` | 估值现实支持，可优先复核 |
| `VALUATION_BLOCKED` | 估值不支持，研究不交易 |
| `WATCH_ONLY` | 继续观察 |

买点/卖点已从固定比例升级为参考：

- `MA50`
- `20日低点`
- `63日回撤位置`
- `估值现实`
- `chase_risk`
- `trade_posture`

仍未完成的更高级部分：

- 成交量确认
- 突破/回踩识别
- 财报/订单事件窗口
- 6月1日后 forward return 验证

### 2.3 建立 Radar 人工复盘模板

新增文件：

`/Users/zhangkun/Desktop/AI个人投资公司/系统优化升级依据/Radar_每周人工复盘模板_v1.md`

用途：

- 每周复盘 Radar 是否真正有用。
- 区分独立发现、朋友样本、漏网机会。
- 判断买点是否触发、是否追高错误、估值结论是否有效。
- 6月1日后直接填真实 forward return。

### 2.4 清理主文档层级

新增索引：

`/Users/zhangkun/Desktop/AI个人投资公司/系统优化升级依据/README.md`

当前规则：

- 主目录只保留每日入口、主策略文档、最新报告。
- 方法论、模板、路线图、评估卡全部放入 `系统优化升级依据/`。
- 如果某个文件变成每日必看，才提升到主目录。

用户主要日常查看：

- `/Users/zhangkun/Desktop/AI个人投资公司/AI个人投资公司_每日驾驶舱.html`
- `/Users/zhangkun/Desktop/AI个人投资公司/投资系统全景图_SYSTEM_OVERVIEW.html`
- `/Users/zhangkun/Desktop/AI个人投资公司/26年阶段性组合策略计划.html`
- `/Users/zhangkun/Desktop/AI个人投资公司/中央风控看板_CENTRAL_RISK_BOARD_LATEST.html`

### 2.5 准备 2026-05-26 V6-A balanced cutover SOP

已更新：

`/Users/zhangkun/Desktop/AI个人投资公司/2026-05-26_V6A_balanced_cutover_执行检查卡_v1.md`

补充内容：

- 本地执行脚本文件存在性已预检。
- 明确当天必须确认 OpenD、Futu 登录态、账户快照、managed state、Central Risk Board。
- 2026-05-26 是 `cutover decision day`，不是默认切换日。

当天只能输出三种结论：

| 结论 | 含义 |
| --- | --- |
| `GO_CUTOVER` | 可进入受控切换流程，但真实下单仍需用户再次确认 |
| `HOLD_OLD_BASELINE` | 继续旧 baseline，不切换 |
| `PAUSE_V6` | 发现账户或执行链路风险，暂停升级 |

### 2.6 建立主仓财报更新模板

新增文件：

`/Users/zhangkun/Desktop/AI个人投资公司/系统优化升级依据/主要持仓财报更新模板_v1.md`

用途：

- 腾讯、泡泡玛特、NU 以及未来主仓财报统一复核。
- V6 仓位如果和主仓重叠，也不能忽略主仓 thesis 更新。
- 每次财报结论必须同步到 overview 和 26 年计划。

## 3. Radar 独立发现口径已修正

已修改脚本：

`/Users/zhangkun/WorkBuddy/程序化/量化程序/radar_theme_rotation_scanner.py`

关键变化：

- Radar 默认使用 `independent_discovery` 口径。
- 朋友/外部短线样本默认排除，不进入独立 alpha。
- 朋友样本只进入 `external_sample_review`。

当前样本闭环验证：

| 类型 | 数量 |
| --- | ---: |
| `independent_discovery` | 9 |
| `external_sample_review` | 3 |
| `missing_opportunity_review` | 6 |

AAOI / MRVL / NOK 当前已正确标记为 `external_sample_review`，不是 Radar 独立发现。

## 4. 今天更新过的关键输出

已同步到桌面：

- `/Users/zhangkun/Desktop/AI个人投资公司/AI个人投资公司_每日驾驶舱.html`
- `/Users/zhangkun/Desktop/AI个人投资公司/AI个人投资公司_每日驾驶舱.json`
- `/Users/zhangkun/Desktop/AI个人投资公司/Radar_样本闭环表_LATEST.md`
- `/Users/zhangkun/Desktop/AI个人投资公司/Radar_样本闭环表_LATEST.csv`
- `/Users/zhangkun/Desktop/AI个人投资公司/Radar_样本闭环表_LATEST.json`
- `/Users/zhangkun/Desktop/AI个人投资公司/Radar_主线扩散自动扫描_LATEST.md`
- `/Users/zhangkun/Desktop/AI个人投资公司/Radar_主线扩散自动扫描_LATEST.json`

新增支撑文档：

- `/Users/zhangkun/Desktop/AI个人投资公司/系统优化升级依据/README.md`
- `/Users/zhangkun/Desktop/AI个人投资公司/系统优化升级依据/Radar_每周人工复盘模板_v1.md`
- `/Users/zhangkun/Desktop/AI个人投资公司/系统优化升级依据/主要持仓财报更新模板_v1.md`
- `/Users/zhangkun/Desktop/AI个人投资公司/系统优化升级依据/2026-05-16_系统工作同步_给其他AI冷启动.md`

## 5. 当前代码改动状态

已修改但未提交 GitHub：

- `investment_company_dashboard.py`
- `radar_sample_loop.py`
- `radar_theme_rotation_scanner.py`

验证：

```bash
python3 -m py_compile radar_theme_rotation_scanner.py radar_sample_loop.py investment_company_dashboard.py
```

结果：通过。

注意：

- 今天没有推 GitHub。
- 工作区有大量历史未追踪/未提交文件，不要随便 revert。
- 不要用 `git reset --hard` 或破坏性命令。

## 6. 6月1日前剩余状态

今天这 6 项已经闭环。6月1日前真正还可以做的，主要是轻量维护：

- 如有新朋友样本，加入外部样本复盘，不直接买。
- 如有主仓财报，按财报模板更新 overview 和 26 年计划。
- 如有新的 Radar 高分候选，补 `radar_order_valuation_seed.csv`。
- 继续观察每日驾驶舱，不因 Radar 候选直接交易。

## 6A. 2026-05-16 GOOGL / PDD 最新同步

### GOOGL

- 已纳入系统长期监控和机会成本比较池。
- 当前身份：`强平台现金牛 / AI 再定价观察`。
- 不是立即加仓指令，也不因 V6 或指数成分身份自动升级为主仓。
- 后续若 GOOGL 同时出现在 V6 与主仓讨论中，必须按主仓 thesis 完整跟踪：搜索利润池、YouTube、Cloud、AI capex、监管和资本配置。

### PDD

- 已 review `/Users/zhangkun/Desktop/AI个人投资公司/公司估值/PDD_估值报告_20260515_SOPv2.5版.html`。
- 报告性质：`2026-05-15 财报前特别版`，数据基础为 FY2025，Q1 2026 仍待 `2026-05-19` 验证。
- 新估值锚：`Bear ≈ $79`，`Base ≈ $148`，`Bull ≈ $262`，净现金底约 `$39.8/ADS`。
- 关键变化：旧 `V_base $234` 已过期；因 FY2025 EBIT/OCF 压缩、Temu 监管风险显性化和 WACC 上调，Base 下修到 `$148`。
- 当前动作：`持有底仓，财报前不加仓`。
- 条件动作：若 Q1 营业利润率/现金流验证 Temu 利润压缩逆转，可讨论升至 `13%-15%`；若营业利润率低于 `18%` 且无改善指引，降级到 `5%-7%` 或更低。
- 系统层结论：PDD 仍有赔率，但已不是“深度击球区”；它的核心矛盾从“便宜不便宜”转为“Temu 成本和监管是否会永久压低 owner earnings”。

需要等日期触发的事项：

| 日期 | 事项 |
| --- | --- |
| `2026-05-26` | 执行 V6-A balanced cutover SOP，判断 GO/HOLD/PAUSE |
| `2026-06-01` | 历史 K 线额度刷新后，跑 V6-B / Radar 正式验证 |

## 7. 6月1日后重点

文件：

`/Users/zhangkun/Desktop/AI个人投资公司/6月1日_V6B_执行卡.md`

要补齐：

- `fwd_5d / fwd_10d / fwd_20d / fwd_60d`
- `max_drawdown_after_signal`
- `trade_posture` 分组表现
- `valuation_verdict` 分组表现
- `buy_zone` 触发后表现
- `chase_error_count`
- `overpriced_avoidance_count`
- `valuation_filter_hit_rate`

目的：

- 验证 Radar 是否真的有独立 alpha。
- 验证 `禁止追高 / 等回调 / 可复核` 是否有效。
- 验证估值现实检查是否能减少追高错误。
- 决定 Radar 是否能从研究辅助升级为 V6-B / Overlay 的半自动输入。

## 8. 给接手 AI 的工作规则

如果接手这个系统，请遵守：

- 不要把朋友样本当作 Radar 独立发现。
- 不要因为主线强就默认可以买。
- 每个标的必须经过：主线、动能、买点、估值现实、Central Risk Board。
- 支撑文档放 `系统优化升级依据/`，不要继续污染主目录。
- 所有文档中文表述。
- 涉及主仓财报必须同步 overview 和 26 年计划。
- 涉及真实交易必须经过用户明确确认，不能自动下单。
- 当前系统目标是稳健提高长期收益，不是复制短线团队的极端收益。

---

## 当前 Handoff 快照

# AI Handoff Current Snapshot

- Last updated: 2026-05-14
- Purpose: 给新接入的 AI 快速继承当前工作，避免重新翻完整聊天记录。

## 先说结论

聊天平台里的完整对话不应被当作长期记忆源。长期可继承的上下文应该沉淀在本地文件和 GitHub 中。

新 AI 接入时，优先读取唯一同步文件：

1. `/Users/zhangkun/WorkBuddy/程序化/量化程序/AI_WORK_SYNC_CURRENT.md`

其他文件只作为证据层或深挖时使用：

2. `/Users/zhangkun/WorkBuddy/程序化/量化程序/AI_HANDOFF_CURRENT.md`（本文件，保留历史 handoff）
3. `/Users/zhangkun/WorkBuddy/程序化/量化程序/AI_COLLAB_LOG.md`（双向协作底层流水账）
4. `/Users/zhangkun/WorkBuddy/程序化/量化程序/V6_STRATEGY_LAB.md`
5. `/Users/zhangkun/WorkBuddy/程序化/量化程序/V6_PRODUCTIONIZATION_SOP.md`
6. `/Users/zhangkun/Desktop/AI个人投资公司/投资系统全景图_SYSTEM_OVERVIEW.html`
7. `/Users/zhangkun/Desktop/AI个人投资公司/AI个人投资公司_每日驾驶舱.html`

## AI 协作同步机制

Claude 和 GPT 通过 `AI_COLLAB_LOG.md` 共享协作状态，避免知识分叉。

同步规则：
- Claude / GPT：每次会话结束前将关键产出写入 `AI_COLLAB_LOG.md`
- 统一对外同步：运行 `python3 collab_sync.py export-current`，刷新 `AI_WORK_SYNC_CURRENT.md`
- 以后给任何新 AI 都优先上传 `AI_WORK_SYNC_CURRENT.md`
- `AI_COLLAB_EXPORT_FOR_GPT.md` 仅保留旧兼容用途，不再作为主要入口

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

## A股 Radar 当前执行口径（2026-05-18 更新）

A股 Radar 当前不是自动交易系统，正式阶段为：

```text
Phase 1A = FutuAPI 拉行情/生成信号/复盘 + 长江证券手动下单
```

当前用户计划用约 5 万 RMB 训练 A股 Radar。目标是打磨主线识别、龙头/中军/补涨判断、买点过滤和退潮信号，不是打板、排板或高频交易。

关键规则：
- 当前不接长江证券 PTrade / QMT / miniQMT 委托接口。
- FutuAPI 可用于行情、K线、成交额、MA5/MA10、执行卡生成。
- 真实交易若发生，用户在长江证券客户端手动下单。
- PTrade 极速版客户经理反馈门槛约为 100 万信用账户净资产；它是未来规模化工具，不是当前验证期前置条件。
- 资金接近 50 万时再评估是否接长江行情/持仓；100 万以上才考虑申请 PTrade，且先只接行情/持仓。
- 只有 50 笔以上实盘样本证明正期望后，才允许讨论小额半自动/自动委托。

相关文件：
```text
investment_screener/radar_astock.json
investment_screener/A_SHARE_RADAR_REVIEW_SOP.md
investment_screener/A_SHARE_RADAR_AUTOMATION_ROADMAP.md
REVIEW_CADENCE_POLICY.md
events_calendar.json
```

Claude 执行 A股 Radar 任务时，应默认只做复盘、信号、执行卡和事件提醒，不写自动下单代码，不触碰券商委托接口。

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

---

## 最近协作日志

## 2026-05-17

### GPT

- [00:29] [决策] A股Radar定位正式从短线实验仓降级为A股低频主线确认观察模块：20个交易日纯观察期，真实仓位0，不打板、不排板、不盯盘、不早盘抢票；目标是训练主线识别/买点过滤/退潮信号并反哺美股Radar/V6-B，不作为当前赚钱系统。代码已将OBSERVATION_ONLY=True，所有候选position_size_rmb强制为0，计划和邮件均改为观察/模拟触发口径。
- [12:07] [决策] A股低频主线确认Radar资金口径微调：当前20个交易日观察期仍真实仓位0；若观察期验证通过，且确认不需要惊心动魄盯盘、不污染主系统和生活节奏，可以评估进入5万RMB低频试运行，不需要极端降到1万。
- [12:48] [决策] 新增AI核心长期复利候选池：目标是寻找AI时代可长期持有、类似当年AAPL之于段永平的核心复利标的。第一梯队MSFT/GOOGL/AMZN/NVDA；第二梯队META/ADBE/AVGO/TSM；第三梯队ASML/AMD/MU/COHR/ALAB/CRDO/AAOI等只做Radar/V6-B或高弹性候选。Claude执行顺序：MSFT完整SOP估值 -> AMZN完整SOP估值 -> NVDA持仓复核估值 -> META -> ADBE AI颠覆压力测试。禁止因13F或喜欢公司直接买，必须给Bear/Base/Bull、击球区、主仓适配性、仓位上限和机会成本比较。
- [12:54] [决策] AI核心候选估值框架升级为SOP v2.6：专用于MSFT/GOOGL/AMZN/NVDA/META/ADBE/AVGO/TSM等AI时代长期核心候选。核心原则为‘底线用传统现金流，进攻用AI期权，但仓位必须由验证事实解锁’。每份报告必须输出V_floor/V_base/V_option、Bear/Base/Bull、反向DCF、AI价值创造路径、AI CapEx ROI、验证/反证事实、仓位解锁、期权表达评估和机会成本比较。已写入系统优化升级依据/AI核心候选估值框架_SOP_v2.6.md，并更新同步文档给Claude执行。
- [13:09] [决策] GPT/用户确认Claude对AI-Core SOP v2.6的资本风险补丁，并正式纳入四项硬约束：(1)V_option必须用概率加权情景法或上限约束计算，不能只写叙事；公式修正为V_AI_probability_weighted=Σ(情景企业价值×概率)，V_option=max(0,V_AI_probability_weighted-V_base)，避免重复计算Base；(2)正股仓位价格前提：Watch≤V_base、Starter≤V_base×0.90、Core≤V_base×0.80、HighConviction≤V_floor×1.10；(3)WACC硬下限：大型科技≥9%、半导体/硬件≥9.5%、地缘风险≥10.5%；(4)V_option不能单独解锁高价正股买入，只能提高观察优先级和长期上行判断，价格>V_base时最多Research Only或Defined-Risk Option Review。
- [13:11] [决策] AI-Core SOP v2.6 已补充 GPT 执行审查层：新增 V_option 三情景概率加权建模模板、AI贡献可追踪指标、价格与仓位强制判定顺序、与 PDD/腾讯/NVDA/泡泡玛特/现金的机会成本硬比较，以及 Claude 复审问题清单。核心口径不变：V_option 只能让我们更认真地等，不能让我们更贵地买。
- [13:18] [决策] 估值 SOP v2.5 已完成 GPT 风险补丁：保留其作为主仓价值投资现金流纪律底座，同时修复六项执行风险：Floor 统一为 min(资产/现金流压力底, DCF_Bear)；击球区不自动买入；Kelly 仅做 sanity check；Price<=Floor 改为 THESIS_REUNDERWRITE_REQUIRED 而非自动止损；EV/FCF 极端折价必须先解释折价来源；新增 WACC 硬下限。已同步核心 SOP、Claude /估值 命令入口和知识库卡片。
- [13:38] [决策] 根据 Claude review 继续修正估值 SOP v2.5 补丁：统一 Section 3.1 中清算价值旧词为资产/现金流压力底；逻辑B改为 Floor=min(TBV×0.7, DCF_Bear)；Step 3.2 Price<=Floor 熔断改为 Downside=Price×20% 仅用于赔率/Kelly 防除零，同时触发 THESIS_REUNDERWRITE_REQUIRED，不默认欺诈、不自动卖出；补充 v2.5/v2.6 WACC 优先级，AI-Core 取 v2.6 或更高下限；明确击球区动作五条件必须全部满足并逐条输出；区分悲观FCFF与独立DCF_Bear。
- [14:10] [决策] 2026-05-17 GPT 已生成主仓估值更新：PDD/腾讯/泡泡玛特/NU/招商银行按新版 SOP v2.5 补丁重新评估。输出文件：/Users/zhangkun/Desktop/AI个人投资公司/系统优化升级依据/2026-05-17_主要持仓估值更新_SOPv2.5补丁版.md。核心结论：PDD 等 5/19 Q1 不加仓；腾讯核心持有但旧 Kelly/Wheel 降级；泡泡玛特 HK50 附近持有不追；NU 小仓/观察不主动加；招行 RMB 停泊仓不升战略核心。
- [14:11] [决策] 更正上一条同步：泡泡玛特结论应为 HK$150 附近持有不追；不是 HK50。
- [14:18] [决策] 已同步更新 /Users/zhangkun/Desktop/AI个人投资公司/26年阶段性组合策略计划.html：策略大方向不变，只把 2026-05-17 SOP v2.5 补丁后的主仓估值与动作纪律写入主指导文件。更新点：PDD 等 5/19 Q1 不加仓；腾讯核心持有但 Kelly/Wheel 降级；泡泡玛特 HK50 附近持有不追；NU 小仓/观察；招行 RMB 停泊仓。
- [14:18] [决策] 更正上一条同步：泡泡玛特结论是 HK$150 附近持有不追，不是 HK50。
- [15:49] [决策] 2026-05-17 AI右尾期权袖珍仓前置工作完成：新增 /Users/zhangkun/Desktop/AI个人投资公司/系统优化升级依据/AI右尾期权袖珍仓执行卡_v1.md，并同步进 26年阶段性组合策略计划.html。定位：US Radar/V6-B 的定义风险右尾表达，不是主仓替代或暴富模块；初期总预算 1% 内，验证后上限 1%-3%，单笔 00-,500，默认可归零；5-26 pilot 总结和 6-01 K线额度刷新前只读准备、不实盘。radar_right_tail_option_screener.py 默认候选池已扩到 CRDO/ALAB/COHR/LITE/IREN/CORZ/APLD/BE/CIFR/AAOI/MU/WDC/TSM/AVGO/AMD/ANET/AMKR。
- [15:49] [决策] 更正上一条同步：AI右尾期权袖珍仓单笔预算应为 $300-$1,500；不是 00-,500。
- [16:02] [决策] 2026-05-17 GPT 已 review Claude 生成的 MSFT/NVDA/ADBE SOP v2.6 估值报告，输出到 /Users/zhangkun/Desktop/AI个人投资公司/公司估值/AI核心三标的_估值报告_GPT_review_20260517.md。结论：MSFT 质量最高但当前 Research Only，$366 以下重新开门；NVDA 已有 AI 核心暴露，持有不加仓，等 2026-05-20 财报，$260/$280 是估值减仓触发但反证事实可提前触发；ADBE 三者里最便宜但 CEO 继任阻断加仓，正式口径修正为 SOP Floor $189、DCF Bear $260、V_base $430、V_bull $615。
- [17:14] [决策] 2026-05-17 GPT 已结合第一上海 AAOI PPT 与 Claude AAOI SOP v2.6 报告完成 review，输出到 /Users/zhangkun/Desktop/AI个人投资公司/公司估值/AAOI_初筛估值报告_GPT_review_20260517.md。结论：AAOI 产业逻辑真实，进入 US Radar/V6-B/AI右尾观察池，但当前不是 AI-Core、不是主仓、不是当前价格下 20X 候选；正股 NO_POSITION，期权 NO_OPTION。重要修正：Claude 顶部概率加权价值 $185 与正文表格不一致，正式口径应采用正文 $82；当前 $223 对 $82 溢价约 172%，即使 Bull Case $169 也低于当前价。回调 $140-$170 也必须叠加 Q2 GAAP 转正、Q3 800G 路径≥20万只、ATM 放缓，才考虑 0.5%-1% 观察仓。
- [17:45] [决策] 完成AAPL SOP v2.5更新估值：按规范化FCFF和新版WACC/Floor纪律，AAPL质量仍高但当前约300美元明显高于V_base约149美元和V_bull约216美元；决策为WATCH_ONLY/NO_NEW_BUY/HOLD_IF_OWNED，低于180美元重新研究，130-150美元才接近Starter区。报告路径：/Users/zhangkun/Desktop/AI个人投资公司/公司估值/AAPL_估值报告_GPT_SOPv2.5更新_20260517.md
- [22:08] [决策] 完成交易决策日志系统设计v1：目标是把每次主仓/V6/Radar/A股Radar/AI右尾/期权动作变成可复盘、可统计、可纠错样本；字段分为动作前与动作后，动作前不可事后修改；20笔做初评，50笔做扩容判断；Claude落地路径为创建交易决策日志目录、decision_log.csv、模板和PDD财报前第一条样例。设计文档：/Users/zhangkun/Desktop/AI个人投资公司/系统优化升级依据/交易决策日志系统设计_v1.md
- [22:09] [决策] 补充X信息源自动扫描机制到交易决策日志系统设计v1：定位为信息输入层，不允许单独触发交易；覆盖宏观/利率、波动率/期权、AI Infra/半导体、期权流向弱信号账号；输出raw/daily/weekly结构，字段包含summary_cn、mentioned_symbols、theme_tags、signal_type、importance、action_required、linked_system；建议第一版先半自动复制高价值链接，两周验证后再接X API/RSSHub/Nitter等自动抓取。
- [22:21] [决策] 完成朋友交易团队信息源接入Radar设计v1：将朋友PDF视为其长期短线edge的信息输入层，允许接入Radar-US/V6-B/A股Radar/AI右尾/期权表达时机，禁止影响主仓估值纪律和大仓位动作；建立Friend Alpha Shadow Track记录朋友观点、理由、我们的Radar是否捕捉、1/5/20日结果、是否有可迁移规则；20样本初评、50样本才制度化。文档：/Users/zhangkun/Desktop/AI个人投资公司/系统优化升级依据/朋友交易团队信息源接入Radar设计_v1.md
- [22:38] [代码] 升级morning_brief为投资系统任务中枢：新增今日动作清单/工作流入口，自动从events_calendar和交易决策日志识别临近事项并提示用户该说的关键词；例如PDD财报前显示‘复盘 PDD’，主仓走财报重估/Thesis Re-underwrite/SOP估值更新，Radar/V6/Friend Alpha走样本复盘。已补events_calendar：2026-05-19 PDD财报后重估、2026-05-28 NVDA财报后AI核心复核。
- [22:51] [代码] Daily工作流提醒节奏已固化：A股Radar在交易日提示‘复盘 A股Radar’（仅有候选/交易时执行）；美股Radar/V6-B在周五提示周度样本复盘或由事件触发；V6-A不做每日人工复盘，只在Pilot/节点事件提示；Friend Alpha仅在20/50样本门槛提示复盘。修正review_engine路由：新增V6-A执行质量/Pilot节点复盘，避免误路由到A股Radar。Friend Alpha已初始纳入10个观察样本：AAOI/COHR/LITE/MU/CRDO/ALAB/IREN/CORZ/APLD/BE，均标记为非交易指令。

---

## 2026-05-18

### GPT

- [10:19] [代码] 修复Weekly Formal Board缺少今日待办：central_risk_board.py已接入morning_brief.collect_workflow_actions，并在Markdown/HTML新增Today's Workflow Actions区块；events_calendar新增2026-05-18 A股Radar收盘轻量复盘：三丰智能、纽威数控、绿的谐波，触发词‘复盘 A股Radar’。验证生成central_risk_board_weekly_workflow_actions_preview，已确认包含A股Radar和PDD两条动作。
- [10:22] [代码] 确认每日早间邮件不论交易日都显示今日待办：morning_brief非交易日会给出‘非交易日系统维护/研究日/无需操作’低优先级提示；central_risk_board Daily/Weekly Board已接入同一workflow actions。今日2026-05-18已验证Daily和Board均显示：HIGH 复盘A股Radar（三丰智能/纽威数控/绿的谐波）、MED 复盘PDD、LOW X Radar扫描。今晚照常按‘复盘 A股Radar’做轻量复盘。


### Claude

- [17:17] [发现] ISRG 全量 SOP v2.5 估值已完成：HTML 报告存入 /Users/zhangkun/Desktop/AI个人投资公司/公司估值/ISRG_估值报告_20260518_SOPv2.5版.html；watchlist.json 已更新。当前正式口径：Core Quality，V_base 约 $305，WACC 9.0%，FDA Class I 召回进行中，当前 $421 不建仓，观察仓触发区 <$380 / $360-380。GPT review 后要求修正 FDA Class I 日期和部分估值口径一致性。
- [17:18] [代码] A股Radar 全量收盘复盘已完成：investment_screener/radar_astock.json 更新三只样本，绿的谐波维持龙头、三丰智能维持中军、纽威数控进入 DIVERGE_WARNING 且 review_required=True、max_position_pct=0；events_calendar.json 写入 2026-05-19 Radar 跟踪事件。GPT review 后修复 morning_brief 路由，确保该事件触发词为“复盘 A股Radar”而不是“X Radar 扫描”。
