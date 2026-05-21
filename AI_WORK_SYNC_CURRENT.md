# AI 工作同步 CURRENT

- Last updated: `2026-05-21 22:34:11`
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

## 2026-05-20

### GPT

- [11:07] [决策] 2026-05-20 冷启动口径修正：README_CURRENT.md 不再把旧 Iron Condor 写作生产系统；当前统一为 Daily Board / Central Risk Board、V6-A 小额人工 pilot、V6-B research/SIM、A股Radar Phase 1A、Value Wheel analyze-only、V3/IC legacy paused。所有模块必须服从统一目标：在不牺牲长期安全性的前提下相对安全地快速增长资本。
- [11:10] [代码] 补齐 2026-05-19 X Radar Daily 的 High 后续动作：GOOGL Google Search AI化已从日报正文落到 x_radar_signal_trial.csv、investment_screener/watchlist.json notes 和 events_calendar 2026-05-22 复盘事件；AI infra 13F long + semi put 对冲此前已在 13F 学习中落到 institutional_hedge_signal / crowding_penalty / reflexivity_score / macro_regime_fit / position_role 字段与 6月1日 V6-B/Radar 刷新清单。
- [11:23] [代码] 把13F学习从文档升级为系统输入：新增 us_radar_13f_system_input_seed.csv 和 us_radar_13f_system_input.py，生成 backtest_results/us_radar_13f_system_input/latest.{json,csv,md} 并同步桌面 LATEST；morning_brief.py 已读取 13F 系统输入，将 GOOGL/IREN/NVDA 等 P0 动作和 6月1日 V6-B候选刷新推入 Daily Board。13F仍禁止直接买卖，只用于候选质量、风险控制、反身性和研究优先级。
- [11:41] [代码] 建立估值体系自动路由：v2.5用于传统/普通质量股，AI-Core v2.6用于AI平台/软件/半导体，AI Infrastructure v2.7用于NEE等AI电力/数据中心/电网/矿转算力；morning_brief已接入路由动作，NEE会以HIGH提示走v2.7，估值结果必须回写watchlist/radar_order_valuation_seed/events_calendar等系统入口。
- [11:54] [代码] 完成NEE AI Infrastructure SOP v2.7估值：V_floor 62-70，V_base 78-88，V_AI_infra_option 6-12，risk-adjusted value 84-96，Bull 105-120；当前约89-91，结论FAIR_BUT_NEEDS_PULLBACK / Research P1 / 不买正股。已回写radar_order_valuation_seed、screener/watchlist和events_calendar，后续跟踪Dominion审批、large-load tariff、rate base/capex recovery及横向比较CEG/VST/GEV/ETN/XEL/SO/DUK。
- [12:20] [代码] OpenD历史K线额度恢复后按低消耗顺序推进：第一批仅补ANET/TSM/MU/AMD/AAOI/ASX/LITE到2026-05-19；同时补齐V6-A最小核心池AMZN/AVGO/GOOGL/META/MSFT/NVDA/BIL/GLD/SPY/QQQ到2026-05-19，刷新V6-A deterministic replay并解除signal_freshness stale blocker，新plan-only release gate PASS；Radar主线扫描显示AI算力与数据中心/二阶扩散、missing cache=0，Missing Review coverage gaps=0但critical misses=4（NOK/MRVL/COHR/AAOI）。未执行交易，未做泛化全量回测。

---

## 2026-05-21

### GPT

- [00:32] [代码] V6AB 已新增 PIT Evidence Ledger + historical classifier replay 管线：`v6ab_pit_evidence_replay.py` 按 `source_date/as_of/last_updated` 做 point-in-time 可见性过滤，并让 `v6ab_mainline_classifier.py` 的市场分数按每个 asof 截断本地价格缓存，避免未来价格泄漏。`v6ab_daily_evolution.py` 已接入 `pit_evidence_classifier_replay` 与 `pit_classifier_bridge_backtest` 两步。
- [00:32] [发现] 最新 PIT replay 区间 `2012-05-21 -> 2026-05-19`，seed evidence 73 条，但现有本地历史非价格证据覆盖不足：169 个历史快照中 active allowlist 为 0；2026-05-19 仅可见 56 条证据，且无 2026-05-20 的 13F seed，因此仍 fallback 到 V2。
- [00:32] [回测] PIT classifier bridge 已接入 V6AB 回测并生成桌面 LATEST 报告。结果：`baseline_v2_v6ab_dynamic_b` 年化 +31.83%、maxDD -15.68%、Sharpe 1.23；`pit_classifier_v6ab_dynamic_b` 年化 +31.83%、maxDD -15.68%、Sharpe 1.23；PIT active rebals = 0。结论：管线防泄漏接通，但当前 PIT 版本等同 V2，不能替换模拟盘。
- [00:32] [决策] V6AB 模拟盘继续保持 `V6AB_SIM_CANDIDATE_V2_DYNAMIC_B_SIZING`，动作仍为 `NO_CHANGE_BACKTEST_ONLY`。下一步不是拉泛化 K 线，而是补更完整的历史 evidence ledger，尤其是 2020、2022、2024 前后的真实主线证据；若新增主题/ticker 缺价，再按最小清单拉 K 线。


- [12:08] [代码] V6AB PIT historical evidence 管线继续推进：SEC historical harvest 已把 8-K items/6-K/10-Q/10-K 映射为 earnings_release、business_update、investor_presentation、material_agreement、quarterly_report、annual_report 等可解释 evidence；PIT replay 默认读取 backtest_results/v6ab_historical_evidence/latest.json；mainline classifier 新增 historical_depth_score（单独来自 SEC/历史公开文件，不伪装成 institutional）。最新 PIT replay seed evidence 1647，allowlist 快照 23/169，latest allowlist=semis_ai；PIT bridge 接入 V6AB 后 active rebals=24。结果仍未通过：V2 V6AB 年化 +31.83%、maxDD -15.68%、Sharpe 1.23；PIT V6AB 年化 +31.08%、maxDD -16.13%、Sharpe 1.15，2024-2026 年化 +55.40% vs V2 +57.40%。结论：PIT 管线进展有效但不晋级，模拟盘继续 V6AB_SIM_CANDIDATE_V2_DYNAMIC_B_SIZING，不动。
- [12:45] [代码] V6AB PIT 继续按‘验证主线识别命题’推进：新增 historical taxonomy，让 PIT replay 在历史期可识别 broad_beta、technology、precious_metals、energy_resources、financials、industrials_infra、utilities_power、consumer_discretionary 等当期主线，而不是用 2026 AI 分类解释全历史；PIT replay 默认 taxonomy=historical，active snapshots 从 23/169 提升到 68/169。新增 v6ab_pit_vs_v2_attribution.py，输出 PIT vs V2 月度 attribution、hard replacement 与 overlay 差异，并接入 v6ab_daily_evolution。修复 run_pit_v6b 状态泄漏：每个 rebalance 月开始前恢复完整 V2 theme set，避免连续 active 月份继承上月过滤后的 universe。最新结果仍不晋级：V2 V6AB 年化 +31.83%、maxDD -15.68%、Sharpe 1.23；PIT hard V6AB 年化 +26.48%、maxDD -15.80%、Sharpe 1.04；PIT overlay V6AB 年化 +29.84%、maxDD -16.54%、Sharpe 1.17。结论：historical taxonomy/overlay 方向更可信，但 PIT 目前只能作为候选增强，不能排他替换 V2；模拟盘继续不动。
- [13:37] [代码] V6AB PIT 按防过拟合路线新增 signal tier 框架：每个 theme 现在输出 WATCH/BOOST/OVERRIDE。规则只用状态、market、breadth、evidence_count、risk_penalty、mainline_score，不针对年份/主题调参；WATCH 不影响回测，BOOST 只做 overlay，OVERRIDE 才允许 hard replace。PIT replay 输出 watchlist/boost_allowlist/override_allowlist；bridge 新增 pit_tier_* 候选；attribution 新增 tier summary。最新结果：当前无 OVERRIDE，67 个 active rebals 全是 BOOST，因此 tier 版等同 overlay；V2 V6AB 年化 +31.83%、maxDD -15.68%、Sharpe 1.23；PIT tier V6AB 年化 +29.84%、maxDD -16.54%、Sharpe 1.17。Tier attribution：WATCH 102 月 sum delta -1.13%，BOOST 66 月 sum delta -19.34%，OVERRIDE 0。结论：当前 PIT 证据尚不足以获得排他权，不能晋级；下一步应提高 BOOST 质量/证据事实抽取，而不是放宽 OVERRIDE 阈值。模拟盘继续 V2，不动。
- [14:07] [代码] V6AB Event Fact Ledger v1 已实现并接入 PIT replay 默认 extra evidence：新增 v6ab_event_fact_ledger.py，从 SEC/IR 文档原文下载/缓存到 sec_doc_cache，规则抽取 revenue_acceleration、orders_backlog、cloud_data_center、ai_accelerator、inventory_correction、demand_slowdown、margin_pressure、supply_constraint 等 event facts。v1 强调宁缺毋滥，已多轮收紧风险因素/依赖供应商/可能性语境，避免把 filing metadata 或风险段落误判为正向事实。当前试跑扫描 250 篇 SEC 文档，抽取 266 条 facts，failures=0；PIT seed evidence 从 1647 增至 1913。结果未改善：V2 V6AB 年化 +31.83%、maxDD -15.68%、Sharpe 1.23；PIT tier V6AB 年化 +29.82%、maxDD -16.54%、Sharpe 1.17；BOOST 65 月 sum delta -25.80%，OVERRIDE 仍为 0。结论：event fact 方向必要，但 v1 事实层仍偏粗，暂不晋级、不调阈值；下一步应提高 fact precision/主题映射质量，而不是为了赢回测放宽规则。模拟盘继续 V2。
- [15:57] [代码] V6AB Event Fact Ledger precision v2：新增 fact_quality/context_role/numeric_present/actionable，并默认只让 actionable facts 进入 PIT evidence；新增主题二次映射 remap_theme，把 AWS/cloud/software 映射 technology，wireless/RF/Apple supply 映射 semis_ai，HBM/GPU 映射 semis_ai，networking/optical 映射相应主题；LOW/risk_factor/accounting_definition/generic context 不进入 classifier。250 篇 SEC 文档重跑后 facts 从 266 降到 198，其中 HIGH 120、MEDIUM 78；risk_fact 142、actual_result 56；主题分布从过度 ai_networking 改为 ai_networking 165、technology 15、ai_platform 10、semis_ai 6、ai_optical 2。结果略改善但仍不晋级：PIT tier V6AB 年化 +29.78%、maxDD -16.54%、Sharpe 1.17；BOOST sum delta 从 -25.80% 改为 -24.54%，2020 overlay/tier delta 从 -7.50% 改为 -6.61%；OVERRIDE 仍为 0。结论：precision/映射方向正确，但事实层仍需更结构化的 MD&A/表格解析；继续不调阈值、不动模拟盘。自动进化工程化方向：后续应建立候选规则生成 -> PIT验证 -> attribution评分 -> 晋级/降级/回滚的闭环，而不是让系统直接改生产策略。
- [16:55] [决策] NVDA FY2027 Q1 经营数据和估值已完成财报后更新：官方 Q1 收入 $81.615B、Data Center $75.2B、non-GAAP EPS $1.87、FCF $48.554B，Q2 收入指引 $91B；H20 中国限制带来 Q1 约 $2.5B 未发货和 Q2 预计约 $8B 影响，但未破坏全球 AI data center 需求曲线。结构化数据录入 `/Users/zhangkun/Desktop/AI个人投资公司/公司财报/经营数据/NVDA_FY2027Q1_20260520.json`，估值更新写入 `/Users/zhangkun/Desktop/AI个人投资公司/公司估值/NVDA_26Q1经营数据与估值更新_20260521.md`，并同步 overview 与 26 年策略计划。结论：thesis 上修，V_base 约 $285-$325，当前动作 HOLD_NO_ADD；允许保留 10%-15% 趋势增强仓，但不因强财报自动新增。
- [17:24] [代码] V6AB PIT tier 规则继续收紧并修复归因口径：market_only 历史主题如果缺少事实证据，最多 WATCH，只有极强市场确认或有证据才 BOOST；pit bridge 的 tier 模式改为只有 BOOST/OVERRIDE 才算 PIT active，WATCH 回到 V2 baseline；同时修复 `pit_signal_tier` 未随月度 preview 保存导致 attribution 误标的 bug，并在 attribution period summary 增加 tier active。最新结果仍不晋级但更接近 V2：V2 V6AB 年化 +31.83%、maxDD -15.68%、Sharpe 1.23；PIT tier V6AB 年化 +30.92%、maxDD -16.44%、Sharpe 1.20，PIT tier active rebals 32，2024-2026 年化 +58.16% 略高于 V2 +57.40%，但全区间和回撤仍不足，模拟盘继续 `V6AB_SIM_CANDIDATE_V2_DYNAMIC_B_SIZING` 不动。
- [20:58] [代码] V6AB P0 后视镜暴露审计已实现：新增 `v6ab_v2_hindsight_audit.py`，输出 `backtest_results/v6ab_v2_hindsight_audit/latest.*` 与桌面 LATEST `V6AB_V2_Hindsight_Audit_LATEST.*`。审计复现 V2 baseline：V6AB 年化 +31.83%、maxDD -15.68%、Sharpe 1.23。压力测试显示 V2 结构底座有效但确有静态赢家依赖：去掉 `semis_ai` 后 V6AB 年化降至 +25.13%、Sharpe 1.06；proxy-only 降至 +22.12%、Sharpe 0.92；去掉 top5 贡献 ticker 后降至 +26.44%、Sharpe 1.09。结论：这不否定 V2 作为当前模拟盘版本，但强化了下一步 PIT 主线识别的必要性；PIT 候选晋级时应同时要求接近/超过 V2，并降低/解释 V2 的后视镜依赖。模拟盘继续不动。
- [21:18] [代码] V6-A 真实 5k pilot 订单/仓位 reconciliation 已完成：修复 `v6a_real_reconciliation.py`，新增 broker 查询超时、历史订单查询、账户持仓快照和成交增量防重复入账；补回 `cash_alpha_v3_repo/futu_account_snapshot.py` 只读账户快照模块，修复 daily gate 缺依赖问题。通过本机 Futu OpenD 只读查询确认 2026-05-20 六笔订单全部 `FILLED_ALL`：AMZN 卖 3@260.10、AVGO 卖 1@412.88、BIL 卖 3@91.56、GLD 卖 1@412.20、GOOGL 买 1@387.66、NVDA 买 5@221.56。本地 V6-A managed state 已更新为 AMZN 1、AVGO 1、BIL 3、GOOGL 3、NVDA 5，pending=0。复跑 guarded runner plan-only：release gate PASS、live quote/account PASS、signal freshness PASS、无 executable orders，仅因 `no_executable_orders` BLOCKED，表示当前已在目标仓位且不会自动下单。V6-A 仍不是无人值守自动买卖；真实执行仍需 `--execute-real` + 手工确认短语。
- [21:38] [代码] V6-A guarded auto-execution v1 已实现但默认关闭：新增 `v6a_auto_guarded_executor.py`、`v6_strategy_lab/configs/v6a_auto_execution_policy_v1.json` 和 launchd 草案 `launch_agents/com.dingcle.v6a.guarded-auto.plist`。机制：外层 auto wrapper 先检查 `auto_enabled`、底层 runner `auto_real_orders_allowed`、kill switch、交易窗口、美股工作日、每日执行次数、pending orders、pre-reconciliation；再跑 `v6a_guarded_runner` plan-only，只有 release/quote/account/managed-state/notional 全 PASS 且确有 executable orders 时才调用 `--execute-real` + confirm phrase；下单后自动 post-reconciliation。默认双开关均为 false，未加载 launchd，不会自动下单。验证：disabled 模式直接 `POLICY_DISABLED` 不连 broker；dry-run/force-window 可走完整只读链路，当前 V6-A 已在目标仓位，返回 `NO_OP_AT_TARGET`。
- [21:45] [代码] V6-A 5k guarded auto-execution 已正式打开：用户确认 5k cash 本身就是测试金，希望避免错过买卖点。执行前验收：临时 auto-enabled dry-run 通过，无 blockers，当前 `NO_OP_AT_TARGET`；kill switch dry-run 修正后可明确 `BLOCKED`；真实配置 dry-run 通过，无 blockers。随后将 `v6a_auto_execution_policy_v1.json:auto_enabled=true`、`v6a_guarded_runner_policy_v1.json:execution.auto_real_orders_allowed=true`，安装并加载 `com.dingcle.v6a.guarded-auto` 到 `gui/501`。触发时间：北京时间 21:45、22:10（当前美股夏令时约 09:45、10:10），脚本窗口 `America/New_York 09:40-10:20`。自动执行仍受 release gate、live quote/account、pending=0、managed-state sell guard、notional/order count、每日一次真实执行、post-reconciliation 和 kill switch 约束；关闭方式：创建 `backtest_results/v6a_state/AUTO_EXECUTION_DISABLED` 或把 auto_enabled 改回 false。
- [21:50] [代码] V6 daily 邮件已接入 V6-A guarded auto 状态：`v6_reporting.py` 新增 `auto_execution` 摘要，日报/HTML 现在显示自动执行开关、底层真钱权限、kill switch、执行窗口、每日上限、最近 auto decision、blockers、最近订单数/金额、LaunchAgent 和关闭文件。日报 action 也会在 pending=0 且 auto 开启时显示“自动化已开启”；最新预览已修正为读取最新 gate 对应 preview，当前显示 gate 通过、预览订单数 0、pending 0、auto 最近 `NO_OP_AT_TARGET`。
- [21:58] [代码] V6AB P1 promotion gate 已实现并接入 daily evolution：新增 `v6ab_promotion_gate.py`，读取 PIT bridge backtest、PIT vs V2 attribution、V2 hindsight audit，统一输出 `REJECTED/WATCH/RESEARCH_OVERLAY/PAPER_SIM_CANDIDATE/PRODUCTION_ELIGIBLE`。Gate 明确要求候选接近 V2 全区间/Sharpe/maxDD/OOS，不能明显错过 2020/2022，成本受控，PIT active 样本足够，BOOST 月度质量不能长期拖累，必须有 OVERRIDE 才能证明可排他替换，同时必须披露 V2 对 semis_ai/top winners/proxy-only 的后视镜依赖。当前 `pit_tier_v6ab_dynamic_b` 被评为 `RESEARCH_OVERLAY`：年化 +30.92% vs V2 +31.83%，maxDD -16.44% vs -15.68%，Sharpe 1.20 vs 1.23，2024-2026 略优；但 2020 少 4.92pp、BOOST sum delta -16.59pp、OVERRIDE=0、2024-2026 tier attribution -3.26pp。结论：只能作为 V2 overlay/研究层继续，不进 paper sim，不动 V6AB 模拟盘。
- [22:19] [代码] V6AB P2 BOOST failure review 已实现并接入 daily evolution：新增 `v6ab_pit_boost_failure_review.py`，读取 PIT vs V2 attribution 与 PIT classifier replay，按最近 PIT snapshot 归因每个 BOOST/tier active 月份，输出 failure labels、theme scores、ticker priority、recommended fixes，并同步 `backtest_results/v6ab_pit_boost_failure_review/latest.{json,md,csv}` 与桌面 LATEST。最新诊断：BOOST/tier active 31 月，负贡献 17 月，sum tier delta -16.59%，win rate 41.94%；主要失败标签为 evidence_precision_risk、overboost_without_override、theme_dilution、expression_dilution、defensive_or_commodity_missed、turnover_drag、historical_taxonomy_mismatch。关键结论：方向不改，下一步优先修 BOOST fact precision、2020 historical taxonomy/regime mapping、主题表达/换手控制；模拟盘继续 `V6AB_SIM_CANDIDATE_V2_DYNAMIC_B_SIZING` 不动。
- [22:33] [代码] V6AB P3 增加 BOOST gate experiment，避免规则过严/误伤正样本：先试过一版硬门控（market-only 无事实不 BOOST、2022 前 ai_* 更高门槛、BOOST 最低 fact precision），完整 daily 跑数后 active 从 31 降到 19、BOOST sum delta 从 -16.59% 变 -17.73%、promotion 从 RESEARCH_OVERLAY 降到 WATCH，说明规则太严，已回退。随后新增 `v6ab_boost_gate_experiment.py`，只在 BOOST failure review 样本上离线模拟候选门控，不改 classifier/模拟盘，并接入 daily evolution。最新实验显示：简单删 market-only 无事实会误伤正样本（kept sum -24.54%，更差）；更有希望的是 `drop_defensive_conflict`（保留 27 月，删 4 个负月，kept sum +6.61%，positive damage 0）和 `drop_high_turnover_expression`（保留 28 月，删 3 个负月，kept sum +1.47%，positive damage 0）。下一步应把这两类做成温和 capped/降权规则，再跑完整 PIT 回测，不直接硬删主线。
### Claude

- [11:53] [发现] 统一早间邮件链路：central_risk_board.py 已接入 morning_brief 的今日动作清单和 stale-data workflow，邮件 HTML/MD 新增 Today's Workflow Actions 与 Open Todos；morning_brief launchd plist 已改为 --no-email，只生成内部文件不再单独发第二封。当前工具会话为 root/非登录GUI域，launchctl 用户域重载未成功，但 plist 语法验证 OK。
