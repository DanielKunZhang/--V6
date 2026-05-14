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
