# V6-B 2026-06-01 执行卡

- Status: ready
- Scope: `K线额度刷新后` 的第一轮 `Radar / V6-B` 正式执行顺序
- Boundary: 这是 `research / validation / governance` 执行卡，不是自动提升 V6-B 预算的授权

## 一句话目标

`6月1日不是“看一眼再说”，而是按固定顺序把数据补齐、候选池审计、scorecard、standalone、synthetic historical、allocator judgement 一次跑完。`

## 执行前提

以下任意一项不满足，当天状态直接记为 `BLOCKED`：

1. Futu OpenD 正常
2. 历史 K 线额度已刷新
3. 本地仓库在正确目录
4. 关键配置文件存在：
   - `v6_strategy_lab/configs/v6b_point_in_time_universe_seed_20260510.json`
   - `v6_strategy_lab/configs/v6b_candidate_registry_v1.json`
   - `v6_strategy_lab/configs/v6b_missing_opportunity_review_theme_map_v1.json`

## Step 1. 先补价格缓存

优先只补缺失，再决定是否全量重刷。

```bash
python3 v6b_fetch_radar_price_cache.py \
  --config v6_strategy_lab/configs/v6b_candidate_registry_v1.json \
  --start 2018-01-01 \
  --only-missing \
  --report 20260601_refresh
```

如果 `only-missing` 仍失败，再讨论分 ticker 重试，不要直接跳过。

## Step 2. 跑 Missing Opportunity Review

```bash
python3 v6b_missing_opportunity_review.py
```

当日要记录四个数字：

- `critical_miss_count`
- `theme_wakeup_count`
- `coverage_gap_count`
- `active_weak_count`

额外强制复盘：

- `US.MRVL`：外部短线网络提示的 AI 数据中心 / networking 漏网样本，判断是否从 `watch_add_candidate` 晋升。
- `US.NOK`：外部短线网络提示的 telecom / optical-network adjacency，判断是主题扩散还是单日投机，默认不因单日上涨晋升。

这类样本统一归入 `External Short Network Sample`：

- 不作为立即买入依据。
- 主要用来反推 Radar 的缺口。
- 每个样本必须归因到 `universe 缺失 / 数据缺失 / 主题映射缺失 / 评分规则太慢 / 合理排除` 之一。
- 若多次出现同类漏网，下一轮必须升级 Radar 扫描规则，而不是继续人工补丁。

每个样本必须拆成六类共性因子：

1. `主题/热点`：是否属于 AI、机器人、光通信、电力、核电等正在扩散的主线
2. `动能转换`：是否从弱势/横盘切换为跑赢 QQQ、SMH 或同主题 benchmark
3. `技术形态`：是否突破平台、站回 MA50/MA200、接近新高或完成趋势修复
4. `成交量/资金`：是否放量、成交额排名提升、连续资金流入
5. `催化/叙事`：是否有订单、财报、指引、政策、客户验证或产业链验证
6. `衍生品/短线情绪`：是否有期权异动、短 squeeze、社群集中讨论

最终 verdict 只能五选一：

- `THEME_DIFFUSION_CONFIRMED`
- `MOMENTUM_ONLY`
- `CATALYST_ONLY`
- `SPECULATIVE_FLOW_ONLY`
- `ALREADY_COVERED_ELSEWHERE`

本机制不只服务 AI。未来任何大主线都按同一条扩散链处理：

`主线确认 -> 龙头重估 -> 二阶扩散 -> 三阶补涨 -> 情绪尾声 -> 退潮`

执行时必须判断当前主题处在哪一段：

- 如果还在 `龙头重估`，优先看核心龙头和一阶受益者。
- 如果进入 `二阶扩散`，重点寻找低预期但动能刚确认的产业链环节。
- 如果已经到 `三阶补涨`，只能小心识别是否仍有主升浪，不能把尾声投机当成新主线。
- 如果进入 `退潮`，任何外部推荐都默认降级为复盘样本，不新增风险。

一个样本若满足 `4/6` 共性因子，就进入 Radar 重点复盘；是否交易仍由 V6-B / Overlay / 人工小额实验规则决定。

## Step 3. 审计 point-in-time universe

```bash
python3 v6b_universe_audit.py \
  --config v6_strategy_lab/configs/v6b_point_in_time_universe_seed_20260510.json
```

如果这里不过，不进入下一步。

## Step 4. 生成最新 scorecard

```bash
python3 v6b_score_universe.py \
  --universe v6_strategy_lab/configs/v6b_point_in_time_universe_seed_20260510.json \
  --tag 20260601_refresh
```

看三件事：

1. 当前 active names 的分数排序
2. `watch_add_candidate` 里有没有应该晋升的
3. robotics / optics / AI supply chain 有没有主题唤醒
4. `MRVL / NOK` 这类朋友先发现的名字，Radar 漏网原因是否能被归因到 universe、数据、主题映射或评分规则

## Step 5. 生成回测可用 universe config

```bash
python3 v6b_build_universe_config.py \
  --universe v6_strategy_lab/configs/v6b_point_in_time_universe_seed_20260510.json \
  --scorecard v6_strategy_lab/scorecards/v6b_scorecard_20260510_seed_refresh.json \
  --as-of 2026-06-01 \
  --tag 20260601_refresh
```

如果 scorecard 文件名当日不同，按最新产物替换，不要硬写死。

## Step 6. 跑 live-forward / standalone challenger

```bash
python3 v6b_radar_momentum_challenger.py \
  --config v6_strategy_lab/configs/generated/v6b_generated_universe_20260510_seed.json \
  --start 2026-05-10 \
  --tag 20260601_refresh
```

当日关注：

- pipeline 是否通
- 是否仍有 cache holes
- 当前 live-forward 读数是否稳定

## Step 7. 跑 synthetic historical 双轨验证

先生成历史快照：

```bash
python3 v6b_synthetic_historical_radar_generator.py \
  --seed v6_strategy_lab/configs/v6b_point_in_time_universe_seed_20260510.json \
  --start 2018-01-01 \
  --end 2025-12-31 \
  --tag 20260601_refresh
```

再跑 challenger：

```bash
python3 v6b_synthetic_historical_challenger.py \
  --manifest v6_strategy_lab/configs/synthetic_history/20260513_v1c_2025e/manifest.json \
  --start 2018-01-01 \
  --end 2025-12-31 \
  --tag 20260601_refresh
```

如果新 generator 产物路径变了，就用当次 manifest，不沿用旧路径。

## Step 8. 再做 allocator judgement

注意：`allocator` 只有在前面都跑完后才有意义。

```bash
python3 v6_allocator.py \
  --metrics v6_strategy_lab/configs/v6_allocator_sample_metrics.csv \
  --output backtest_results/v6_allocator/allocator_20260601_refresh.json
```

这一步不是为了强行给 V6-B 权重，而是正式回答：

- 现在是否仍然 `V6-A 100 / V6-B 0`
- 如果不是，为什么

## Step 9. 当天必须产出的 5 份判断

1. `Missing Opportunity Review`
2. `最新 scorecard`
3. `V6-B standalone read`
4. `synthetic historical read`
5. `allocator judgement`

少任何一份，当天状态记为：

`PARTIAL_ONLY`

## 当天最终结论只能三选一

### A. 继续研究，不给预算

适用条件：

- standalone 不稳
- synthetic historical 仍弱
- allocator 仍给 `0%`

### B. 进入更严肃 challenger review

适用条件：

- 某一轨道明显改善
- 但还不够 production-ready

### C. 申请极小研究预算讨论

适用条件：

- standalone / synthetic / allocator 三层都明显改善
- 且 point-in-time / replay / tradability 没问题

注意：这也只是 `讨论资格`，不是自动上线。

## 纪律

`6月1日最重要的不是跑出一个好看的结果，而是按固定顺序把 V6-B 的研究供给链正式跑通。`
