# V6-B Radar Weekly Triage SOP v1

- Date: `2026-05-14`
- Status: active
- Scope: 定义 `Missing Opportunity Review -> Candidate Registry -> Universe Refresh` 的每周人工决策流程。

## 一句话结论

Radar 现在已经能自动暴露三类问题：

- `critical miss`
- `coverage gap`
- `active-but-weak`

但这些输出不会自动改 universe。  
每周必须按统一 SOP 做人工 triage。

## 周度顺序

1. 运行 `v6b_missing_opportunity_review.py`
2. 运行 `v6_weekly_review_board.py`
3. 人工阅读：
   - `critical misses`
   - `coverage gaps`
   - `active-but-weak`
4. 对每个重点名字给出唯一 verdict
5. 只在 verdict 明确后，才允许改 `candidate registry` 或 `point-in-time universe`

## 四种标准 Verdict

### 1. `PROMOTE_TO_ACTIVE_RESEARCH`

适用条件：

- 名字已在 `candidate registry`
- 当前属于 `watch_add_candidate` 或 `observe_only`
- 本周 review 为 `critical miss`
- 数据可用，不再是 `coverage gap`
- 主题逻辑、反证条件、入池理由可以写清楚

动作：

- 更新 `candidate registry`
- 如确有必要，再更新 `point-in-time universe`
- 同步记录 source / reason / anti-thesis / entry_date

### 2. `KEEP_IN_REGISTRY`

适用条件：

- 名字确实主题相关
- 但证据还不够，或者只是短期价格冲动
- 或者数据刚补齐，仍需再观察 1-2 周

动作：

- 保持在 `watch_add_candidate` 或 `observe_only`
- 明确写出本周不晋级原因

### 3. `EXCLUDE_WITH_REASON`

适用条件：

- 本周很强，但不属于目标主题
- 或者只是情绪拉升，没有可复盘的主题传导逻辑
- 或者虽然强，但已被 `V6-A core` 充分覆盖，不值得进入 V6-B

动作：

- 不入 active research
- 必须写一句排除理由

### 4. `DOWNGRADE_ACTIVE_NAME`

适用条件：

- 名字已经在 `active_research`
- 但连续走弱，或者反证开始强化

动作：

- 从 `active_research` 降到 `watch_add_candidate` 或 `observe_only`
- 必须说明：是价格弱、主题弱、还是反证成立

## Active Name 降级规则

### 软降级

满足任一：

- `score < 55` 连续 `2` 周
- 连续 `2` 周弱于 theme benchmark
- 价格仍在 `MA200` 上方，但明显掉出主题主升浪队列

处理：

- `active_research -> watch_add_candidate`

### 硬降级

满足任一：

- `score < 45`
- 跌破 `MA200` 且 `rel60_vs_theme_benchmark` 明显转负
- 原先的核心 thesis 被反证

处理：

- `active_research -> observe_only`
- 若 thesis 明确失效，可直接移出 registry 的周度优先层

## Coverage Gap 处理规则

`coverage gap` 先不讨论买不买，先回答：

1. 这是 theme 里的真候选，还是顺手放进去的陪跑？
2. 值不值得消耗 K 线额度补数据？
3. 补完数据后，它最可能是：
   - `watch_add_candidate`
   - `observe_only`
   - `排除`

优先级：

1. 先补 `watch_add_candidate`
2. 再补 `observe_only`
3. `theme_watch` 只有在 theme wake-up 时才提升优先级

## 外部短线网络提示处理规则

当朋友、交易群或外部短线网络先于 Radar 发现强势标的时，不直接追买，也不直接否定 Radar。
这些标的统一进入 `External Short Network Sample` 复盘口径，用来提炼可复制的扫描特征。

硬性分流规则：

- `independent_discovery`：Radar 在排除朋友/外部样本后自行发现的标的，才允许进入正式候选讨论。
- `external_sample_review`：朋友、交易群或外部短线网络先提示的标的，只能做方向归因、漏网复盘和追高风险评估。
- 外部样本不得被包装成 Radar 独立 Alpha；若后续要进入买入候选，必须在独立扫描或 Missing Opportunity Review 中重新通过。
- 已经短期大涨的样本，默认先回答“能否追高”，再回答“是否属于好公司/好主题”。

重点回答四个问题：

1. 它属于哪个正在扩散的主线，还是单日投机/期权流？
2. 它上涨前是否已经出现价格、成交量、相对强度或期权异动？
3. 它是主题内的“滞后补涨低预期标的”，还是已经被主线验证的核心标的？
4. Radar 没发现它，是因为 universe 缺失、价格数据缺失、主题映射缺失，还是评分规则太慢？

每个样本都必须拆成六类共性因子：

| 因子 | 要判断的问题 | 例子 |
| --- | --- | --- |
| 主题/热点 | 是否属于正在扩散的主线，而不是孤立上涨 | AI 数据中心、机器人、光通信、核电、电力设备 |
| 动能转换 | 是否从弱势/横盘转为明显强于市场和同主题 | 20/60日相对强度抬升、跑赢 QQQ/SMH/XLI |
| 技术形态 | 是否完成突破、均线修复或平台放量 | 突破 3个月高点、站回 MA50/MA200、平台突破 |
| 成交量/资金 | 是否有明显量能确认 | 放量突破、连续资金流入、成交额排名提升 |
| 催化/叙事 | 是否有订单、财报、指引、政策或客户验证 | AI capex、数据中心订单、机器人发布、监管变化 |
| 衍生品/短线情绪 | 是否有期权异动、短 squeeze 或社群关注 | call volume/OI 异常、短线交易圈集中讨论 |

最后必须给出一个 `commonality_verdict`：

- `THEME_DIFFUSION_CONFIRMED`：主题扩散 + 动能/技术确认，值得进入 Radar 重点复盘。
- `MOMENTUM_ONLY`：价格强，但主题或基本逻辑不清，保持观察。
- `CATALYST_ONLY`：有新闻催化，但价格/量能未确认，保持观察。
- `SPECULATIVE_FLOW_ONLY`：更像期权/短 squeeze/社群流量，不进入 V6-B。
- `ALREADY_COVERED_ELSEWHERE`：已被 V6-A 或主仓逻辑覆盖，不重复纳入。

本类样本的默认动作：

- 若有清晰主题传导且数据缺失，先标记 `needs_price_cache`。
- 若逻辑强、但还没完成数据验证，放入 `watch_add_candidate`。
- 若逻辑偏边缘或更像单日投机，放入 `observe_only`。
- 只有补完数据并通过 Missing Opportunity Review / scorecard 后，才允许讨论 `active_research`。

当前观察到的共性假设：

- 标的往往不是第一眼最热门龙头，而是主线扩散到二阶/三阶时的低预期承接者。
- 触发通常来自“主题重新定价 + 相对强度突然抬升 + 资金开始寻找未充分定价环节”。
- 它们不一定适合价值主仓，但非常适合训练 V6-B 的动态资源池。
- 这类机会的目标不是抓第一个涨停/第一根大阳线，而是识别主升浪是否仍可延续。

## 跨主题主线扩散方法论

这套机制不只服务 AI。  
未来任何能形成大级别行情的主线，都按同一套生命周期处理：

`主线确认 -> 龙头重估 -> 二阶扩散 -> 三阶补涨 -> 情绪尾声 -> 退潮`

Radar / V6-B 的任务不是预测每个主题，而是在主题已经出现市场确认后，尽快识别：

1. 龙头是否已经完成第一轮定价
2. 资金是否开始外溢到二阶/三阶受益者
3. 哪些标的兼具低预期、价格动能和可讲清楚的产业链位置
4. 哪些只是尾声投机，不能进入系统候选

### 可迁移主题示例

| 主线 | 龙头层 | 二阶扩散 | 三阶补涨/低预期载体 |
| --- | --- | --- | --- |
| AI 算力 | GPU / hyperscaler | 网络、ASIC、HBM、光通信 | 小型光模块、封装、散热、电力设备 |
| 机器人 | 整机 / 平台公司 | 伺服、电机、减速器、传感器 | 工业自动化、测试设备、零部件小票 |
| 电力 / 核电 | 核电运营、电网龙头 | 变压器、开关、电缆、储能 | 工程服务、材料、区域公用事业 |
| 医药创新 | 平台药企 / 核心管线 | CXO、上游耗材、检测 | 低预期小 biotech、设备服务商 |
| 消费复苏 | 品牌龙头 | 渠道、供应链、广告平台 | 区域零售、上游制造、低估值补涨 |
| 金融重估 | 交易所 / 大行 / 券商 | 资管、保险、金融科技 | 高 beta 区域金融、经纪业务受益者 |

### 主线扩散评分原则

一个外部推荐样本如果同时满足以下 `4/6`，就应进入 Radar 重点复盘：

1. 主题已被市场确认，不是孤立新闻
2. 标的处在二阶或三阶受益链条，且过去预期不高
3. 20/60 日相对强度明显转强
4. 技术上突破平台或站回关键均线
5. 成交量/成交额明显放大
6. 有财报、订单、政策、客户或产业链催化支撑

但即使满足 `4/6`，也只代表“值得复盘/入候选”，不代表直接买入。  
是否交易仍必须经过 V6-B、Overlay 或明确的人工小额实验规则。

### 追高处理规则

Radar 对所有高分候选必须同时输出 `chase_risk` 和 `trade_posture`。

| 场景 | 默认处理 |
| --- | --- |
| 20日和60日涨幅都已大幅兑现，且接近阶段高位 | 禁止直接追高，只允许等回撤/盘整或小额期权彩票规则 |
| 趋势强但短期涨幅偏大 | 只允许小仓试错，必须有预设亏损上限 |
| 强度高但不极端 | 进入正式复核，仍不是自动买入 |
| 趋势未确认 | 观察，不追 |

这条规则的目的不是错过强势股，而是避免把“已经涨很多的正确方向”误判成“现在仍有好赔率的买点”。

## 本轮最重要的纪律

- `critical miss` 不等于立刻入池
- `coverage gap` 不等于一定值得补
- `active-but-weak` 不等于立刻删除

真正目标不是追涨，而是让：

- 漏网原因可复盘
- 入池理由可追踪
- 降级理由可复述

## 2026-06-01 额度刷新后的首个动作

1. 先补 `AAOI / ASX / LITE`
2. 再补 `ROK / ETN / HON / IR / TER`
3. 重跑 `Missing Opportunity Review`
4. 用本 SOP 对 `critical miss / coverage gap / active-but-weak` 做第一轮正式 triage
