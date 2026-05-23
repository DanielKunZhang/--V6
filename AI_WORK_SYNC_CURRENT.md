# AI 工作同步 CURRENT

- Last updated: `2026-05-23 16:16:48`
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

### 统一目标与系统协同原则

# AI个人投资公司：统一目标与系统协同原则

日期：2026-05-20  
状态：active / system-level principle  

## 一句话原则

AI个人投资公司的所有工作，最终都必须服务于一个目标：

**在不牺牲长期安全性、不扩大毁灭性回撤风险的前提下，相对安全地快速增长资本。**

任何研究、估值、Radar、13F 学习、V6、仓位调整、价格带更新、daily 邮件和新功能开发，都不能各自独立存在。它们必须互相辅助，统一优化组合的收益质量和风险控制。

## 强制评估问题

后续任何工作完成前，都必须至少回答以下问题：

1. **是否提高组合预期收益？**
   - 是发现更好的候选，还是提高已有高 alpha 机会的识别能力？
   - 是否能让资本从低效率仓位流向更高质量机会？

2. **是否降低重大回撤或错误加仓风险？**
   - 是否识别拥挤交易、估值透支、宏观 regime 不匹配、财报反证或仓位集中风险？
   - 是否改善现金、等待资金、对冲、止损或降级纪律？

3. **是否改善标的选择或仓位结构？**
   - 是否帮助区分底仓、进攻仓、V6、Radar训练仓、现金/等待资金？
   - 是否改变某个标的的角色、目标仓位、击球区或退出规则？

4. **是否符合投资哲学，而不是增加无效复杂度？**
   - 是否仍服从长期复利、风险优先、少数高质量决策、默认不动、可关闭可复盘？
   - 如果只是“看起来更专业”，但不提升决策质量，应降级或放弃。

5. **是否形成实际动作或明确归档？**
   - 动作可以是：升级候选、降级候选、等待回调、保持现金、更新价格带、触发复盘、接入 Radar/V6-B。
   - 如果没有动作，也必须明确写：只归档，不进入 Radar，不影响仓位。

## 对 13F 学习的特别约束

13F 学习不是为了学而学。每次 `更新13F学习` 必须新增一节：

## 对组合收益/安全性的实际贡献

并回答：

1. 有没有提高预期收益？
2. 有没有降低风险？
3. 有没有改变动作？
4. 有没有反哺系统？

如果四个问题都答不出来，结论必须写：

`本次 13F 学习不产生系统增益，只归档，不进入 Radar。`

## 对 Radar / V6 / 估值 / 组合调整的统一要求

| 工作类型 | 必须回答 |
|---|---|
| Radar 新字段 / 新候选 | 是否提高候选池质量、买点纪律、拥挤度识别或反证能力 |
| 13F 学习 | 是否提炼出可执行 alpha skill，是否反哺候选池或风险识别 |
| 主仓估值 | 是否改变 thesis、价值锚、击球区、仓位目标或机会成本排序 |
| 仓位类型调整 | 是否让底仓、进攻仓、V6、Radar、现金职责更清楚 |
| V6 / V6-B | 是否提高组合收益/回撤/相关性结构，而不是追逐漂亮回测 |
| 新功能开发 | 是否减少错误、提高执行纪律、提高信息效率，或降低系统维护成本 |
| daily 邮件 | 是否帮助今天做对的事，减少遗漏和错误动作 |

## 默认处理规则

- 如果能提高收益或安全性：进入系统，并记录反哺路径。
- 如果只提供线索：进入研究池，不影响仓位。
- 如果无法说明增益：只归档。
- 如果增加复杂度但没有明显收益/风险改进：不做。
- 如果与投资哲学冲突：即使短期可能赚钱，也不升级为系统规则。

## 固定系统链路

后续所有工作都要落到这条链路里：

`投资哲学 → 组合目标 → 仓位结构 → 标的选择 → Radar输入 → 估值验证 → 执行纪律 → 复盘反馈`

任何模块不能脱离这条链路单独扩张。

### 冷启动系统同步

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

- Last updated: 2026-05-20
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

2026-05-20 起，所有模块统一服从一个目标：

```text
在不牺牲长期安全性、不扩大毁灭性回撤风险的前提下，相对安全地快速增长资本。
```

任何研究、估值、Radar、13F 学习、V6、仓位调整、价格带更新、daily 邮件和新功能开发都必须回答：是否提高组合预期收益、是否降低重大回撤或错误加仓风险、是否改善标的选择或仓位结构、是否符合投资哲学、是否形成实际动作或明确归档。固定链路为：

```text
投资哲学 → 组合目标 → 仓位结构 → 标的选择 → Radar输入 → 估值验证 → 执行纪律 → 复盘反馈
```

正式文件：`/Users/zhangkun/Desktop/AI个人投资公司/系统优化升级依据/AI个人投资公司_统一目标与系统协同原则_20260520.md`

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

2026-05-19 更新：A股 Radar 正式定位为训练仓，不是大资金进攻仓。正式文件：`/Users/zhangkun/Desktop/AI个人投资公司/系统优化升级依据/26年A股Radar定位_20260519.md`。

- 当前资金：5 万 RMB。
- 50 笔真实样本前不扩到 10 万。
- 100 笔真实样本且经历退潮期仍能控制回撤后，才讨论 20 万。
- 不考虑自动交易；真实交易仍由用户在长江证券手动下单。
- A股 Radar 与 V6-B / 美股 Radar 分开记账、分开样本、分开评估。

## Seeking Alpha 输入源试验（2026-05-19 新增）

`Seeking Alpha` 当前处于外部输入源试验，不是交易信号，不自动化爬取，不绕 paywall；只用于美股 Radar / V6-B / 主仓反证的样本记录。

- 阶段：Phase 1 免费版观察期（2周）
- 记录文件：`backtest_results/external_signal_trials/seeking_alpha_trial.csv`
- 设计文件：`SEEKING_ALPHA_INPUT_TRIAL.md`
- 付费判断：满足 7 中任意两条才考虑 Premium，当前不订阅

样本边界：`seeking_alpha_trial.csv` 只记录真正来自 Seeking Alpha 的文章/评级/摘要信号。X / unusual_whales / CheddarFlow / OptionsHawk / MenthorQ 等外部社媒信号必须写入 `backtest_results/external_signal_trials/x_radar_signal_trial.csv`，不能混入 SA 试验样本。

## 数据源成本纪律（2026-05-18 更新）

当前全资产规模约 300 万 RMB，系统阶段仍以打磨流程、风控和复盘为主，不增加不必要固定成本。

正式口径：
- 1000 万 RMB 总资产之前，不新增 EODHD / Tiingo / Polygon / Nasdaq Data Link 等付费数据源订阅。
- 当前数据源优先级仍为 Futu OpenD / FutuAPI。
- Futu 历史 K 线额度不足时，不用付费源绕过进攻信号 gate；进入 stale data / degraded mode。
- 外部付费数据源只作为未来 1000 万 RMB 以上资产规模后的升级项，用于稳定历史日 K / 周 K / 跨市场数据冗余。
- TradingView 不作为程序化主数据源。

相关设计：`v6_strategy_lab/reports/2026-05-18_v6_stale_data_risk_exit_policy_v1.md`

## 2026 组合策略动态占比新口径（2026-05-19 更新）

正式主指导文件：`/Users/zhangkun/Desktop/AI个人投资公司/26年阶段性组合策略计划.html`

核心变化：不改变价值投资底层哲学，但主仓内部从“低反馈稳定资产过重”调整为“底仓 + 进攻仓 + V6-A + 现金 / 等待资金”。当前约 300 万 RMB 本金阶段允许比 3000 万以后更主动地动态调整占比；所有系统、评估和复盘都要服务于提高资本配置效率，同时不破坏长期安全边界。

当前目标口径：
- 底仓：约 35%-50%，负责长期生存、心理稳定和净值底座。
- 进攻仓：正常 20%-25%，强机会 25%-30%，上限 30%；候选包括 NVDA 进攻部分 / ADBE / 泡泡玛特 / NU / PDD 财报后机会，但必须通过财报、估值、主题强度和拥挤度复核。
- V6-A：当前 5k pilot；通过后先到总资产 5%-8%，至少 3 个月真实稳定后才讨论 10%-12%。V6-B / 美股 Radar 暂不占正式预算。
- A股 Radar：当前 5 万 RMB 训练仓，50 笔真实样本前不扩到 10 万，100 笔且经历退潮期后才讨论 20 万。
- 现金 / 等待资金：总资产最低 5%，正常 8%-12%，回撤期有明确机会可降到 3%-5%；富途现金最低 10%，正常 15%-25%，回撤期有明确机会可降到 8%-12%。
- 腾讯总暴露：2026-05-19 HQ Compounder 重估后，从约 31.8% 降向 12%-15%，阶段上限 18%-20%。
- PDD 正股：从约 20.3% 降向 8%-10%，阶段上限 12%；LEAP 只作为未来减正股后的替代弹性。
- 富途回流资金：优先补进攻仓 / V6-A / 现金，不再继续堆低反馈资产。

动态调整原则：300 万-1000 万阶段允许更高反馈、更高频占比调整；1000 万-3000 万阶段逐步降低换手；3000 万以上明显转向慢调整、低换手和更低永久损失风险。任何加仓不得由短期焦虑或身边人收益刺激触发。

2026-05-19 后续升级：稳定底盘的正式表达应进一步替换为“高质量错杀复利仓”，不是养老型低波资产池。正式框架见 `HQ_COMPOUNDER_REUNDERWRITE_20260519.md`。

高质量错杀复利仓定义：高质量长期复利资产 + Good People + Reasonable Growth + 有吸引力/被错杀价格 + 可承受波动 + thesis 破坏时坚决换。

所有底仓标的必须过两道关口：初筛关（Good Business / Good People / Reasonable Growth / 低永久损失风险）和估值关（Bear/Base/Bull、买入区、持有区、减仓区、目标仓位、thesis 破坏条件）。底仓不应过度分散，目标集中在 3-5 只最好的重拳机会；15%+ 单只仓位仅允许极少数特别机会，并必须通过初筛、估值、反证、组合、心理和退出规则六项审核。

腾讯 2026-05-19 已完成首个 HQ Compounder 重估，文件：`HQ_COMPOUNDER_TENCENT_20260519.md`。结论：`Core HQ Compounder / Hold But Deweight`；保留核心资格，但当前约 31.8% 总暴露过高，目标降至 12%-15%，阶段上限 18%-20%；当前 HK$460 不新增，HK$430-440 以下才重新复核，HK$380-400 以下且 thesis 未破才进入错杀增配区。

美的 2026-05-19 已完成 HQ Compounder 重估，正式文件优先存放在 `/Users/zhangkun/Desktop/AI个人投资公司/HQ_COMPOUNDER_MIDEA_20260519.md`，git 备份副本在仓库根目录。结论：`Core HQ Compounder / Position Capped`；保留核心资格，但目标仓位下调到 8%-10%，阶段上限 12%；当前约 14.4% 已高于新上限，持有但不新增；RMB 78 以下只小额复核，75-76 进入舒服补仓区，72 以下且 thesis 未破才做较大补仓复核。

ADBE 2026-05-19 已完成 HQ Compounder 重估，正式文件优先存放在 `/Users/zhangkun/Desktop/AI个人投资公司/HQ_COMPOUNDER_ADBE_20260519.md`，git 备份副本在仓库根目录。结论：`Candidate HQ Compounder / Upgrade After Gates`；当前允许 3%-5%，只有 Q2 FY2026 与 CEO 继任 gate 通过后才升级到 5%-8%，阶段上限 8%；AI 焦虑构成潜在错杀，但必须确认 AI-native 工具没有侵蚀 Creative / Document workflow、净新增 ARR 和定价权。

NVDA 2026-05-19 已完成 HQ Compounder 重估，正式文件优先存放在 `/Users/zhangkun/Desktop/AI个人投资公司/HQ_COMPOUNDER_NVDA_20260519.md`，git 备份副本在仓库根目录。结论：`Core HQ Compounder / Trend Overlay`；8%-10% 是长期核心复利仓，10%-15% 是趋势增强仓，阶段上限 15%；当前约 12.8% 可以持有但 FY2027 Q1 财报前不新增。财报强通过可维持 12%-15%，中性通过回到 10%-12%，未通过先降趋势增强部分到 8%-10%。

每完成一个 HQ Compounder 策略制定或重估，都必须同步进 26 年组合策略计划 HTML。若 `/Users/zhangkun/Desktop/AI个人投资公司/26年阶段性组合策略计划.html` 因 macOS 权限暂时不可写，先写入 `STRATEGY_26_PENDING_HTML_UPDATES.md`，待权限恢复后合并。当前腾讯、美的、ADBE、NVDA 重估结论均已合并进正式 HTML，并已在 git 仓库保存 HTML 快照。

2026-05-19 已新增现金 / 等待资金规则，正式文件：`/Users/zhangkun/Desktop/AI个人投资公司/系统优化升级依据/26年现金等待资金规则_20260519.md`。现金不是保守摆设，而是等待更好机会的弹药；不为了满仓买低优先级资产，不在 V6-A pilot、ADBE gate、NVDA 财报或 PDD Q1 未验证前提前释放大额现金。

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
backtest_results/v6a_state/v6a_managed_positions_real_<FUTU_ACCOUNT_ID>.json
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

## V6 2026 策略仓配置（2026-05-19 更新）

正式配置文件：`/Users/zhangkun/Desktop/AI个人投资公司/系统优化升级依据/26年V6策略仓配置_20260519.md`

V6 是独立策略仓，不和主观进攻仓混在一起。当前不允许因为回测或短期信号直接给大仓位，只按三段扩容：

- 当前：`5k pilot`，约总资产 1%-2%，富途内约 2%-3%；目标是验证真实执行、滑点、managed state、reconciliation、日报和 kill switch，不追求短期收益。
- 第一档：通过 2 周真实 pilot 后，先到总资产 5%，再看是否到 8%；资金只来自富途现金或腾讯/PDD/IT 回流。
- 第二档：至少 3 个月真实运行稳定后，才讨论 10%-12%。
- 当前不讨论 15%+；V6-B 未完成 standalone、V6-A 对比、组合测试和 live-forward 前，不占正式扩容预算。

V6 扩容不得动腾讯 RSU、国内 A 股账户或港股通底仓。

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

## 2026-05-22

### GPT

- [工作] V6AB 吸收 AAOI/短线报告中可迁移的“事实精度、入场质量、拥挤/赔率风险”思路，但严格保持研究层：已提交 `b7aec3e feat: attribute V6AB boost risk skill`，将 risk skill 指标接入 BOOST failure review、risk skill gate experiment 和 daily report。完整 daily 通过。结论：硬门槛不晋级，最佳 `top3_quality_limit_entry50_fact20` 仅比 guarded 多约 +0.04% 年化，只能 WATCH/诊断，不改变模拟盘。
- [工作] 新增 `v6ab_signal_sizing_experiment.py` 并接入 daily report，已提交 `00c4f5b feat: test V6AB signal quality sizing`。该实验只测试“低 fact precision / 低 entry quality 时降低 PIT B sleeve 表达强度”，不改 classifier、不改 allowlist、不动模拟盘。结果：`cap_low_fact_or_entry_half` 年化 +31.30%，较 guarded -0.64pp；`cap_quality_risk_ladder` +30.65%，较 guarded -1.29pp；`cap_no_entry_edge_to_low` +30.61%，较 guarded -1.33pp。结论：当前瓶颈不是简单降仓/风控能解决，而是 historical evidence、fact precision 和主题映射质量仍需提升。
- [决策] V6AB 模拟盘继续保持 `V6AB_SIM_CANDIDATE_V2_DYNAMIC_B_SIZING`。当前最强研究候选仍是 `pit_tier_turnover_guarded_v6ab_dynamic_b`：年化约 +31.93%、maxDD -15.68%、Sharpe 1.24、2020 +30.51%、2024-2026 +60.09%，但 active rebalances=29<30 且 OVERRIDE=0，不能晋级。下一步优先做 fact precision / historical mainline mapping，而不是继续叠加低收益风控规则。
- [代码] Daily email 降噪已完成并提交 `4a868be fix: reduce daily workflow email noise`：13F 系统输入默认只显示 3 天内到期项且固定为 MED，估值路由只跟随 3 天内事件，不再因为远期横向比较/近期研究文件把 CEG/DUK/ETN/GEV/SO/VST/XEL 等推到 Today's HIGH；早间简报 HTML/文本只把 HIGH 放在“必须处理”，MED/LOW 放入“建议准备/研究队列”；Central Risk Board 的 Today's Workflow Actions 也只展示 HIGH。验证今天从 24 条噪音任务收敛为 2 条必须处理：PDD 日志遗留、GOOGL AI Search thesis watch。
- [代码] V6AB Historical Mainline Gap Review 已实现并接入 daily evolution，提交 `b4ad272 feat: add V6AB historical mainline gap review`。新增 `v6ab_historical_mainline_gap_review.py`，只做诊断，不改交易规则：从 PIT guarded vs V2 月度 attribution 中定位负贡献月份里 V2 被挤掉的主题和 PIT 替换进去的主题。最新结果：guarded active months 28，negative 15，negative sum -40.08%；负贡献最集中在 missed V2 themes：`technology` 7次 / -23.98%，`precious_metals` 4次 / -17.87%；added guarded 负贡献集中在 `ai_platform` -21.99%、`ai_memory` -11.50%、`ai_optical` -9.09%。结论：下一步应优先补 2020/2023/2024/2026 相关的 technology / precious_metals / defensive-or-commodity 历史主线证据和映射，而不是继续简单给 AI BOOST 加风控。
- [代码] V6AB Theme Mapping Experiment 已实现并接入 daily evolution，提交 `7f1f325 feat: test V6AB historical theme mapping`。新增 `v6ab_theme_mapping_experiment.py`，离线测试“AI 子主题证据不足时回到父主题”的候选映射，不改正式 classifier/PIT replay/模拟盘。结果：`ai_child_low_fact_to_parent` 年化 +32.00%，较 guarded +0.07pp，Sharpe +0.00，2020 相对 V2 优势从 +0.92pp 提升到 +1.83pp，active 29，changed snapshots 4；但提升低于晋级阈值，decision=`NO_THEME_MAPPING_PROMOTION`。结论：方向有效但证据不足，保留为 WATCH/研究候选；下一步应把它和更完整的 historical evidence/fact precision 合并验证，而不是单独晋级。
- [代码] V6AB 父/子主题冲突映射实验取得更明确进展，提交 `a91c7fa feat: test V6AB parent theme conflict mapping`。新增候选：当 `ai_platform` 与父主题 `technology` 同时在 BOOST 且无 OVERRIDE 时，把 `ai_platform` 合并回 `technology`；泛化版则把 AI 子主题与父主题冲突时回父主题。最新 theme mapping 实验：`platform_parent_conflict_to_technology` 年化 +32.30%，maxDD -15.68%，Sharpe 1.25，较 guarded +0.36pp，2020 vs V2 +4.62pp，2024-2026 vs V2 +3.38pp，active 29，changed snapshots 5；日报 decision=`REVIEW_THEME_MAPPING_CANDIDATE`。映射命中 2020-06、2020-07、2023-07、2024-01、2025-07，正好对应此前 gap review 暴露的 technology 被 ai_platform 挤掉问题。仍不动模拟盘；下一步应为该候选单独跑 attribution/promotion gate，检查是否只是修 5 个历史月份、是否有隐性损伤。
- [代码] 同步新增 `v6ab_macro_regime_evidence_seed.py`，生成 2020 liquidity/technology/precious metals、2022 energy/rate shock、2023 broad technology/AI transition 的 date-stamped macro regime evidence。试验默认接入后没有净提升，guarded 年化基本不变且 2020 小幅回落，因此未接入默认 PIT replay，仅保留为研究输入，后续需和主题映射/主线强弱排序组合验证。
- [代码] V6AB 父/子主题冲突候选已升级为正式候选审查，并新增 Theme Hierarchy Diagnostics。`v6ab_theme_mapping_candidate_review.py` 单独评估 `platform_parent_conflict_to_technology`：年化 +32.30% vs V2 +31.83%，maxDD -15.68% 持平，Sharpe 1.25 vs 1.23，2020 +34.20% vs +29.58%，2024-2026 +60.78% vs +57.40%；但 active rebals=29<30 且 OVERRIDE=0，decision=`RESEARCH_OVERLAY`，模拟盘 `NO_CHANGE`。新增 `v6ab_theme_hierarchy_diagnostics.py` 并接入 daily evolution：child BOOST 样本 22，merge_to_parent 4，override_ready_research 1；诊断要求子主题独立必须有相对父主题的市场/趋势领先，不能只因证据多就 OVERRIDE。完整 daily 通过，新增步骤 `theme_mapping_candidate_review` 与 `theme_hierarchy_diagnostics` 均 OK。下一步不是放宽 gate，而是补 date-stamped、可差异化的主线证据，让真正独立的 child theme 能产生 OVERRIDE。
- [代码] V6AB 新增 `v6ab_override_evidence_candidate_review.py` 并接入 daily evolution，用来审查 child theme 是否有可差异化、PIT 可见的 OVERRIDE 事实证据。规则要求 actionable event facts、主题关键词命中、跨 ticker 广度、相对父主题市场领先和证据质量优势；不再把 AMZN North America sales 这类泛化收入增长误算为 `ai_platform` 事实。最新完整 daily 通过：reviewed child rows=22，`override_candidates=0`、`watch=0`、`metadata_reject=22`。结论：当前 child theme BOOST 大多仍由 filing metadata 和非差异化事实支撑，不能产生 OVERRIDE；下一步应定向补 HBM/AI memory、AWS/Azure/cloud AI、optical/networking/datacenter 等带日期、带经营事实、跨公司验证的 evidence，而不是放宽 gate 或继续堆复杂风控。


- [22:34] [发现] 长期目标已确认：V6AB 与 A股 Radar 都要演进为小型、可用、持续进化的主线识别/表达/复盘系统；共同链路为 当期可见信息 -> 判断真实主线 -> 选择表达工具 -> 控制替换风险 -> 复盘归因 -> 晋级/降级。V6AB 负责美股/海外主线轮动，A股 Radar 负责 A股市场实现。两者共享方法论、工程机制和复盘框架，但不共享具体规则、阈值、交易动作；跨市场迁移默认 RESEARCH_TRANSFER，必须本市场独立验证。已归档到 系统优化升级依据/V6AB_A股Radar_长期目标_可持续进化主线系统_20260522.md。
- [23:34] [发现] V6AB qualified legacy preservation forward paper WATCH 已实现并接入 daily evolution：新增 v6ab_legacy_preservation_forward_watch.py，按日记录 V2 / original PIT / qualified preservation 三套选择、legacy protection 是否触发、触发理由和被阻止的替换；输出 backtest_results/v6ab_legacy_preservation_forward_watch/latest.{json,md,csv} 以及桌面 LATEST daily/weekly WATCH 报告，并在 V6AB_Daily_Mainline_Report_LATEST.md 展示。2026-05-22 截面 decision_date=2026-05-19，qualified protection 触发，preserved=precious_metals，blocked=ai_optical:US.SMH。模拟盘仍保持 V6AB_SIM_CANDIDATE_V2_DYNAMIC_B_SIZING，NO_CHANGE。
- [23:49] [发现] V6AB qualified legacy preservation 第二步复核已完成：新增 v6ab_legacy_preservation_trigger_review.py，复核 2026-05-19 forward WATCH 触发样本。结论 REASONABLE_WATCH：precious_metals 中期趋势仍在（SLV 6M/12M 强），但 1-3M 回落，不能视为短期确定赢家；被拦截的 ai_optical 由 AAOI/LITE/COHR 等极端动量驱动，且无 OVERRIDE。继续 WATCH，不替换 V2、不升 paper sim。morning_brief 已接入 V6AB WATCH 待办：连续 ledger 观察、触发复核、非 AI 历史主线证据补强、WATCH 晋级条件草案，全部标明不改变 V2 模拟盘。
### Claude

- [18:39] [发现] V6AB PIT: added override evidence gap review; improved event fact extraction for ai_memory/ai_platform; reran SEC fact ledger with short timeout; override evidence improved from 0 to 3 candidates + 1 watch in daily, PIT guarded ann now 32.05% vs V2 31.83%, still RESEARCH_OVERLAY/no sim change.
- [19:03] [发现] V6AB PIT: added offline override candidate backtest. Legal/fair-use/copyright AI text now rejected as positive fact noise. After rerun, override evidence candidates reduced to ai_memory 2021-01/2021-02 only; ai_platform 2025 downgraded to WATCH. Offline override candidate V6AB ann 32.38% vs V2 31.83%, 2021 improves, but one override month has -9.53pp vs V2, so decision remains REJECT_FOR_NOW / no sim change.
- [20:51] [发现] A股 Radar: added V6AB transfer review diagnostic. It applies PIT boundary, fact precision, mainline/expression separation, and promotion gates to A-share Radar. Current tier PAPER_TRADE_ONLY, not real-money: mainline/expression pass initial simulation readiness, but blockers remain sample_size_lt20 and strict_tracker_evaluated_lt20.
- [20:55] [发现] System principle added: V6AB and A-share Radar may share methodology/engineering framework but must not directly share market-specific rules, thresholds, signal meanings, or trading actions. Cross-market transfer defaults to RESEARCH_TRANSFER and requires source/target/scope/not_allowed_scope/local validation before any promotion. Canonical doc: /Users/zhangkun/Desktop/AI个人投资公司/系统优化升级依据/V6AB_A股Radar_双线迁移防污染原则_20260522.md
- [21:00] [发现] Cross-market sync mechanism added. New cross_market_research_sync.py generates SHARE / QUARANTINE / VALIDATION_QUEUE plus a reusable prompt. It reads latest V6AB daily and A-share transfer review, syncs transferable methodology, and quarantines market-specific rules/thresholds. Integrated into A-share daily loop; output: 报表输出/LATEST/跨市场研究同步_LATEST.md.

---

## 2026-05-23

### GPT

- [00:02] [发现] PDD 主仓压力点已启动处理：用户反馈 PDD 跌至约93美元并后悔中概持仓。已新增公司研究/PDD/PDD_财报前压力复盘_20260522.md，结论为 NO_ADD_PRE_EARNINGS / HOLD / POST_EARNINGS_REUNDERWRITE：财报前不加仓、不卖CSP、不因后悔情绪直接清仓；财报后若收入失速+利润率恶化+管理层解释差，按既有规则减仓300-400股至风险预算内。已将 events_calendar PDD Q1重估日期修正到 2026-05-27，并修正 decision_log 目标日期，保留原始 2026-05-17 HOLD 决策不变。
- [00:14] [发现] 完成 AMZN AI-Core SOP v2.6 首轮估值：报告写入 公司估值/AMZN_估值报告_20260523_SOPv2.6版.md；结论 Research Only，V_base $253、V_floor $91、Bull $424，当前约 $268.5 高于 V_base，PRICE_GATE FAIL，V_option 按概率加权为 $0；已将 AMZN 加入 investment_screener/watchlist.json，高优先级观察但不建仓、不替换现有主仓。
- [00:25] [发现] 完成三项组合级工作：1) NVDA 财报后仓位纪律报告写入 公司研究/HQ_Compounder重估/NVDA_财报后仓位纪律_20260523.md，结论 HOLD_NO_ADD，8%-10%核心、10%-15%趋势增强可持有，$220-$240且集中度下降才复核补仓，$360-$400无进一步上修复核降趋势增强仓；2) AI-Core 候选横向表写入 系统优化升级依据/AI_Core候选横向比较表_20260523.md，排序 ADBE > NVDA持有 > AMZN观察 > MSFT观察 > GOOGL研究；3) 主仓风险预算总表写入 知识库_v1/01_Portfolio/主仓风险预算总表_20260523.md，明确 PDD/腾讯/NVDA/泡泡玛特/美的/现金BIL 的身份、目标区间、加减仓触发。watchlist 已将 NVDA 财报后 V_base 更新为 $305、floor $210、ceiling $420。
- [12:03] [发现] 完成 V6AB 防守层归因与连续防守实验：新增 v6ab_defense_layer_attribution.py 和 v6ab_continuous_defense_experiment.py。归因显示 V2/turnover-guarded/qualified legacy 的 MaxDD 都发生在 2020-02-19 -> 2020-03-16，平均 hedge 22.89%，防守已触发但 GLD 在窗口贡献 -2.54%，V6A 贡献 -4.66%，B sleeve 贡献 -7.84%；Deepseek 的同一压力窗口观察成立，但不能简单说只由防守层决定。MaxDD 外 overhedge audit 显示防守触发约 1152 天、overhedge 约 370 天、误触率约 32%，false hedge drag 约 -67%，说明优化价值更可能在减少非灾难月误防守。连续防守实验第一轮未通过：baseline V2 31.83%/-15.68%/Sharpe 1.23；连续 GLD+BIL/多资产版本年化和 Sharpe 均下降，cash-first 虽把 MaxDD 降到 -14.98%但年化降至 29.62%、Sharpe 1.17。结论 NO_DEFENSE_PROMOTION：不改 V2，不加复杂防守层；下一步若继续，只研究 overhedge filter/误触复核。
- [12:26] [发现] A股 Radar 按新方向升级为 Phase 1A 主线识别/短线表达/交易纪律训练系统：已读取 Deepseek 工作流记录 /Users/zhangkun/WorkBuddy/2026-05-23-11-30-26/.workbuddy/memory/2026-05-23.md，并将关键原则写入 A股短线Radar每日执行手册_v1.md。核心改动：纯概念排除改为概念持续性校验；A股频率采用每日记录、周度主线复盘、双周诊断；Phase 1A 先看纪律指标而非收益，30笔完整样本前不改规则。morning_brief 已接入交易日 MED 提醒：A股 Radar Phase 1A 纪律记录；晚间指导邮件模板已显示 30笔前不改规则、概念持续性校验、收盘复盘需记录信号执行/止损失效/主观干预/复盘覆盖。
- [12:37] [发现] A股 Radar 进一步明确为“中频主题轮动训练系统”，不是打板/高频短线：目标是提前识别政策/产业/资金主线，在启动初期或分歧回踩时轻量埋伏，主线冷却后退出，尽量每天低频确认而非秒级盯盘。新增系统文档 系统优化升级依据/A股Radar_中频主题轮动定位_20260523.md，并更新 A股短线Radar每日执行手册_v1.md、morning_brief 和晚间指导模板。Phase 1A ledger 必须记录信号来源、为什么是刚开始、计划动作、模拟入场、冷却信号、模拟收益、主观干预和复盘结论；30笔完整样本前不改规则。
- [15:28] [代码] V6AB/A股人工主题证据链路继续推进：修复 Seeking Alpha Trending News 免费标题解析，TICKER +/-pct 行现在归入 seeking_alpha_news_title；短 ticker/公司关键词改为词边界匹配，避免 metals 被误判 META。Theme Evidence ledger 已按 2026-05-23 重生成：64 条，US/V6AB 64，免费标题 47、Premium 标题 17，到期复核 0。morning_brief 已接入近3天 V6AB 高价值人工证据摘要，作为“今日需人工复核”提示，明确需主源验证且不改变 V6AB V2 模拟盘。当前证据主要支持 AI semis/NVDA/HBM/光模块/datacenter/cloud 软件仍是需要跟踪的候选线索，但多数只是标题级，不能作为 OVERRIDE 或替换 V2 的证据。
- [15:56] [代码] A股 Radar 官方/准官方白名单自动扫描器第一版已落地：新增 a_share_official_policy_scan.py 与 a_share_official_policy_sources.json，只扫描固定白名单公开页面（中国政府网、发改委、工信部、证监会、能源局、上交所、深交所），按主题关键词归类到人形机器人、半导体设备/国产替代、低空经济、算力/数据中心、电力设备/储能、设备更新/新型工业化、商业航天、资本市场等。输出 A股官方政策白名单扫描_LATEST.{md,json,csv}，标注 needs_manual_review 与失败源；不绕登录/验证码/付费墙，不作为交易信号，只用于 Phase 1A evidence 与人工复核。已接入 a_share_radar_daily_loop 和 A股晚间指导。2026-05-23 联网验证命中发改委“郑栅洁主任赴上海人工智能实验室调研”，主题=算力/数据中心，置信度94；工信部栏目 403，后续作为人工补查/备用源优化。
- [16:07] [代码] A股 Radar 信息源稳定化继续推进：官方白名单扫描器改用浏览器 UA，工信部由 403 恢复为可访问；源配置扩展到 10 个白名单源（政府网、发改委、工信部、科技部、财政部、证监会、能源局、发改委产业、上交所、深交所），支持 source.list_urls 多栏目扫描，并移除无效发改委 404 备用 URL。官方扫描结果已自动并入 Theme Evidence ledger，source_type=auto_official_policy，生成 5/10/14 天复核；2026-05-23 ledger 变为 65 条，其中 A股 1 条、US/V6AB 64 条，发改委“郑栅洁主任赴上海人工智能实验室调研”进入算力/数据中心 evidence，D5 到期复核。A股 INBOX 顶部规则已改为自动源优先、人工只补失败/需复核官方源、巨潮/交易所公告和有政策产业支撑的媒体异动。morning_brief 已显示官方扫描状态/命中数/失败源，晚间指导已显示官方政策扫描区块。
- [16:16] [代码] Daily email 已补充收尾提醒：morning_brief 的 workflow 现在每天显示 A股官方信息源稳定性巡检（失败源>0 自动升 MED），提醒查看官方白名单扫描、失败源/连续空结果时让 AI 优化 URL/RSS/关键词，并检查官方政策是否与富途板块热度和候选结构共振；A股人工 INBOX 与 V6AB Theme Evidence 录入/清理提醒仍保留在 daily email。
