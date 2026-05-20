# 2026-05-20 V6-A + V6-B Sleeve Blend First Read v1

## Question

Can V6-B's dynamic theme rotation be combined with V6-A's steadier large-cap attack engine and hedge sleeves to raise total portfolio Sharpe?

## Test

- Script: `v6ab_sleeve_blend_backtest.py`
- Window: `2012-05-21` to `2026-05-19`
- V6-A source: `backtest_results/attack_engine_replay/attack_replay_daily_20260520_live_refreshed.csv`
- V6-B source: local rerun of `ETF theme discovery -> theme-to-stock expression`
- Hedge sleeves tested: `GLD`, `IEF`, `BIL`
- Report: `backtest_results/v6ab_sleeve_blend/v6ab_sleeve_blend_20260520_v1.md`

This is a research blend only. It does not change live V6-A execution.

## Standalone Baseline

| sleeve | ann | maxDD | Sharpe |
| --- | ---: | ---: | ---: |
| `V6A` | `+28.2%` | `-21.1%` | `0.99` |
| `V6B guarded theme-to-stock` | `+25.7%` | `-24.3%` | `0.84` |
| `V6B raw theme-to-stock` | `+29.6%` | `-31.6%` | `0.82` |
| `SPY` | `+14.7%` | `-33.7%` | `0.60` |
| `QQQ` | `+20.0%` | `-35.1%` | `0.75` |
| `GLD` | `+7.2%` | `-42.1%` | `0.21` |

## Best Blend

Best risk-adjusted blend:

- `V6A`: `60%`
- `V6B guarded theme-to-stock`: `30%`
- `GLD`: `10%`
- Annualized return: `+26.2%`
- Max drawdown: `-17.9%`
- Sharpe: `1.06`

This improves Sharpe versus both standalone sleeves:

- Versus V6-A: `0.99 -> 1.06`
- Versus V6-B guarded: `0.84 -> 1.06`
- Versus QQQ: `0.75 -> 1.06`

It also lowers drawdown versus V6-A:

- V6-A max drawdown: `-21.1%`
- Best blend max drawdown: `-17.9%`

## Higher Return Blend

Best high-return blend among the top ranks:

- `V6A`: `70%`
- `V6B raw theme-to-stock`: `30%`
- Annualized return: `+29.7%`
- Max drawdown: `-20.6%`
- Sharpe: `1.05`

This keeps return near the aggressive V6-B result while maintaining drawdown close to V6-A.

## Correlation Read

Daily return correlations:

- `V6A` vs `V6B guarded`: about `0.54`
- `V6A` vs `V6B raw`: about `0.51`
- `V6A` vs `GLD`: about `0.07`
- `V6B guarded` vs `GLD`: about `0.10`
- `V6A` vs `QQQ`: about `0.54`

Interpretation:

- V6-B is not independent enough to create a huge Sharpe jump by itself, but it is different enough to improve the V6-A curve.
- GLD is the cleaner diversification leg; its standalone Sharpe is weak, but its low correlation makes it useful inside the blend.
- IEF did not improve the first-ranked blends materially in this window.

## Verdict

The intended architecture is validated at first-pass research level:

`V6-A stability + V6-B dynamic main-theme rotation + GLD hedge sleeve`

The best first-pass allocation is:

`60% V6-A / 30% V6-B guarded / 10% GLD`

This is not yet a production allocation. Before live allocation changes, the next required checks are:

1. Walk-forward sleeve sizing.
2. OOS validation by subperiod.
3. Crisis-window attribution for 2018Q4, 2020, 2022, and 2025.
4. Capital cap mapping from research weights to the current real-account V6-A pilot size.
5. Explicit rule for when V6-B sleeve is disabled or cut in half.

