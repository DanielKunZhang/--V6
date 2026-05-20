# 2026-06-01 V6-B + Radar 主线扫描 Data Refresh Execution Card v2

- Status: ready
- Purpose: 在 Futu 历史 K 线额度刷新后，补齐 Radar 缺失候选数据，重跑自动主线扩散扫描，并完成第一轮正式 triage。

## 2026-05-20 提前执行进度

OpenD 历史 K 线额度已提前恢复，因此本卡中一部分 6月1日动作已经在 `2026-05-20` 执行。

### 已完成

- `US.AAOI / US.ASX / US.LITE` 第一批价格缓存已补到 `2026-05-19`。
- V6-B / Radar 扩展所需的 `US.COHR / US.WDC / US.INTC / US.AMKR / US.SMH / US.SOXX` 已按最小必要范围补齐到 `2026-05-19`。
- `radar_theme_rotation_scanner.py --tag 20260520_quota_refresh --sync-desktop` 已运行。
- `v6b_missing_opportunity_review.py --tag 20260520_quota_refresh` 已运行。
- 正式 triage 已落地：
  - `US.COHR`: `watch_add_candidate -> active_research`
  - `US.AAOI`: `observe_only -> watch_add_candidate`
  - `US.MRVL`: 保持 `watch_add_candidate`，但标记 stale cache / 高追高风险
  - `US.NOK`: 保持 `observe_only`，只做外部样本归因
  - `US.ANET / US.TSM`: 保持 active，但被标记为 active-but-weak / 需持续观察
- `v6_strategy_lab/configs/v6b_point_in_time_universe_seed_20260510.json` 已加入 `US.COHR`，entry date 为 `2026-05-20`，避免回填到 2026-05-10。
- 已完成第一版动态 V6-B synthetic historical 纠偏：静态名单回测被降级为风险检查；新增 `optics_and_interconnect` track，纳入 `US.COHR / US.LITE / US.AAOI`。
- 已新增并运行 V6-B 第一层跨主题 ETF rotation v0：
  - 脚本：`v6b_theme_rotation_backtest.py`
  - 区间：`2018-01-01` 至 `2025-12-31`
  - 目的：先用 ETF / 行业代理识别当期主线，再进入主题内候选池，避免 V6-B 被固定为 AI infra 子策略。
  - 初步结果：最佳 v0 配置约 `+15.3%` 年化、`-38.8%` 最大回撤、Sharpe `0.49`；2020 和 2024-2025 有主线捕捉能力，但风险控制明显不足，不能作为 allocator 版本。
- 已试跑 ETF theme rotation `v1_guarded` 风控变体：
  - 加入 overheat cooldown、vol target、drawdown brake。
  - 结果不合格：最佳 v1_guarded 约 `+10.5%` 年化、`-30.2%` 最大回撤、Sharpe `0.38`，低于 v0 的收益/Sharpe，且回撤改善不足。
  - 结论：当前 v1_guarded 不作为候选版本，只保留为反例；下一版应重做主题退潮识别和 sleeve sizing，而不是简单压风险资产权重。
- 已按“额度应花在提高系统判断力处”的原则，用 OpenD 刷新主题 ETF / 行业代理到 `2026-05-19`：
  - `US.XLK / US.XBI / US.XLV / US.XLE / US.XOP / US.SLV / US.GDX / US.XLF / US.KRE / US.XLI / US.XLU / US.XLY / US.ARKK / US.IGV / US.FDN / US.IWM / US.IEF / US.DBC`
  - 报告：`backtest_results/v6b_theme_rotation/v6b_fetch_theme_etf_cache_report_20260520.json`
  - 使用 18 个标的额度，远低于月度 1000 标的额度。
- 用最新 ETF 缓存重跑到 `2026-05-19`：
  - v0 最佳约 `+16.0%` 年化、`-38.8%` 最大回撤、Sharpe `0.51`。
  - v1_guarded 仍不合格，最佳约 `+10.4%` 年化、`-30.2%` 最大回撤、Sharpe `0.37`。
  - 近期主题识别显示 `Gold / Precious Metals` 与 `Semis / AI Compute` 持续靠前，2026-05-19 top themes 为 `Semis / AI Compute`、`Energy / Resources`、`Broad Beta`。

### 部分完成

- `US.MRVL / US.NOK` 已有本地旧缓存，但未刷新到 `2026-05-19`；当前结论仍然不允许直接追高或主动升 active。
- robotics 第二批 `US.ROK / US.ETN / US.HON / US.IR / US.TER` 已有部分历史缓存，但尚未完成本卡要求的统一 2026-06-01 刷新与正式 triage。
- Radar 当前截面扫描可以识别最高主线和二阶扩散，但 V6-B 主干仍需升级为“跨主题 ETF 主线轮动 -> 主题内候选池”的完整系统，避免 AI infra 过期后继续困在 AI 池。

### 仍待 6月1日或额度允许时完成

- 刷新第二批 robotics 全量缓存到当日最新日期。
- 刷新第三批 `US.MRVL / US.NOK` 到当日最新日期，并重跑 `external_short_network_review.py`。
- 用 ETF / 行业代理先完成 V6-B 第一层历史 theme rotation 验证，再进入各主题候选池；不要再把 AI infra 子模块结果当作完整 V6-B。
- 改进 ETF theme rotation v0：
  - 降低 `-38%` 级别回撤；
  - 增加主题退潮识别；
  - 增加“晚确认但不追尾”的 overheat / cooldown 规则；
  - 将通过的 top theme 映射到主题内候选池，而不是直接买 ETF 代理。
- 不采用 `v1_guarded` 当前实现。下一轮应优先测试：
  - theme score slope / breadth deterioration 作为退潮信号；
  - 按主题波动分配 sleeve，而不是全局固定 risk_weight；
  - theme ETF 只作为入口，实际表达转到主题内候选池；
  - V6-A + V6-B sleeve 组合层风控，而不是 ETF rotation 单独满仓跑。
- 重跑 `v6_weekly_review_board.py` 和 `investment_company_dashboard.py`，确认 backlog / 驾驶舱吸收本轮结论。
- 重新提交 6月1日正式刷新结果。

## 一句话目标

6月1日不是只补 K 线。  
当天要把 `price cache -> 自动主线扫描 -> Missing Review -> triage -> V6-B 候选更新` 串成一条链。

把当前 `coverage gap / 主线扫描候选` 推进成三种清晰状态之一：

- `PROMOTE_TO_ACTIVE_RESEARCH`
- `KEEP_IN_REGISTRY`
- `EXCLUDE_WITH_REASON`

## 今日优先名单

第一批先补：

- `US.AAOI`
- `US.ASX`
- `US.LITE`

第二批再补：

- `US.ROK`
- `US.ETN`
- `US.HON`
- `US.IR`
- `US.TER`

第三批补“外部短线网络提示但 Radar 未主动突出”的漏网样本：

- `US.MRVL`
- `US.NOK`

## 执行前检查

全部满足才开始：

1. OpenD 已启动
2. Futu 历史 K 线额度已恢复
3. 当前分支干净到可继续提交这轮结果
4. 已确认 `radar_theme_rotation_scanner.py` 可运行
5. 已确认桌面 `Radar_主线扩散自动扫描_LATEST.md` 可同步

## Step 1: 补 price cache

先跑第一批：

```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 v6b_fetch_radar_price_cache.py \
  --tickers US.AAOI,US.ASX,US.LITE \
  --start 2018-01-01 \
  --end 2026-06-01 \
  --home-dir /private/tmp/futu_v6b_home \
  --report backtest_results/v6b_missing_opportunity_review/fetch_gap_cache_report_20260601_batch1.json
```

再跑第二批：

```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 v6b_fetch_radar_price_cache.py \
  --tickers US.ROK,US.ETN,US.HON,US.IR,US.TER \
  --start 2018-01-01 \
  --end 2026-06-01 \
  --home-dir /private/tmp/futu_v6b_home \
  --report backtest_results/v6b_missing_opportunity_review/fetch_gap_cache_report_20260601_batch2.json
```

最后跑第三批：

```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 v6b_fetch_radar_price_cache.py \
  --tickers US.MRVL,US.NOK \
  --start 2018-01-01 \
  --end 2026-06-01 \
  --home-dir /private/tmp/futu_v6b_home \
  --report backtest_results/v6b_missing_opportunity_review/fetch_gap_cache_report_20260601_batch3_external_short_network.json
```

## Step 2: 先跑 Radar 自动主线扩散扫描

正式口径先跑 `independent_discovery`，排除朋友/外部短线网络样本，避免把外部样本包装成系统 Alpha：

```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 radar_theme_rotation_scanner.py \
  --exclude-external-samples \
  --tag 20260601_refresh \
  --sync-desktop
```

重点看：

- 当前最高主线是否仍为 `AI 算力与数据中心`
- 当前阶段是否仍是 `二阶扩散`
- 排除外部样本后，系统自己还能发现哪些主线和候选
- 新补数据后 `LITE / ROK / ETN / HON / IR / TER` 是否进入独立高分候选
- `AAOI / MRVL / NOK / 后续朋友样本` 只看 `external_sample_review`、漏网归因和追高风险，不作为独立发现
- 每个高分候选的 `chase_risk` 和 `trade_posture` 是否允许现在表达
- `scan_journal.json` 是否写入 2026-06-01 快照

这一步是反事后诸葛亮的关键：  
后续复盘必须基于 `2026-06-01` 当天 scanner 看到的候选，而不是未来涨完再回填。

## Step 3: 重跑 Missing Opportunity Review

```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 v6b_missing_opportunity_review.py \
  --tag 20260601_refresh
```

重点看：

- `critical misses`
- `coverage gaps`
- `active-but-weak`

## Step 4: 做正式 triage

参考：

- `v6_strategy_lab/reports/2026-05-14_v6b_radar_weekly_triage_sop_v1.md`
- `v6_strategy_lab/scorecards/v6b_radar_weekly_triage_template.md`
- `backtest_results/radar_theme_rotation_scanner/latest.md`

本次最重要的人工判断：

1. `US.COHR` 是否从 `watch_add_candidate` 升到 `active_research`
2. `US.ASX` 补完数据后是否保持 `watch_add_candidate`
3. `US.AAOI` 补完数据后是否从 `observe_only` 升到 `watch_add_candidate`
4. robotics 名单里是否有任何名字值得从 `theme_watch` 升级
5. `US.MRVL` 是否应从 `watch_add_candidate` 升到 `active_research`
6. `US.NOK` 是真实 AI 网络基础设施扩散，还是单日投机/期权流导致的合理排除
7. `US.ANET / US.TSM` 是否仍属于 `active-but-weak`
8. 自动主线扫描给出的最高主题、阶段和高分候选是否与 Missing Review 一致
9. 如果 scanner 高分但 Missing Review 没提示，判断是 theme map 缺失还是 score 口径差异

对 `MRVL / NOK / 后续朋友提示的强势票`，必须额外写一张共性因子表：

| 标的 | 主题/热点 | 动能转换 | 技术形态 | 成交量/资金 | 催化/叙事 | 衍生品/短线情绪 | commonality_verdict |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `US.MRVL` | 待补 | 待补 | 待补 | 待补 | 待补 | 待补 | 待判定 |
| `US.NOK` | 待补 | 待补 | 待补 | 待补 | 待补 | 待补 | 待判定 |

这张表以后不只用于 AI。任何外部推荐强势票都必须先归入主线生命周期：

`主线确认 / 龙头重估 / 二阶扩散 / 三阶补涨 / 情绪尾声 / 退潮`

若连续多次漏掉同一阶段的机会，说明 Radar 需要升级对应扫描规则：

- 漏掉 `龙头重估`：核心 universe 不完整
- 漏掉 `二阶扩散`：产业链映射不完整
- 漏掉 `三阶补涨`：低预期/动能转换扫描不足
- 把 `情绪尾声` 误判成新机会：风控和退潮识别不足

## Step 5: 按 verdict 改 registry / universe

如果结论只是：

- `KEEP_IN_REGISTRY`
- `EXCLUDE_WITH_REASON`
- `DOWNGRADE_ACTIVE_NAME`

只改：

- `v6_strategy_lab/configs/v6b_candidate_registry_v1.json`

只有在明确满足：

- 主题逻辑清楚
- 数据已补齐
- 反证条件写得清楚
- 本次 verdict 是 `PROMOTE_TO_ACTIVE_RESEARCH`

才允许继续改：

- `v6_strategy_lab/configs/v6b_point_in_time_universe_seed_20260510.json`

## Step 6: 重跑 External Short Network Review

```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 external_short_network_review.py \
  --tag 20260601_refresh \
  --sync-desktop
```

确认：

- `MRVL / NOK` 的 gap attribution 是否从 `数据缺失` 变成可判断状态
- 六因子表是否可以开始填真实判断

## Step 7: 重跑 Weekly Review Board

```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 v6_weekly_review_board.py \
  --tag 20260601_refresh
```

确认 backlog 是否出现：

- `radar_missing_opportunity`
- `radar_coverage_gaps`

并检查新 priority 是否合理。

## Step 8: 刷新每日驾驶舱

```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 investment_company_dashboard.py \
  --tag 20260601_refresh \
  --sync-desktop
```

确认驾驶舱显示：

- Radar 自动主线扫描
- 当前最高主线
- 当前阶段
- 候选数 / 缺失价格缓存

## Step 9: 提交并推 GitHub

最少应提交：

- 最新 fetch reports
- 最新 Radar 主线扫描报告
- 最新 scan journal
- 最新 missing opportunity review
- 最新 external short network review
- 最新 weekly review / backlog
- 若有变动，则包含 registry / universe 更新

建议 commit message：

```text
research: refresh v6b radar coverage after june quota reset
```

## 今天的成功标准

最低成功：

- 第一批 `AAOI / ASX / LITE` 不再是 `no_local_price_cache`
- `radar_theme_rotation_scanner.py` 能跑出主线排名、阶段和候选
- `scan_journal.json` 写入 2026-06-01 快照
- 能完成一轮正式 triage

中等成功：

- `COHR / ASX / AAOI` 三者的层级关系更清楚
- robotics 至少从“纯 gap”进入“有数据可评估”
- `MRVL / NOK` 不再只是外部样本，而是能被自动 scanner 归入明确主线阶段

最好结果：

- 有 `1-2` 个名字能合理晋级到 `active_research`
- 同时有 `1-2` 个旧 active 名字被诚实降级
- 自动主线扫描和 Missing Review 对同一批二阶/三阶候选给出一致提示

## 如果当日仍失败

### 情况 A：OpenD 不通

- 停止抓数
- 记录 blocker
- 不做 theme 结论升级

### 情况 B：额度仍不足

- 先补 registry / triage 文字结论
- 继续保持当前 universe 不动

### 情况 C：数据补齐但没有任何名字值得升级

- 这是有效结论，不算失败
- 重点是把“为什么不升”写清楚
