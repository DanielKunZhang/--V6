# 美股 Radar：宏观对冲基金思路 Skill 化框架

日期：2026-05-19  
目标：把有长期结果的宏观 / 对冲基金思维，转化为美股 Radar 可执行维度，服务“相对安全地快速增长资本”，而不是追星、抄作业或炫技。

## 一页结论

美股 Radar 可以吸收优秀宏观对冲基金的思路，但必须把它们翻译成系统语言：

- 不学“他们买了什么”，学“他们如何定义机会、拥挤、催化、风险和退出”。
- 不把 13F 当买入清单，只当延迟披露的机构行为样本。
- 不把宏观判断变成主观大仓冲动，而是变成 Radar 的加分、降级、等待和风控条件。

最终输出应是一个 Radar skill 库：每个 skill 都能回答一个具体问题，并影响候选池排序或执行动作。

## 可提炼的 7 个 Radar Skills

| Skill | 学习对象 / 思维来源 | Radar 作用 | 输出 |
|---|---|---|---|
| `macro_regime_skill` | 全球宏观基金：利率、美元、流动性、通胀、财政周期 | 判断当前市场是否适合高 beta / 长久期 / AI CapEx 扩张交易 | `risk_on / neutral / risk_off` |
| `reflexivity_skill` | Soros / Druckenmiller 式反身性 | 判断价格上涨是否在强化基本面、融资能力、客户信心和资本开支 | `positive_reflexivity / fragile_reflexivity / no_reflexivity` |
| `concentration_conviction_skill` | 高胜率集中押注型基金 | 判断是否存在“少数真正值得重仓研究”的主线，而不是平均撒网 | `core_watch / secondary / discard` |
| `asymmetric_payoff_skill` | 期权 / 宏观事件交易思维 | 判断右尾是否足够大、左尾是否可控、是否适合小仓试错或期权表达 | `small_trial / wait / avoid` |
| `crowding_hedge_skill` | Situational Awareness 这类 long + put 结构 | 判断主题是否仍强但交易过拥挤，是否需要等待回调或降低权重 | `crowded_but_valid / crowded_avoid / clean_setup` |
| `catalyst_path_skill` | 事件驱动与宏观交易路径 | 判断未来 30/60/90 天是否有财报、订单、政策、融资、产品节点 | `near_catalyst / medium_catalyst / no_catalyst` |
| `invalidation_skill` | 顶级宏观基金的止损纪律 | 预先定义什么证据证明 thesis 错了，防止故事越讲越大 | `clear_stop / fuzzy_stop / no_stop_no_trade` |

## 对美股 Radar 的具体改造

### 1. 从“股票列表”升级为“机会结构评分”

旧 Radar 容易输出：这个票在 AI 主线里、涨得强、有人买。

新 Radar 必须输出：

- 它处在什么宏观 regime？
- 价格上涨是否强化了基本面，还是只强化了叙事？
- 它是主线核心、二阶扩散，还是三阶尾部？
- 机构是在裸多，还是 long 小票 + put 大票？
- 下一个催化是什么？
- thesis 错了的证据是什么？

### 2. 增加字段

建议在美股 Radar 样本表 / 候选表中新增这些字段：

| 字段 | 说明 |
|---|---|
| `macro_regime_fit` | 当前宏观环境是否支持这个交易 |
| `reflexivity_score` | 价格、融资、订单、客户信心是否互相增强 |
| `theme_concentration_rank` | 是否属于少数核心主线 |
| `institutional_validation` | 13F / 产业资本 / 高质量基金是否验证 |
| `institutional_hedge_signal` | 是否有 put / ETF hedge / 行业对冲信号 |
| `crowding_penalty` | 热度、估值、换手、机构拥挤度惩罚 |
| `catalyst_window` | 30/60/90 天内是否有可验证事件 |
| `invalidation_evidence` | 什么事实出现就降级或剔除 |
| `position_role` | `research / watch / pullback / small_trial / V6B_candidate / manual_attack_candidate` |

## 基金风格到 Radar 规则的翻译

| 风格 | 不该学什么 | 应该学什么 | Radar 规则 |
|---|---|---|---|
| Druckenmiller / Duquesne | 不追逐 13F 单票 | 大趋势 + 集中 + 快速承认错误 | 高分候选必须同时有主线、价格行为、催化和止损 |
| Soros / Quantum | 不做纯宏观豪赌 | 反身性：价格是否改变基本面 | 对融资依赖、平台型、新云、矿转算力票增加 reflexivity 检查 |
| Tudor Jones | 不做短线噪音交易 | 风险优先、亏损可控、趋势确认 | 没有止损点 / 失效证据的 Radar 票不准进入小仓 |
| Brevan Howard / Rokos / Caxton | 不把宏观观点硬套个股 | regime、流动性、利率、美元、波动率 | 高 beta AI 链条必须通过 macro_regime_fit |
| Situational Awareness | 不照抄 AI 小票 | 看懂 long + hedge 的结构 | 主题强但 put 对冲大时，输出“等回调 / 降权”，不是追高 |
| 多经理平台 | 不碎片化交易 | 每个 pod 有清晰风险预算和撤退线 | Radar 每个主题必须有预算上限、失效位和复盘样本 |

## 当前最适合先落地的 3 个 Skills

### 1. `crowding_hedge_skill`

优先级最高。原因：我们现在已经在 AI 基础设施、NVDA、V6-B、美股 Radar 上有明显相关暴露。这个 skill 可以防止“主线正确但买在拥挤顶端”。

输入：

- 13F long / call / put
- ETF put 或行业 put 信号
- 短期涨幅和相对强度
- 估值现实检查
- 同主题持仓集中度

输出：

- `clean_setup`：主线强、机构验证、拥挤度可接受
- `crowded_but_valid`：主线强，但只等回调或事件确认
- `crowded_avoid`：主线强但价格/拥挤度已经不适合新仓

### 2. `reflexivity_skill`

适合 AI data center、新云、矿转算力、电力、融资驱动型成长股。

核心问题：

- 股价上涨是否降低融资成本？
- 融资是否支持更快 capex？
- capex 是否已经有客户 / 订单 / 租约承接？
- 客户承接是否反过来证明估值？

如果中间断一环，降级为 `narrative_without_numbers`。

### 3. `catalyst_path_skill`

让 Radar 不只是“好公司 / 好故事”，而是知道什么时候验证。

输出必须写：

- 下一个 30 天验证点
- 下一个 60 天验证点
- 下一个 90 天验证点
- 若没有可验证催化，则只能进入研究池，不能进入小仓试错

## 使用纪律

1. 这些 skill 只服务 Radar，不直接产生大仓建议。
2. 任何基金持仓都不能单独触发买入。
3. 13F 至少滞后 45 天，主要用于结构研究和主题验证。
4. 只有当 Radar skill、估值现实检查、价格行为和仓位预算同时通过，才允许进入 `small_trial` 或 `V6B_candidate`。
5. 对主观进攻仓，Radar 只能提供候选和反证，不能覆盖 26 策略文件里的仓位纪律。

## 下一步落地顺序

1. 先把 `crowding_hedge_skill` 写进 Radar 评分规则。
2. 把 Situational Awareness 13F 作为第一批样本，回填 `SNDK / BE / CRWV / IREN / APLD / CORZ / MU / TSM / AVGO / AMD / NVDA`。
3. 6月1日历史 K 线额度恢复后，用这些字段跑一版美股 Radar / V6-B universe refresh。
4. 每周只复盘 5-10 个最高信息密度样本，不扩大成无边界研究。

## 资料来源

- SEC EDGAR 13F filings
- Caxton 官方简介：强调 global macro、严谨分析和风险管理
- Brevan Howard 官方简介：强调 macro thinking、trade structuring、risk management
- Situational Awareness LP 2026Q1 13F：用于 `crowding_hedge_skill` 第一批样本
