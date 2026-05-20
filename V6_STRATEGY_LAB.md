# V6 Strategy Lab

- Status: active
- Created: 2026-05-06
- Scope: V6 主策略的持续研究、挑战、复盘、升级和淘汰机制。

## 一句话结论

V6 Strategy Lab 的目标不是证明 V6-A 永远正确，而是建立一个小型量化基金式流程：持续提出策略假设、验证 challenger、监控主策略、在失效前降权或替换。

## 研发总目标

V6 的长期目标是持续提升稳定性和收益能力，但两者必须用不同机制实现。

- `稳定性`：不是追求永远不回撤，而是让回撤可解释、可控、可暂停。主要依靠 pilot 执行质量监控、preflight gate、kill switch、managed state 防误卖、真实滑点/换手跟踪、极端年份/滚动窗口复盘。
- `收益能力`：不是频繁优化底层 engine 参数，而是优先通过 Universe 动态调优、V6-B 候选池验证、Allocator 权重分配、challenger 袖珍策略比较来提升。
- `执行原则`：Engine 保持经典、简单、稳定；Alpha 主要来自正确选择和更新可交易 Universe，以及在 Core / Dynamic / Defensive sleeve 之间做有证据的分配。
- `晋级原则`：任何收益增强都必须经过 standalone 回测、V6-A 对比、组合层回测、可交易性检查、模拟盘/live-forward 验证，不能因为近期涨幅好就直接进入生产。

## 收益目标分层

V6 的收益目标必须分层管理，不能把 `35%+` 年化当作默认预期。

- `18%-20%+`：保留底线。扣成本后若长期低于这个区间，要重新评估 V6 是否值得保留。
- `25%+`：核心门槛。达到这一层，V6 才有资格作为进攻仓的长期核心策略。
- `30%+`：优秀目标。说明 baseline、Universe 和执行质量形成了明显 alpha。
- `35%+`：进攻目标。必须依靠 `V6-A baseline + V6-B 动态 Universe + Allocator + 真实执行质量` 共同达成，不能作为默认假设。
- `45%-55%+`：组合右尾年份目标。只能来自 `主仓顺风 + V6 顺风 + Radar/Overlay 少数右尾样本` 的共同作用，不能要求 V6 单独承担，也不能为了追求这个区间破坏风控。
- `纪律要求`：不得为了追求 `35%+` 牺牲风控、kill switch、managed state、preflight gate 和验证纪律。

V6 的职责是提高资本效率，不是毁掉生活质量。系统可以争取高收益年份，但不能把高收益年份当成必须兑现的压力目标。

## 当前主策略

- 主策略：`V6-A ATTACK_EQUAL_REPLAY`
- 策略属性：美股高进攻动量 + 防守切换
- 当前阶段：`REAL_MANUAL_PILOT_ACTIVE`
- 当前定位：`$5,000` V6-A 已进入 Futu real manual pilot；managed state、reconciliation、日报、preflight gate 已打通，但 kill switch 仍保持 `ON`，无人值守自动实盘仍未开启
- 并行升级线：`V6-A core engine baseline/challenger` 已通过 `replay bridge` 独立产出 runner-compatible artifacts；当前与 legacy `ATTACK_EQUAL_REPLAY` live sleeve 分轨管理，避免把参数升级和执行验证混成一步

## 当前 V6 完整版状态（2026-05-20）

V6 完整版已从“研究组合”进入 `50,000 USD` 富途模拟盘验证阶段，但不改变 V6-A 小额实盘 pilot 的边界。

- `V6-A`：继续作为 `$5,000` 真实账户人工监控 pilot 运行。它负责验证真实成交、滑点、stale-data gate、managed state 和风险退出纪律；不需要再单独在模拟账户保留一套 V6-A 对照盘。
- `V6AB`：当前模拟盘生产候选为 `V6AB_SIM_CANDIDATE_V2_DYNAMIC_B_SIZING`，配置文件为 `v6_strategy_lab/configs/v6ab_sim_candidate_v2.json`。
- `V6-B`：不再被定义为固定 AI infra 主题策略，而是动态主线 / theme rotation / 候选池内相对强弱选择机制；顺风年扩权，逆风或高相关风险时缩权。
- `Overlay`：固定 `10% GLD` 已被否决；采用动态 `GLD/BIL/CASH` 防守 overlay，根据波动、相关性、回撤、GLD 趋势触发。
- `执行账户`：富途模拟账户重置后 API active SIM account 变为 `19429788`；`v6ab_sim_executor.py` 已改为自动解析当前 ACTIVE SIMULATE US 账户，避免继续使用旧账号 `19005590`。
- `当前模拟订单`：2026-05-20 已按 `50,000 USD` 策略资本提交 V6AB 模拟订单；富途返回 `SUBMITTED`，未失败，未成交，等待美股 RTH 成交后用 reconciliation 落仓。

当前 V6AB 模拟目标权重：

| ticker | target weight | role |
| --- | ---: | --- |
| `US.GOOGL` | `23.5%` | V6-A / V6-B 共同偏好的大型平台与 broad beta 表达 |
| `US.BIL` | `18.6%` | V6-B 内部现金/短债风险缓冲 |
| `US.NVDA` | `13.1%` | V6-A AI mega 核心暴露 |
| `US.AMZN` | `10.4%` | V6-B broad beta / 平台主线表达 |
| `US.DBC` | `7.2%` | resources / commodities theme |
| `US.SLV` | `7.2%` | precious metals theme |
| `US.AVGO` | `6.7%` | V6-A AI infra 核心暴露 |
| `US.GLD` | `4.0%` | 动态防守 / 黄金 sleeve 残余权重 |
| `CASH` | `9.4%` | 现金余量 |

最新 V6AB 研究基准：

| version | ann | maxDD | Sharpe | status |
| --- | ---: | ---: | ---: | --- |
| `V6-A standalone` | `+28.2%` | `-21.1%` | `0.99` | live pilot baseline |
| `V6-B guarded standalone` | `+25.7%` | `-24.3%` | `0.84` | alpha sleeve only |
| `V6AB V1 fixed B 30% + dynamic overlay` | `+29.5%` | `-18.6%` | `1.14` | superseded |
| `V6AB V2 dynamic B sizing + dynamic overlay` | `+31.8%` | `-15.7%` | `1.23` | current paper-sim candidate |

后续 V6 完整版工作只有两个核心目标：

1. `持续提升 alpha`：用 V6-B theme rotation、X Radar、13F 学习、Seeking Alpha、财报/估值、行业强度和候选池过滤，提高标的选择质量；任何新增信号必须进入回测、对照、模拟盘替换流程，不能只停留在文档。
2. `尽可能降低回撤`：优化 sleeve sizing、动态 overlay、crisis window 行为、A/B 相关性控制、stale-data / kill-switch / managed-state 执行纪律。

禁止事项：

- 不再开一套单独 V6-A 模拟账户长期跑，避免和 V6-A 真实 pilot、V6AB 模拟盘重复。
- 不因某个单一主题强而把 V6-B 固化成该主题策略。
- 不把 X Radar、13F、Seeking Alpha 或估值报告只做成展示文档；必须能反哺候选池、过滤器、权重、风控或复盘。
- 不在成交确认前把 pending orders 记为实际持仓；必须等待 reconciliation。

## V6AB 每日进化原则（2026-05-21 起）

从 `2026-05-21` 起，V6AB 的进化方式正式改为 `daily evidence loop`。这不是每日改策略、每日换仓，而是每日更新证据、主线状态、候选池排序和下一步动作。

核心定义：

- `V6-A`：继续作为稳健底盘、真实执行纪律和风险控制验证层。
- `V6-B`：升级为 `Mainline Radar + Mainline Classifier + Dynamic Stock Pool`，即主线进攻引擎。
- `V6AB`：用 V6-A 的稳定性承接 V6-B 的顺风主线进攻，并由动态 sizing / overlay 控制组合回撤。

每日进化闭环：

1. `Market Evidence`：自动更新主题 ETF、主题股票池、3/6/12 月相对强度、趋势、广度、回撤和 SPY/QQQ 对比。
2. `Narrative Evidence`：X Radar / 新闻 / 产业链扩散信息进入 evidence ledger，只用于候选主题、解释和确认速度，不直接触发交易。
3. `Fundamental Evidence`：Seeking Alpha、财报、指引、订单、capex 和盈利预期修正进入主题质量分和股票池排序。
4. `Institutional Evidence`：13F 作为慢变量确认层，只用于季度级主线持久性与高质量机构加仓验证，不做短线开关。
5. `Mainline State`：每个主题每日更新 `candidate / starter / confirmed / aging / failed` 状态。
6. `V6AB Feedback`：主线状态只通过三个接口影响系统：主题准入、主题内股票排序、V6-B sleeve 上限；任何变更必须再经过回测、V2 对比、模拟盘验证和人工确认。

执行入口：

```bash
python3 v6ab_daily_evolution.py --asof YYYY-MM-DD
```

当前 v1 输出：

- `backtest_results/v6ab_daily_evolution/latest_evidence_ledger.{md,json,csv}`
- `backtest_results/v6ab_daily_evolution/latest_mainline_classifier.{md,json}`
- `backtest_results/v6ab_daily_evolution/latest_daily_mainline_report.md`
- `/Users/zhangkun/Desktop/AI个人投资公司/报表输出/LATEST/V6AB_Daily_Mainline_Report_LATEST.md`

`2026-05-20` 首次运行结论：

- `AI Memory / Storage`、`AI Networking / Fabric`、`Semis / AI Compute` 为 `STARTER`。
- 暂无 `CONFIRMED` 主线，因此继续 fallback 到 `V6AB_SIM_CANDIDATE_V2_DYNAMIC_B_SIZING`。
- `b_sleeve_cap_hint = 30%`，但动作仍为 `NO_CHANGE_BACKTEST_ONLY`。
- ticker triage 前排：`MU / TSM / AVGO / SNDK / AMD / NVDA`。

执行纪律：

- 允许识别主线晚 `1-3` 个月，但不允许被假热点频繁骗仓。
- 没有确认新主线时，当前 `V6AB_SIM_CANDIDATE_V2_DYNAMIC_B_SIZING` 继续作为 fallback。
- X Radar、Seeking Alpha、13F、估值和人工判断必须能改变候选池、评分、确认状态、仓位上限或复盘结论；不能只停留在文档展示。
- 每日邮件必须提示 `今日人工 triage`，但用户只需要补充少量高价值语义信息；重复性数据采集由系统自动化。
- 任何从 V2 升级到 V3 的替换，都必须先证明 full-window、OOS、压力年份、V6AB 组合层和 live-forward 均优于或明显补足 V2。

## 双 AI 对照锁定的后续优化方向（2026-05-12）

Claude 和 GPT 独立分析后交叉验证，结论一致，差异仅在语气（Claude 更乐观，GPT 更保守）。共识锁定 4 条优化方向，作为后续所有 V6 工程实现的行动纲领：

1. **V6-A 执行质量和真实摩擦验证做满**
   继续 pilot，收集真实滑点、换手、资金摩擦数据，建立可信的 live OOS 记录。不提前开 kill switch，不跳过 2 周复盘。

2. **V6-B 做成真正的动态 universe refresh engine**
   不只是 Radar 清单，而是有完整回测验证、OOS 检验、可交易性核查的候选池生成机制。V6-B 通过验证前不给实盘权重。

3. **扩展低相关 sleeve / challenger，不只押一个 alpha 来源**
   机构的强大来自多个低相关因子的组合，而非单一神策略。V6-B 是第一步，后续考虑不同资产类别（港股某些板块）、不同时间尺度的互补信号。

4. **Allocator + Regime 做成正式治理层**
   负责权重分配和 sleeve 间风控，不负责追涨。必须有 regime 判断依据（市场状态 → 进攻 vs 防守权重），而不是静态权重。

> 共识定位：做"在某个细分中频方向里很强"的系统，不默认成为全市场全周期顶级大厂模型。真正护城河是 **Engine + Universe + Allocator + 风控工程 + 协作知识库** 这整套持续迭代系统。

---

## V6 长期研发方向

V6 的长期方向不是把一个策略越改越复杂，而是像小型量化基金一样：底层 engine 慢变，universe 动态更新，多个 sleeve 独立验证后再由 allocator 做组合层风控。

```text
V6 Engine = 固定底层规则：经典动量 / 相对强弱 / risk-on risk-off / 波动率控制 / 回撤刹车
V6 Universe = 总候选池：V6-A Core Pool + V6-B Dynamic Pool + Defensive Pool
V6-A Core Pool = 低频更新的 AI mega / mega tech 核心池，当前 baseline
V6-B Dynamic Pool = 动态主题扩散 / 候选池生成与验证机制；AI-capex 只是第一代训练主题，不是策略本体
V6-C Pool = ETF / 行业 / 全市场 meta-rotation，未来 challenger
Allocator = 风控与资金分配器，根据近期表现、相关性、回撤、regime 分配 Core / Dynamic / Defensive 权重
Options Expression Layer = 可选表达层，只在已有 V6/Radar edge 通过后评估期权结构；不替代 V6 正股/ETF engine
```

## 与全投资系统的关系

V6 不是孤立存在的。

它在整个 AI 个人投资公司里的正式位置已经锁定为：

- `价值投资主仓`：长期资本池
- `V6`：中频进攻/防守切换的收益增强层
- `Radar-Sourced Overlay`：小额右尾收益层
- `Research / Experimental Sleeves`：只负责验证，不默认进入生产
- `Options Expression Layer`：定义风险表达层，每个标的/策略都必须评估期权是否更合适，但可以明确结论为不使用期权

未来 `12` 个月的系统升级总路线见：

- `AI_INVESTMENT_COMPANY_12M_UPGRADE_ROADMAP.md`
- `CENTRAL_RISK_BOARD_SPEC.md`

### V6-B 的正式定义边界

`V6-B` 不能定义成 `AI-capex 策略`。如果把 V6-B 与单一主题绑定，那么主题周期结束时，策略本身也会一起失效。

V6-B 的正式定义应为：

- `V6-B = 动态主题扩散 + 瓶颈发现 + 候选池生成机制`
- `AI-capex` 只是第一代训练样本，因为它扩散路径清晰、瓶颈明确、验证数据多
- V6-B 的长期有效性来自 `Theme 可迁移 + Universe 可更新 + Engine 固定`

长期结构拆成三层：

- `Theme Layer`：识别当前最强的资本开支、利润扩散或供需错配主线。AI 只是其中一个阶段性主题。
- `Universe Layer`：针对该主线构建 point-in-time 候选池，靠扩散地图、瓶颈识别、预期上修、流动性和反证清晰度筛票。
- `Engine Layer`：不负责找主题，只负责在候选池里做入场、减仓、退出、risk-on/risk-off 和仓位控制。
- `Expression Layer`：在 V6-B 候选通过买点、流动性和风控后，比较正股/ETF、call debit spread、protective put、index iron condor 等表达方式；当前只研究，不自动实盘。

设计纪律：

- 不追求“永远有效的主题”，而追求“可迁移的 alpha 框架”。
- 未来即使 AI 主线降温，V6-B 也应能够迁移到新的强主线，例如电力升级、工业自动化、网络安全、医疗设备、周期重估或资源瓶颈。
- 允许替换 `Theme Layer`，但不应频繁改写 `Engine Layer`。
- 任何人都不应把当前 `AI-capex` 的研究样本误解为 V6-B 的永久定义。

研发路线：

1. `阶段 0：V6-A SIM-first 闭环`：先保证 V6-A baseline 的目标仓位、下单、退出、reconciliation 和 managed state 都能在模拟盘稳定运行。
2. `阶段 1：V6-B 单独回测`：只验证 Radar 动态池能不能赚钱，不能污染 V6-A baseline。
3. `阶段 2：V6-A vs V6-B 对比`：比较收益、回撤、Sharpe、OOS、rolling、黑天鹅、换手、可交易性。
4. `阶段 3：V6-A + V6-B 组合`：测试 `70/30`、`50/50`、动态权重等组合。
5. `阶段 4：V6-B 稳定贡献后升级`：只有通过 deterministic replay、release gate、live preview 和模拟盘后，才允许进入 V6 资源池优化层。

关键原则：

- `Engine Core` 必须经典、简单、可解释，不能因为 1-2 个月表现差就改。
- `Engine Parameters` 可以季度/半年做 challenger，但不能追着最近行情调参。
- Alpha 主要来自正确调整 universe，而不是过度优化 MACD/均线等短期参数。
- `V6-B` 不是整个 V6 Universe；它是动态候选池来源层，负责给 V6 Universe 提供新标的。
- Radar 是 `Research Input`，不是前台持仓层；V6-B 是动态 universe generator，最终下单仍由 V6 Engine + Allocator 决定。
- 任何新增 universe 都要证明增量收益，而不是因为最近涨过就加入历史回测。
- `V6-A` 是 baseline core pool，但不是永久冻结名单；它应低频维护，像指数委员会一样慢变，而不是像 Radar 一样快变。
- `V6-B` 不应演化成“一主题一策略”；正确方向是 `统一 engine skeleton + 少数 track-aware execution profiles`。
- 每个 V6-B 候选进入交易讨论前，必须补 `期权表达评估`：可以写 `NO_OPTION`，但必须说明为什么正股/ETF优于期权。
- V6-B 期权化的第一原则是 `V6 signal first, option expression second`。没有 V6-B edge，不允许用期权制造虚假进攻性。

### V6-B 新设计：Radar 供给 + 买点过滤 + 可选期权表达

V6-B 后续按三段式设计：

1. `Radar Supply`
   - 负责全市场主题识别、扩散链、missing opportunity review、external sample attribution。
   - 输出 point-in-time universe，不直接输出交易。

2. `V6-B Trade Filter`
   - 负责对候选做动量、趋势、回撤、流动性、chase_risk、trade_posture 过滤。
   - 只有通过过滤的候选，才允许进入 V6-B standalone / V6-A 对比 / allocator judgement。

3. `Options Expression Review`
   - 负责判断这次信号是否适合期权表达。
   - 默认生产路径仍是正股/ETF；期权只作为研究层或小额定义风险 overlay。

当前允许研究的 V6-B 期权表达只有三类：

| 研究线 | 适用场景 | 当前状态 |
| --- | --- | --- |
| `V6-B signal + call debit spread` | 强趋势、单腿 Call 太贵、希望定义最大亏损 | research only |
| `V6 sideways regime + QQQ/SPY iron condor` | 无强趋势、指数震荡、IV 有溢价 | research only |
| `V6 high-risk window + protective put` | V6/主仓风险同向过高，需要尾部保护 | risk tool research |

禁止：

- 把 V6-B 买入信号直接替换成裸 Call。
- 因为想提高收益率而跳过期权回测、IV、bid/ask、DTE、Delta 检查。
- 在 Central Risk Board 为 `RED` 时扩大期权预算。
- 让期权交易污染 V6-B 正股/ETF 回测样本。

## V6 调整治理：自动 vs 人工

V6 不追求“全自动频繁自我优化”。当前采用 `定期提醒 + 人工发起 + 证据晋级` 的治理方式。

| 组件 | 调整频率 | 自动化程度 | 规则 |
| --- | --- | --- | --- |
| `V6 Engine Core` | 半年或重大 regime 变化才考虑 | 不自动调整 | 只允许用 challenger 报告晋级，不能因短期表现差直接改生产规则 |
| `V6 Engine Parameters` | 季度复核 | 半自动研究，人工确认 | 可测试动量窗口、趋势窗口、再平衡频率、回撤阈值、top N，但必须走 OOS / rolling / black swan / robustness |
| `V6-A Core Pool` | 季度/半年低频复核 | 半自动扫描，人工确认 | 类似指数成分股维护；`慢变`，不是 `永远不变`；只允许因结构性失效、长期领导权转移或治理/可交易性问题调整 |
| `V6-B Dynamic Pool` | 周度观察，月度正式更新 | 半自动生成候选，人工确认入池 | 用 Radar、漏网复盘、主题扩散、预期上修和动量确认生成 point-in-time universe |
| `Allocator` | 周/月复核 | 先规则化，后续可半自动 | 作为风控层决定 Core / Dynamic / Defensive 权重，不是收益追逐器 |

当前执行口径：

- 每周邮件提醒：V6-A 状态、V6-B live-forward、是否触发异常、是否需要用户发起复盘。
- 每月邮件提醒：是否需要更新 V6-B Dynamic Pool，是否需要做 Missing Opportunity Review。
- 每季度邮件提醒：是否进入 Engine / Core Pool / Allocator revalidation。
- 任何 production 级调整，都必须先写入 `V6_STRATEGY_LAB.md`、AI Wiki 系统卡、Overview，再进入执行。
- 2026-05-11 起，V6-B SIM 暂停扩张；优先把 V6-A SIM-first 闭环跑稳定，V6-B 回到回测与动态 universe 生成器研发。

## 邮件报告要求

V6 需要像 V3 一样有定期邮件摘要，但邮件内容应偏“状态与提醒”，不直接自动触发真实交易。

当前已落地脚本：

```bash
python3 v6_reporting.py --period weekly
```

配置文件：

```text
v6_strategy_lab/configs/v6_reporting_policy_v1.json
```

输出目录：

```text
backtest_results/v6_reporting/
```

邮件默认关闭；只有显式传入 `--send-email` 才会尝试发送。

发送逻辑：

1. 优先复用 V3 的 `notifier.EmailNotifier`，读取本地 `.ic_env.local` 中已有的邮箱授权配置，默认收件人为 `quanyi_zk@163.com`。
2. 如果 V3 notifier 不可用，再 fallback 到 `V6_EMAIL_*` 环境变量。

邮件最小字段：

- V6-A 当前信号、目标持仓、实际持仓、偏离、回撤、异常订单
- V6-B 当前 universe、入池/出池候选、live-forward 表现、是否缺数据
- Allocator 当前建议权重：Core / Dynamic / Defensive
- 本周是否需要人工动作：`不动 / 复盘 / 刷新数据 / 重新 gate / 扩容讨论`
- 下一次固定复盘日期

邮件结论必须写成：

```text
本周动作：不动 / 需要用户确认 / 禁止实盘
```

不能把邮件做成自动下单触发器。

## 2026-05-10 今日已可落地事项

在 Futu 历史 K 线额度刷新前，今天先完成不消耗行情额度的工程底座：

1. `point-in-time universe` 格式固定
   - 配置：`v6_strategy_lab/configs/v6b_point_in_time_universe_seed_20260510.json`
   - 审计：`python3 v6b_universe_audit.py --config v6_strategy_lab/configs/v6b_point_in_time_universe_seed_20260510.json`
   - 当前种子池 9 个 active tickers，覆盖 `core_reacceleration / bottleneck_diffusion / turnaround_momentum` 三条轨。

2. `Allocator v1` 规则固定
   - 策略：`v6_strategy_lab/configs/v6_allocator_policy_v1.json`
   - 执行：`python3 v6_allocator.py --metrics <sleeve_metrics.csv>`
   - 当前默认逻辑：V6-B 没有通过 point-in-time / OOS / replay 前，权重固定为 `V6-A 100% / V6-B 0% / V6-C 0%`。

3. `V6-B release order` 固定
   - 先做 V6-B standalone。
   - 再做 V6-A vs V6-B。
   - 再做 V6-A + V6-B 组合。
   - 最后才允许 Allocator 给 V6-B 权重。

4. `V6-B 买入/选票/仓位/退出/评分系统` 固定
   - 策略：`v6_strategy_lab/configs/v6b_entry_sizing_policy_v1.json`
   - 评分覆盖：主题强度、基本面验证、预期修正、价格动量、流动性、拥挤/估值风险、反证清晰度、组合适配度。
   - 执行：`python3 v6b_score_universe.py --tag <tag>`
   - 当前输出：`v6_strategy_lab/scorecards/v6b_scorecard_20260510_seed.md`
   - 评分只决定研究排序，不是买入信号；买入仍需 V6-B standalone、V6-A 对比、Allocator 非零权重、risk-on 和 tradability 通过。

5. `评分 -> 回测配置` 接口固定
   - 执行：`python3 v6b_build_universe_config.py --tag 20260510_seed --scorecard v6_strategy_lab/scorecards/v6b_scorecard_20260510_seed.json`
   - 输出：`v6_strategy_lab/configs/generated/v6b_generated_universe_20260510_seed.json`
   - 当前生成四档：`v6a_base_only`、`v6b_eligible_only`、`v6b_watch_plus`、`v6b_full_active`。
   - 这一步保证未来回测不是手工改池子，而是按 point-in-time universe 和 scorecard 自动生成。

6. `cache-only probe` 已验证缺数据边界
   - 执行：`python3 v6b_radar_momentum_challenger.py --config v6_strategy_lab/configs/generated/v6b_generated_universe_20260510_seed.json --cache-only --tag generated_seed_probe`
   - 当前只有 `v6a_base_only` 可跑；V6-B variants 因 AMD、TSM、MU、ANET、WDC、INTC、AMKR、AMBA、CEVA 等缺历史缓存不能得出结论。
   - 输出：`backtest_results/v6b_radar_momentum/v6b_report_generated_seed_probe.md`

7. `验证分层` 固定为两轨
   - 轨道 A：`live-forward`，用当前 Radar 池在模拟盘持续记录，先跑至少 1 个月，工程稳定后再考虑小额 pilot。
   - 轨道 B：`synthetic historical Radar generator`，只用于历史回测，不能把今天才发现的赢家机械回填到过去。
   - 这两条轨道必须分开记账、分开报告、分开结论。

8. `2026-05-13 方法论校正` 已补做
   - 结论：Claude 那次 `ROUGH_TEST_NO_POINT_IN_TIME` 不应被理解成 `V6-B 历史表现测试`，只能降级为 `engine compatibility probe`。
   - 原因：脚本内部虽然在每个历史时点按当期动量选 `top_n`，但上游 Universe 仍然用了 `2026-05-10` 才定义好的候选族群覆盖更早历史。
   - 校正测试：
     - lookahead 版本：`python3 v6b_rough_test_yahoo.py --cache-only --tag lookahead_recheck_20260513`
     - entry-date 版本：`python3 v6b_rough_test_yahoo.py --respect-entry-dates --cache-only --tag entry_date_respected_20260513_strict`
   - apples-to-apples 对照结果：
     - `V6-B core_reaccel` lookahead：`AnnR +27.6% / Sharpe 0.79 / MaxDD -34.4%`
     - 同池 `entry_date respected`：`AnnR +9.0% / Sharpe 0.57 / MaxDD -9.3%`
     - `V6-AB blended` 在 `entry_date respected` 模式下与 `V6-A baseline` 基本一致，说明先前 uplift 主要来自过早激活 V6-B 名单，而不是已验证的历史 alpha。
   - 正确解释：
   - `lookahead rough test`：只回答“这类高波动周期 / 扩散链票与 V6-A 参数是否大致相容”
   - `entry-date respected probe`：只回答“如果不提前激活名单，之前 rough test 的结论会被压缩多少”
   - 两者都不能替代正式 `synthetic historical Radar generator`

9. `2026-05-13 synthetic historical Radar generator v1` 已落地
   - policy：`v6_strategy_lab/configs/v6b_synthetic_historical_generator_policy_v1.json`
   - generator：`python3 v6b_synthetic_historical_radar_generator.py --start 2018-01-01 --end 2025-12-31 --tag 20260513_v1c_2025e`
   - challenger：`python3 v6b_synthetic_historical_challenger.py --manifest v6_strategy_lab/configs/synthetic_history/20260513_v1c_2025e/manifest.json --start 2018-01-01 --end 2025-12-31 --tag 20260513_v1c_2025e`
   - 结果摘要：
     - `V6-A baseline` 仍最强：`AnnR +26.2% / MaxDD -26.1% / Sharpe 0.88`
     - `V6-B core_track` 最好也只有：`AnnR +19.4% / MaxDD -39.6% / Sharpe 0.57`
     - `V6-B bottleneck_track`：`AnnR +16.2% / MaxDD -42.1% / Sharpe 0.49`
     - `V6-B blended_tracks` 最差：`AnnR +10.5% / MaxDD -38.8% / Sharpe 0.32`
   - 当前解释：
     - `V6-B` 的历史候选池重建链路已经打通
     - 但在当前 engine 下，`V6-B` 仍未证明应获得 allocator 权重
     - 下一步必须分轨做独立 engine 设计，不应继续优先研究 mixed pool

10. `2026-05-13 V6 engine profiles / core governance` 口径已补充
   - `V6-A` 不应理解为“永远不变的池子”，而应理解为 `低频维护的核心池`
   - 允许调整的原因只包括：`结构性失效`、`长期领导权转移`、`治理/可交易性变化`
   - `V6-B` 不应变成“一主题一策略”的集合；正确落地方向是 `动态资源池 + track-aware execution profiles`
   - profile policy：`v6_strategy_lab/configs/v6_engine_profile_selector_v1.json`
   - 治理说明：`v6_strategy_lab/reports/2026-05-13_v6_engine_profiles_and_core_pool_governance_v1.md`

11. `2026-05-13 profile attribution 校正` 已补做
   - 新增 same-parameter control：`overlay` 不再只和当前 baseline 比，还必须和 `同参数 V6-A base-only` 对照。
   - 原因：否则会把 `参数优化` 误判成 `V6-B 真正贡献`。
   - 结果：
     - `core_reaccel overlay` 通过 attribution 检验，最佳组合约为 `mom60 / top2 / trend120 / rebal10`，相对 same-parameter base-only 仍有 `Ann +5.3% / Sharpe +0.08 / MaxDD 改善 1.7%` 的真实增量，属于第一条有资格继续推进的 V6-B challenger。
     - `turnaround overlay` 有小幅真实增量，但轨道过 sparse（`23/96` 历史快照非空，平均 `0.24` 只/快照），只能作为低优先级 secondary challenger。
     - `bottleneck overlay` 未通过 attribution 检验：看似比 baseline 强，但相对 same-parameter base-only 仅 `Ann +0.4%`，同时 `Sharpe -0.13`、`MaxDD 恶化 6.5%`，说明当前收益主要来自参数变化，不是 bottleneck 轨道本身。
   - 战略含义：
     - `V6-B` 当前不是“多条轨都能直接带来提升”，而是 `只有少数轨道在同参数对照下仍能证明真实增量`。
     - 下一步优先级应调整为：`core_reaccel formal challenger > turnaround secondary research > bottleneck freeze`。
   - 另外需要单独开 `V6-A parameter challenger`，因为同参数对照显示，一部分 uplift 其实来自 base-only 的 engine profile 变化。
   - 归因报告：`v6_strategy_lab/reports/2026-05-13_v6b_profile_search_attribution_v1.md`

12. `2026-05-13 V6 review mechanism v1` 已固定
   - 结论：V6 应该有正式复盘机制，但不应照搬高频团队的日内密集复盘。
   - 正确节奏：
     - `Daily Ops Review`：抓执行 / 运维异常，不做策略判断
     - `Weekly System Review`：作为主复盘单位
     - `Monthly Research Review`：把现象转成 challenger / freeze / promote 队列
     - `Quarterly Governance Review`：决定 baseline 是否维持 / 升级 / 降权 / 暂停
   - 当前最该正式补上的工件是：`Weekly V6 Review Board`
   - 说明文档：`v6_strategy_lab/reports/2026-05-13_v6_review_mechanism_v1.md`

13. `2026-05-13 V6-A parameter challenger v1` 已启动
   - 假设：`v6_strategy_lab/hypotheses/H007_v6a_parameter_challenger.md`
   - 配置：`v6_strategy_lab/configs/v6a_parameter_challenger_v1.json`
   - 脚本：`python3 v6a_parameter_challenger.py --manifest v6_strategy_lab/configs/synthetic_history/20260513_v1c_2025e/manifest.json --start 2018-01-01 --end 2025-12-31 --tag 20260513_v1`
   - 首轮结果：
     - 当前 baseline `mom60 top3 trend100 mkt150 rebal5` 并非明显最优 anchor
     - `mom120 top2 trend150 mkt200 rebal10` 给出最强 raw challenger：`AnnR +37.5% / MaxDD -26.3% / Sharpe 1.09`
     - `mom60 top3 trend150 mkt200 rebal10` 给出更平衡的 core-upgrade 读数：`AnnR +34.0% / MaxDD -22.3% / Sharpe 1.11 / OOS Sharpe 1.52`
   - 当前解释：
     - `V6-A` 本身存在真实参数升级空间
     - 这意味着后续收益增强不一定只能来自 `V6-B`
     - 但当前仍不能直接切生产 baseline，必须先补 `turnover/cost re-audit`、`parameter neighbor robustness`、`formal side-by-side review board`
   - 首轮解读报告：`v6_strategy_lab/reports/2026-05-13_v6a_parameter_challenger_first_read_v1.md`

14. `2026-05-13 Weekly Review -> Research Backlog` 闭环已落地
   - 周复盘脚本：`python3 v6_weekly_review_board.py --tag <tag>`
   - 输出：
     - `backtest_results/v6_weekly_review/`
     - `backtest_results/v6_research_backlog/`
   - 作用：
     - 把 `latest daily/weekly report`、`pilot review`、`preflight gate`、`V6-A challenger`、`V6-B track search` 收敛成一张 `Weekly Review Board`
     - 再把结果映射成 rule-based `research backlog`
   - 关键原则：
     - 复盘结果反哺的是 `研究队列`，不是直接改生产系统
     - 这样 V6 才是 `有治理的自进化`，不是 `情绪驱动的乱调参`

15. `2026-05-13 V6-A balanced challenger` 首个稳健性检查已完成
   - 脚本：`python3 v6a_parameter_neighbor_robustness.py --label 'mom60 top3 trend150 mkt200 dd10 rebal10' --tag 20260513_balanced_v1`
   - 结果：`stable_neighbor_cluster`
   - 读数：
     - 邻域样本 `11`
     - `11 / 11` 都属于 `promising_core_upgrade` 或 `full_sample_upgrade`
     - 邻域中位数：`AnnΔ +7.6% / SharpeΔ +0.21 / MaxDD 改善 3.7%`
   - 当前解释：
     - `mom60 top3 trend150 mkt200 rebal10` 不是孤立尖峰
     - 它比 raw-best 的 `top2` 候选更符合当前 `V6 = relatively safer annual return enhancer` 的定位
   - 阶段结论：
     - `balanced V6-A challenger` 应进入正式 follow-up
     - 下一步优先做 `turnover/cost re-audit` 和 `baseline vs challenger side-by-side board`
   - 汇总报告：`v6_strategy_lab/reports/2026-05-13_v6_weekly_review_and_v6a_robustness_v1.md`

16. `2026-05-13 balanced challenger turnover/cost re-audit` 已完成
   - 脚本：`python3 v6a_challenger_turnover_cost_reaudit.py --candidate-label 'mom60 top3 trend150 mkt200 dd10 rebal10' --tag 20260513_balanced_v2`
   - 结论：`candidate_survives_costs`
   - 关键读数：
     - baseline `25bps`：`Ann +23.5% / OOS Sharpe 1.20 / annual turnover 8.88`
     - candidate `25bps`：`Ann +32.4% / OOS Sharpe 1.47 / annual turnover 5.00`
   - 当前解释：
     - `balanced challenger` 不只是无摩擦下更优
     - 它在成本后仍明显优于 baseline，且换手更低、再平衡频率更低
   - 报告：`backtest_results/v6a_challenger_turnover_cost_reaudit/v6a_challenger_turnover_cost_reaudit_20260513_balanced_v2.md`

17. `2026-05-13 baseline vs balanced challenger review board` 已补做
   - 当前结论：`balanced challenger wins the pre-production research board`
   - 但不立刻替换 live baseline；应先进入 `implementation / replay / preview` 队列
   - 原因：
     - 当前证据仍来自 research engine
     - live sleeve 仍处于 manual pilot
     - 不能把执行验证和 baseline 替换混成一步
   - 当前 V6-A 优先级修正为：
     - `execution-quality evidence`
     - `balanced challenger implementation / replay / preview`
     - `baseline promotion discussion`
   - 评审板：`v6_strategy_lab/reports/2026-05-13_v6a_baseline_vs_balanced_review_board_v1.md`

18. `2026-05-13 V6-A core replay bridge` 已落地
   - 脚本：`python3 v6a_core_deterministic_replay.py --config v6_strategy_lab/configs/v6a_core_replay_bridge_v1.json --tag 20260513_bridge_v1`
   - 新工件：
     - `v6a_core_deterministic_replay.py`
     - `v6_strategy_lab/configs/v6a_core_replay_bridge_v1.json`
     - `backtest_results/v6a_core_replay/v6a_core_replay_manifest_20260513_bridge_v1.json`
     - `v6_strategy_lab/reports/2026-05-13_v6a_core_replay_bridge_board_v1.md`
   - 关键结论：
     - `balanced challenger` 在 replay bridge 中仍领先：`Full Ann +34.0% / MaxDD -22.3% / Sharpe 1.11 / OOS Ann +44.2% / OOS Sharpe 1.30`
     - baseline 为：`Full Ann +26.2% / MaxDD -26.1% / Sharpe 0.88 / OOS Ann +36.8% / OOS Sharpe 1.13`
     - 换手 / 再平衡继续改善：`5.25x / 25.2次年` 对比 baseline `9.01x / 50.4次年`
   - release-style 读数：
     - `balanced challenger` 通过当前数值 gate，且 `rolling_3y_worst_ann = +0.78%`
     - baseline 仍卡在 `rolling_3y_worst_ann = -4.73%`
     - 两者当前都不能宣称 preview-ready，因为 bridge 最新 replay row 仅到 `2026-05-05`，`signal freshness` 仍需补
   - 当前解释：
     - 这一步确认 `balanced challenger > current V6-B` 是近端 production-path 优先级上的正确判断
     - 也确认 `ATTACK_EQUAL_REPLAY live pilot` 与 `V6-A core baseline/challenger` 不是同一条线，后续必须分轨治理
   - 下一步：
     - `execution-quality evidence` 继续按原 ATTACK live sleeve 跑到 `2026-05-26`
     - `balanced challenger` 进入 `single-candidate runner wiring / dry-run preview` 队列

19. `2026-05-13 V6-A balanced challenger cutover SOP` 已固定
   - 文档：`v6_strategy_lab/reports/2026-05-13_v6a_balanced_challenger_cutover_sop_v1.md`
   - 最早决策日：`2026-05-26`
   - 关键定义：
     - `2026-05-26` 是 `cutover decision day`，不是默认切换日
     - 允许输出只有三种：`GO_CUTOVER`、`HOLD_OLD_BASELINE`、`PAUSE_V6`
   - 当前原则：
     - 旧 `ATTACK_EQUAL_REPLAY` pilot 通过，是必要条件，但不是充分条件
     - `balanced challenger` 还必须同时通过 `fresh replay + single-candidate preview + migration diff clarity`
   - 这份 SOP 的作用：
     - 到期时不靠主观感觉拍板
     - 把评估、切换、切后观察和 rollback 条件写死

20. `2026-05-14 V6-A balanced challenger cutover prep` 已推进到 preview/migration 层
   - fresh replay 重跑：
     - 脚本：`python3 v6a_core_deterministic_replay.py --config v6_strategy_lab/configs/v6a_core_replay_bridge_v1.json --tag 20260514_bridge_refresh_v1`
     - 结果：数值结论保持不变，但 `latest_date` 仍停在 `2026-05-05`
     - 含义：`balanced challenger` 的核心 research 优势仍在，但 `signal freshness` blocker 依旧存在，当前还不能通过 cutover gate
   - 新增 preview policy：
     - `v6_strategy_lab/configs/v6a_balanced_challenger_guarded_runner_policy_v1.json`
     - 作用：把 `balanced challenger` 单候选 replay artifacts 接进 guarded-runner 生产链路，用于 cutover 预演，不碰当前 live ATTACK sleeve
   - 新增 migration diff 工具：
     - 脚本：`python3 v6a_cutover_migration_diff.py --tag 20260514_balanced_cutover_v2`
     - 产物：`backtest_results/v6a_cutover/v6a_cutover_migration_diff_20260514_balanced_cutover_v2.md`
   - 当前 snapshot-fallback diff：
     - `ownership_transfer + buy`：`AMZN 4 -> 6`、`AVGO 2 -> 3`
     - `buy only`：`NVDA 0 -> 7`
     - `sell only`：`BIL 6 -> 0`、`GLD 1 -> 0`、`GOOGL 2 -> 0`
   - 当前 blocker 解释：
     - `preview wiring` 已打通，但今天直接打 OpenD 的 `quote/account` 路径不稳定，guarded-runner 仍可能因 timeout 阻断
     - 就算 timeout 消失，`freshness gate` 仍会因为 `signal_date=2026-05-05` 卡住
   - 下一步：
     - 先解决 `2026-05-05 -> 当前日` 的 replay freshness
     - 再补一轮成功的 `balanced challenger` live preview（quotes/account/orders 全 PASS）
     - 最后在 `2026-05-26` 决策日按 SOP 汇总 `live pilot + fresh replay + preview + migration diff`

21. `2026-05-14 V6-A balanced challenger` 的 freshness / preview / release gate 证据已补齐
   - `price cache` 已通过 OpenD 刷新到 `2026-05-13`
   - `fresh replay`：
     - 脚本：`python3 v6a_core_deterministic_replay.py --config v6_strategy_lab/configs/v6a_core_replay_bridge_v1.json --tag 20260514_bridge_refresh_v3`
     - 最新工件：`backtest_results/v6a_core_replay/v6a_core_replay_summary_20260514_bridge_refresh_v3_v6a_core_balanced.csv`
     - 当前解释：`latest_date = 2026-05-12` 不再代表缓存陈旧，而是由 replay config 中的 `sample.end=2026-05-12` 决定
   - `single-candidate live preview`：
     - 脚本：`/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 attack_engine_live_order_preview.py --daily backtest_results/v6a_core_replay/v6a_core_replay_daily_20260514_bridge_refresh_v3_v6a_core_balanced.csv --strategy-capital 5000 --max-gross 1.0 --max-order-value 5000 --min-order-value 25 --net-managed-positions --managed-positions-state backtest_results/v6a_state/v6a_managed_positions_real_281756481449956811.json --acc-id 281756481449956811 --trd-env REAL --quote-timeout-sec 25 --account-timeout-sec 25 --tag 20260514_balanced_cutover_preview_v3`
     - 结果：`quotes/account/orders` 全部成功，无 warnings
     - 当前 target：`AMZN / AVGO / GOOGL`
     - 当前增量 buy：`AMZN +2`、`AVGO +1`、`GOOGL +2`
   - `release gate`：
     - 结果：`PASS`
     - 关键通过项：
       - `signal_freshness_gate`: `signal_date=2026-05-12` 对 `asof=2026-05-14` 仅 `2` 天
       - `live_quotes_complete_gate`: `3/3` 通过
       - `live_account_gate`: 通过
       - `order_value_gate`: 通过
     - 工件：`backtest_results/attack_engine_release_gate/attack_engine_release_gate_20260514_balanced_cutover_gate_v1.md`
   - 当前含义：
     - `balanced challenger` 的技术性 cutover blocker 已基本收口
     - 现在剩下的是 `治理时点`，不是 `工程接线`
     - 当前 live `ATTACK_EQUAL_REPLAY` sleeve 仍保持不动，正式 go/no-go 继续等 `2026-05-26`
   - 汇总报告：`v6_strategy_lab/reports/2026-05-14_v6a_balanced_cutover_gate_status_v1.md`

22. `2026-05-14` 已新增 `2026-05-26` 决策日一页执行卡
   - 文档：`v6_strategy_lab/reports/2026-05-14_v6a_balanced_cutover_decision_day_card_v1.md`
   - 作用：
     - 把长版 cutover SOP 压缩成当天可直接执行的一页卡
     - 锁定用户触发语、允许 verdict、evidence pack、决策顺序、执行边界
   - 当前规则：
     - 到 `2026-05-26` 当天，用户只需发：`执行 V6-A balanced challenger cutover SOP`
     - 系统只允许输出：`GO_CUTOVER / HOLD_OLD_BASELINE / PAUSE_V6`
     - 即便 `GO_CUTOVER`，真实下单前仍需单独确认：`GO_BALANCED_CUTOVER_EXECUTE`

今天不能做的事：

- 不能消耗 Futu 历史 K 线额度继续拉全量数据。
- 不能宣称 V6-B 有收益贡献。
- 不能把 Radar 当前种子池直接放进历史回测并使用 2012-2026 全周期表现，因为这会形成未来函数。
- 不能把当前 scorecard 当作交易清单，因为价格动量、流动性和拥挤度还没有接入最新真实数据。
- 不能把 `generated_seed_probe` 中的 V6-A baseline 结果当作 V6-B 结果；它只是证明脚本链路和缺数据报告正常。
- 不能用当前 live Radar 池直接做历史回测；历史回测必须走 synthetic Radar generator。

## 目录结构

```text
v6_strategy_lab/
  README.md
  configs/
  hypotheses/
  reports/
  scorecards/
```

## 工作节奏

### 每日

- 检查订单、仓位、OpenD、reconciliation 状态
- 不做策略层判断，除非触发异常

### 每周

- 复盘 V6-A 本周表现
- 检查理论仓位 vs 实际仓位
- 检查是否出现未成交、部分成交、异常偏离
- 判断是否继续模拟、暂停、或准备小额 pilot

### 每月

- 提出 3-5 个 challenger 假设
- 至少完成 1 个可回测 challenger
- 对比 V6-A 与 challenger 的 OOS、回撤、Sharpe、黑天鹅窗口

### 每季度

- 完整 revalidation：
  - deterministic replay
  - release gate
  - robustness / parameter neighbor
  - black swan windows
  - rolling 3y/5y
  - live tradability
- 决定是否维持、降权、暂停或替换 V6-A

## Challenger 提升规则

Challenger 不能因为某个单点指标好看就替代 V6-A。至少要满足：

1. OOS Sharpe 不低于 V6-A
2. Full/OOS MaxDD 不明显恶化
3. Rolling 3y worst ann 不低于 V6-A，或有明确风险收益补偿
4. 黑天鹅窗口不比 V6-A 明显差
5. 最近两年表现不能靠单一月份贡献
6. 参数邻域稳定
7. 可交易性不差于 V6-A
8. 若相关性很高，必须明显优于 V6-A；若相关性较低，可作为组合增强候选

## 降权 / 暂停规则

V6-A 出现以下情况时，进入降权或暂停讨论：

- 实盘/模拟盘回撤超过历史正常区间
- 连续多次信号切换失效
- 理论信号和实际成交长期偏离
- 滑点、成交、最小下单单位导致真实结果明显差于 preview
- rolling 3y / rolling 5y 最新重算明显恶化
- 防守资产失效，风险关闭时仍出现异常亏损

## 当前第一批假设

详见：

- `v6_strategy_lab/hypotheses/H001_ai_momentum_decay.md`
- `v6_strategy_lab/hypotheses/H002_defensive_pool_optimization.md`
- `v6_strategy_lab/hypotheses/H003_non_ai_momentum_expansion.md`
- `v6_strategy_lab/hypotheses/H004_regime_filter_tightening.md`
- `v6_strategy_lab/hypotheses/H005_equal_vs_inverse_vol_weighting.md`
- `v6_strategy_lab/hypotheses/H006_radar_momentum_challenger.md`

## 当前边界

- Strategy Lab 不直接改 V6-A 生产逻辑。
- Strategy Lab 不直接下单。
- 所有 challenger 都必须先 research，再 replay，再 preview，再 sim。
- 任何替换主策略的决定必须有报告证据。

## 当前治理工件

以下工件是当前 V6 进入“可治理状态”的正式证据层：

| 工件 | 作用 | 当前结论 |
| --- | --- | --- |
| `v6_strategy_lab/reports/2026-05-13_v6a_execution_quality_board.md` | 统一 V6-A pilot 执行质量看板 | 当前继续 manual pilot |
| `v6_strategy_lab/reports/2026-05-13_v6b_supply_chain_diffusion_map_v1.md` | 固化 V6-B 当前训练主题与扩散地图 | AI-capex 作为第一代训练主题 |
| `v6_strategy_lab/reports/2026-05-13_v6_allocator_governance_spec_v1.md` | 固化 Allocator 的职责、边界和晋级口径 | 当前 V6-B 仍是 0% 权重 |

## 当前实现规格

以下规格由 GPT 负责定义，由 Claude 负责实现。它们不改变 V6-A engine，不授权自动实盘交易，只为 pilot 复盘和自动化前置评估提供证据。

| 规格 | 目的 | 状态 |
| --- | --- | --- |
| `v6_strategy_lab/specs/2026-05-12_v6a_turnover_cost_audit_spec.md` | 测算 V6-A 历史换手率、交易成本敏感性、小账户可行性 | 已实现并出报告 |
| `v6_strategy_lab/specs/2026-05-12_v6a_pilot_review_dashboard_spec.md` | 为 2026-05-26 两周 pilot 复盘建立证据看板 | 已实现并出报告 |
| `v6_strategy_lab/specs/2026-05-12_v6_automation_preflight_gate_spec.md` | 把 OpenD 宕机、未成交、资金不足、滑点超标、kill switch 做成自动化前置 gate | 已实现并出报告 |

实现顺序：

1. `turnover_cost_audit`
2. `pilot_review_dashboard`
3. `automation_preflight_gate`

验收口径：

- 先出报告，再讨论是否进入小额自动化。
- 自动化 gate 实现完成前，不开启无人值守真实交易。
- 所有实现结果必须通过 `AI_COLLAB_EXPORT_FOR_GPT.md` 回传给 GPT review。
