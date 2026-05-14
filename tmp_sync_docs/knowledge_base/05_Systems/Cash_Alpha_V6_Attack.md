# Cash Alpha V6 Attack

- Summary: V6 高进攻动量策略线的系统卡，记录 V6-A baseline、V6-B Dynamic Universe、Allocator、回测表现、放行纪律与后续维护方式。
- Status: active
- Tags: system, automation, v6, attack-engine, momentum
- Created: 2026-05-06
- Last Updated: 2026-05-14
- Related Notes: `系统映射索引.md`, `治理与报告层.md`, `Cash_Alpha_V3.md`, `../00_System/自动化边界与放行纪律.md`, `../06_Execution/V6模拟盘运行记录.md`
- Source Files: `../../投资系统全景图_SYSTEM_OVERVIEW.html`, `/Users/zhangkun/WorkBuddy/程序化/量化程序/attack_engine_deterministic_replay.py`, `/Users/zhangkun/WorkBuddy/程序化/量化程序/attack_engine_sim_executor.py`, `/Users/zhangkun/WorkBuddy/程序化/量化程序/v6_weekly_review_board.py`, `/Users/zhangkun/WorkBuddy/程序化/量化程序/central_risk_board.py`, `/Users/zhangkun/WorkBuddy/程序化/量化程序/performance_attribution.py`, `/Users/zhangkun/WorkBuddy/程序化/量化程序/monthly_research_review.py`

## 一句话结论

Cash Alpha V6 是高进攻动量策略线。当前 V6-A 已进入 `$5,000` 小额实盘 pilot ready 状态，但尚未下单，必须由用户在美股 RTH 后人工确认；V6-B 是 Dynamic Universe 生成与验证机制，当前仅 SIM / research，不直接上线。

## 策略定位

- V6-A 当前主候选：`ATTACK_EQUAL_REPLAY`
- V6-A 组合方式：6 个 robust ATK 子策略等权组合
- V6-B 研发方向：Dynamic Universe Sleeve / Universe Refresh Engine，Radar 是其研究输入之一
- 核心风格：AI / mega cap / 科技动量进攻 + 防守资产切换
- 当前用途：V6-A 用小额 pilot 验证真实成交和监控；V6-B 验证动态候选池是否能成为 V6 Universe 的持续更新来源
- 未来可能用途：规模更大后，与价值投资主账户、V3 现金增强线形成分层组合

## 长期研发架构

```text
V6 Engine = 固定底层规则：经典动量 / 相对强弱 / risk-on risk-off / 波动率控制 / 回撤刹车
V6 Universe = 总候选池：V6-A Core Pool + V6-B Dynamic Pool + Defensive Pool
V6-A Core Pool = 低频更新的 AI mega / mega tech 核心池，当前 baseline
V6-B Dynamic Pool = 动态候选池生成与验证机制，目标是成为 V6 Universe Refresh Engine
V6-C Pool = ETF / 行业 / 全市场 meta-rotation，未来 challenger
Allocator = 风控与资金分配器，根据近期表现、相关性、回撤、regime 分配 Core / Dynamic / Defensive 权重
```

研发顺序：

1. V6-B 单独回测，只验证 Radar 池能不能赚钱。
2. V6-A vs V6-B 对比，看收益、回撤、Sharpe、相关性、换手和可交易性。
3. V6-A + V6-B 组合测试，例如 70/30、50/50、动态权重。
4. 若 V6-B 稳定贡献，再升级为 V6 资源池优化层。

关键纪律：Engine Core 慢变，Universe 可以更快更新；V6-B 不是整个 V6 Universe，而是动态候选池来源层。Radar 是 `Research Input`，不是前台持仓层；任何 V6-B universe 都必须 point-in-time，不能用未来才发现的标的回填历史。

## 当前核心表现口径

基于 2026-05-06 最新 replay：

- Full ann：约 `29.80%`
- OOS ann：约 `36.43%`
- Full max DD：约 `-21.13%`
- OOS Sharpe：约 `1.18`
- min equity：约 `94.41%`
- rolling 3y worst ann：约 `7.20%`

逐年特征：强年份很强，弱年份会明显承压；它不是低波稳健策略，而是受控高进攻策略。

## 黑天鹅压力表现

- 2018 Q4：区间约 `-11.47%`，最大回撤约 `-14.61%`
- 2020 Covid：区间约 `-7.12%`，最大回撤约 `-16.37%`
- 2022 加息熊市：全年约 `-9.78%`，最大回撤约 `-13.81%`
- 2026 YTD：截至 2026-05-05 约 `-6.41%`，最大回撤约 `-14.12%`

解读：V6 在黑天鹅中不是免跌，而是通过防守切换避免灾难性亏损。

## 当前运行状态

- V6-A：`REAL_PILOT_READY_MANUAL_CONFIRM`
- 实盘状态：尚未下单；需要美股 RTH 后重新 preview / release gate / 用户人工确认
- V6-B：`SIM_ONLY / RESEARCH_ONLY`
- 模拟账户：`19005590`
- 初始 V6-A 策略资本：`$5,000`
- 单笔订单上限：`$5,000`
- 不使用 margin
- 只用整股

V6-A 当前 `$5,000` pilot preview 订单为：

- AMZN：目标 `4` 股
- AVGO：目标 `2` 股
- BIL：目标 `6` 股
- GLD：目标 `1` 股
- GOOGL：目标 `2` 股

## 放行纪律

V6 当前只能做：

- replay
- release gate
- live preview
- simulate execution
- 成交核验
- 运行报告
- 小额真实 pilot，前提是用户明确确认

V6 当前不能做：

- 自动切到真实账户或自动扩容
- 与 V3 叠加在同一个模拟仓位中混跑
- 用真实账户长线持仓做 netting
- 在未完成 1-2 周模拟验证前开启自动定时实盘
- 因回测高收益而跳过成交、滑点、下单单位、OpenD 稳定性验证
- 把 V6-B 未验证的 Radar 动态池直接并入 V6-A
- 用非 point-in-time 的候选池做历史回测
- 因为某个 Radar 标的暴涨，就跳过 standalone / 对比 / 组合测试

## 调整治理

| 组件 | 调整频率 | 自动化程度 | 规则 |
| --- | --- | --- | --- |
| `V6 Engine Core` | 半年或重大 regime 变化 | 不自动调整 | 只允许 challenger 报告晋级 |
| `V6 Engine Parameters` | 季度复核 | 半自动研究，人工确认 | 测试动量窗口、趋势窗口、再平衡频率、回撤阈值、top N |
| `V6-A Core Pool` | 季度/半年低频复核 | 半自动扫描，人工确认 | 类似指数成分股维护，mega 也会变，但不能月度追热点替换 |
| `V6-B Dynamic Pool` | 周度观察，月度正式更新 | 半自动生成候选，人工确认入池 | Radar、漏网复盘、主题扩散、预期上修和动量确认生成 point-in-time universe |
| `Allocator` | 周/月复核 | 先规则化，后续可半自动 | 风控层决定 Core / Dynamic / Defensive 权重 |

## 邮件报告要求

V6 需要定期邮件摘要，但邮件只做状态与提醒，不自动触发实盘交易。

- 每周：V6-A 信号、实际持仓、偏离、回撤、异常订单；V6-B live-forward；Allocator 建议权重。
- 每月：Dynamic Pool 是否需要更新；Missing Opportunity Review；是否需要用户发起复盘。
- 每季度：Engine / Core Pool / Allocator revalidation 提醒。

邮件结论必须明确写成：`本周动作：不动 / 需要用户确认 / 禁止实盘`。

## V6 复盘机制

V6 的复盘不是高频团队那种“每天复盘大量交易细节”，而是按系统频率做四层治理：

| 层级 | 频率 | 核心问题 | 当前自动化程度 |
| --- | --- | --- | --- |
| `Daily Ops Review` | 每个交易日 | 系统有没有坏，执行链条有没有异常 | 高 |
| `Weekly System Review` | 每周一次 | 这一周的收益、回撤、暴露和执行是否来自预期逻辑 | 中高 |
| `Monthly Research Review` | 每月一次 | 哪些现象值得变成 challenger / universe / allocator 研究 | 中 |
| `Quarterly Governance Review` | 每季度一次 | 主系统是否维持、降权、暂停或升级 | 低，必须人工决策 |

当前最关键的主复盘单元是 `Weekly V6 Review Board`。它会把下面这些证据链拉到一张板上：

- `v6_reporting`
- `v6a_pilot_review`
- `v6_automation_preflight`
- `v6a_parameter_challenger`
- `v6a_parameter_robustness`
- `v6a_challenger_turnover_cost_reaudit`
- `v6b_profile_search`

这张周度板的作用，不是自动改生产参数，而是把运行现象转成结构化结论：

- `No change`
- `Investigate / Continue manual pilot`
- `Research follow-up`
- `Risk discussion`

然后自动落成 `V6 Research Backlog`，把下周/下月最该研究的事项按优先级排出来。

## 当前治理交付物

V6 现在不再只靠单份周报判断状态，而是接入了更完整的治理证据链：

- `Central Risk Board v1.2`：把 V6 暴露并入总账户分母，统一看 concentration、theme overlap 和 event window。
- `Performance Attribution v1`：把 V6 与主仓、Overlay、实验线拆开，避免主仓盈亏掩盖 V6 执行质量。
- `Overlay Trade Journal`：把 Radar-Sourced Overlay 独立记账，不让右尾实验污染 V6 样本。
- `Monthly Research Review v1`：把 V6-A manual pilot、V6-B 供给链、missing opportunity review 统一转成 backlog。
- `V6B_2026-06-01_EXECUTION_CARD.md`：把 6 月 1 日该跑的 universe / challenger / allocator 顺序提前写死。

一句话说，这一层的目标不是“多报表”，而是让 V6 的扩容、cutover 和 V6-B 晋级都有可追溯证据。

## 自动化边界与用户职责

这套机制是 `部分自动化`，不是“全自动自我进化”。

已经自动化的部分：

- 日常运行证据：`morning_brief`、`v6_reporting`、`reconciliation`、`preflight`
- 周度治理产物：`v6_weekly_review_board.py` 自动生成 `Weekly V6 Review Board` 和 `V6 Research Backlog`
- 研究信号汇总：自动读取最新 V6-A challenger、robustness、cost re-audit、V6-B track profile 结果

仍然不能自动做的部分：

- 自动切换真实账户或扩大 V6-A 真金白银规模
- 自动把某个 challenger 升格为新 baseline
- 自动给 `V6-B Dynamic Pool` allocator 权重
- 自动修改 engine 参数、风险边界或治理纪律

你真正需要做的，不是每天盯盈亏，而是做这四件事：

1. 每周看一次 `Weekly V6 Review Board` 的 verdict 和 `V6 Research Backlog`
2. 对 `P0 / P1` 级事项决定是继续观察，还是发起正式 challenger / 调查
3. 在月度/季度节点参与重大治理决策，例如 baseline 替换、V6-B 晋级、风险降档
4. 任何真实账户动作继续人工确认，尤其是 pilot 下单、扩容和 cutover

## 与 V3 的关系

- V3：现金增强 / 低波辅助线，目标是执行稳定和回撤较低。
- V6：高进攻动量线，目标是提高组合收益上限。
- 现在：模拟盘从 V3 切到 V6，先单独验证 V6。
- 未来：规模更大后，可以考虑 `价值投资主账户 + V6-A/V6-B进攻主仓 + V3现金增强/备用线` 的分层结构。

## 维护方式

V6 不是一次性策略。后续要像量化基金一样维护：

1. 定期 replay 最新数据
2. 每次换仓前过 release gate
3. 每周运行 `v6_weekly_review_board.py`，把最新运行证据转成 `Weekly V6 Review Board` 和 `V6 Research Backlog`
4. 每月复盘逐年/滚动/黑天鹅表现是否漂移，并更新研究优先级
5. 持续研究新动量来源，但新因子必须和现有 ATK 候选平行测试
6. 任何替换都要证明 OOS、回撤、Sharpe、成交可行性不劣于当前主线
7. V6-B 必须独立记录入池日期、出池日期、source、track、入池理由和反证条件
8. 每次治理规则调整必须同步到 `V6_STRATEGY_LAB.md`、本系统卡、Overview 和必要的执行文件

## 关键本地文件

```text
/Users/zhangkun/WorkBuddy/程序化/量化程序/attack_engine_deterministic_replay.py
/Users/zhangkun/WorkBuddy/程序化/量化程序/attack_engine_release_gate.py
/Users/zhangkun/WorkBuddy/程序化/量化程序/attack_engine_live_order_preview.py
/Users/zhangkun/WorkBuddy/程序化/量化程序/attack_engine_sim_executor.py
/Users/zhangkun/WorkBuddy/程序化/量化程序/attack_engine_real_pilot_executor.py
/Users/zhangkun/WorkBuddy/程序化/量化程序/v6_live_launch_policy.json
/Users/zhangkun/WorkBuddy/程序化/量化程序/V6_STRATEGY_LAB.md
/Users/zhangkun/WorkBuddy/程序化/量化程序/v6b_live_forward_sim_executor.py
/Users/zhangkun/WorkBuddy/程序化/量化程序/v6b_radar_momentum_challenger.py
/Users/zhangkun/WorkBuddy/程序化/量化程序/v6_strategy_lab/reports/2026-05-10_v6_long_term_research_roadmap.md
/Users/zhangkun/WorkBuddy/程序化/量化程序/backtest_results/attack_engine_replay/
/Users/zhangkun/WorkBuddy/程序化/量化程序/backtest_results/attack_engine_sim_executor/
```

## 当前待补

- 美股 RTH 后重新拉 V6-A final preview，等待用户人工确认是否执行 `$5,000` pilot
- 生成 V6 每日/每周邮件报告入口
- V6-B live-forward SIM 开始后，记录候选池、模拟订单、表现和偏离
- 若未来进入自动化，必须重新写 live 放行记录和 LaunchAgent 边界
- 等 Futu 历史 K 线额度刷新后，补齐 V6-B 数据并运行 standalone 回测
- 建立 V6-B point-in-time universe，避免未来函数
