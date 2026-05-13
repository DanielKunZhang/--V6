# V6-B Synthetic Historical v1

- Date: 2026-05-13
- Status: research_only
- Scope: first working `synthetic historical Radar generator` plus first clean challenger readout.

## 一句话结论

在当前 `price-only`、`no-lookahead`、`2018-01-01 ~ 2025-12-31` 的干净口径下，`V6-A` 仍然是最强基线；`V6-B` 尚未证明自己应该获得 allocator 权重。

## 这次做了什么

1. 新建 `v6b_synthetic_historical_radar_generator.py`
   - 月度生成 `point-in-time` 历史快照
   - 输出路径：`v6_strategy_lab/configs/synthetic_history/20260513_v1c_2025e/`

2. 新建 `v6b_synthetic_historical_challenger.py`
   - 用历史快照驱动动态 risk pool
   - 跑 `V6-A baseline / V6-B standalone / V6-AB overlay`

3. 固定第一版 generator policy
   - `v6_strategy_lab/configs/v6b_synthetic_historical_generator_policy_v1.json`

## 为什么正式口径先收在 2025-12-31

- `SMH` 本地缓存完整覆盖到 `2025-12-31`
- `2026-01` 之后半导体 benchmark 缓存不完整，会污染 `bottleneck_diffusion` 的相对强弱评分
- 因此 `2018-2025` 是当前可对外解释的 clean sample

## Clean Sample 结果

参考文件：

- `v6_strategy_lab/configs/synthetic_history/20260513_v1c_2025e/summary.md`
- `backtest_results/v6b_synthetic_historical/v6b_synth_challenger_20260513_v1c_2025e.md`

最佳基线：

- `V6-A base (mom60 top3 dd10%)`
- `AnnR +26.2% / MaxDD -26.1% / Sharpe 0.88 / OOS AnnR +47.1% / OOS Sharpe 1.28`

各 track 最好结果：

- `V6-B core_track`
  - 最好：`conc (mom60 top2 dd10%)`
  - `AnnR +19.4% / MaxDD -39.6% / Sharpe 0.57`
- `V6-B bottleneck_track`
  - 最好：`base (mom60 top3 dd10%)`
  - `AnnR +16.2% / MaxDD -42.1% / Sharpe 0.49`
- `V6-B blended_tracks`
  - 最好：`base (mom60 top3 dd10%)`
  - `AnnR +10.5% / MaxDD -38.8% / Sharpe 0.32`

overlay 最好结果：

- `V6-AB core_overlay`
  - 最好：`slow (mom120 top3 dd10%)`
  - `AnnR +24.4% / MaxDD -31.2% / Sharpe 0.74`
- `V6-AB bottleneck_overlay`
  - 最好：`base (mom60 top3 dd10%)`
  - `AnnR +23.5% / MaxDD -36.1% / Sharpe 0.70`
- `V6-AB blended_overlay`
  - 最好：`slow (mom120 top3 dd10%)`
  - `AnnR +22.6% / MaxDD -33.1% / Sharpe 0.66`

## 当前解读

1. `V6-A` 仍是最优正式基线
   - 当前没有任何 `V6-B standalone` 或 `V6-AB overlay` 在 Sharpe / drawdown / full-period quality 上击败它

2. `core_reacceleration` 有 alpha，但当前 engine 不匹配
   - 回报不是没有，但风险调整后明显弱于 `V6-A`
   - 这支持“`V6-B` 需要独立 engine 参数”的原判断

3. `bottleneck_diffusion` 的 OOS 爆发性强，但全样本质量差
   - 说明它更像主题顺风期的强扩散轨
   - 但如果没有更强的风控 / regime filter，很容易在全样本里拖累体验

4. `mixed pool` 明显劣化
   - 把 core + bottleneck + turnaround 全部揉进一个动态池，效果最差
   - 这支持后续必须分轨研究，而不是先混池

## 当前可执行结论

- `Allocator` 继续维持 `V6-A 100% / V6-B 0% / V6-C 0%`
- `V6-B` 继续是 `research challenger`
- 后续优先级：
  1. 为 `core_reaccel` 设计独立 engine 参数
  2. 为 `bottleneck_diffusion` 设计独立 regime / exit / exposure 规则
  3. 不再优先研究 `blended_tracks`

## 重要边界

- 这仍然不是最终 production validation
- generator 当前主要使用 `price-only` contemporaneous rules，尚未接入真实历史基本面修正数据
- 因此它回答的是：
  - 这套 `历史候选池生成机制` 是否比 lookahead 更诚实
  - 哪些 V6-B 轨道值得继续研究
- 它还不能回答：
  - `V6-B` 已经可以上线
  - `V6-B` 已经能拿 allocator 权重
