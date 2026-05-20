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

Best risk-adjusted static blend:

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

## Dynamic Hedge/Cash Overlay Follow-Up

After reviewing the system architecture, fixed `10% GLD` should not be treated as the default V6 design because V6-A already has defensive behavior inside the strategy. GLD / BIL should instead be a portfolio-level risk adjustment tool.

A dynamic overlay test was added:

- Base sleeve is only `V6-A + V6-B`.
- GLD / BIL is added only when market trend, base sleeve drawdown, volatility, or A/B correlation risk triggers fire.
- If GLD is above its 126-day moving average, the overlay uses GLD; otherwise it uses BIL.
- Report: `backtest_results/v6ab_sleeve_blend/v6ab_sleeve_blend_20260520_dynamic_overlay_v1.md`

Best dynamic overlay result:

- Base: `70% V6-A / 30% V6-B guarded`
- Max overlay: `25%`
- Vol trigger: `28%`
- Corr trigger: `65%`
- Drawdown trigger: `-10%`
- Annualized return: `+28.9%`
- Max drawdown: `-17.6%`
- Sharpe: `1.12`

Overlay usage:

- Total trading days: `3520`
- Any GLD/BIL overlay: `1427` days, about `40.5%`
- GLD overlay: `1065` days, about `30.3%`
- BIL overlay: `362` days, about `10.3%`
- Latest `2026-05-19` weights: `70% V6-A / 30% V6-B guarded`, no GLD/BIL overlay.

This is materially better than fixed GLD:

- Static best Sharpe: `1.06`
- Dynamic overlay best Sharpe: `1.12`
- Static best annualized return: `+26.2%`
- Dynamic overlay best annualized return: `+28.9%`
- Static best max drawdown: `-17.9%`
- Dynamic overlay best max drawdown: `-17.6%`

## Refined Overlay Result

A narrower follow-up grid tested the most promising dynamic overlay region:

- V6-B branch: `v6b_guarded_top3_90`
- Base A/B range: `65-75% V6-A` and `25-35% V6-B`
- Overlay max: `25-30%`
- Vol trigger: `28%`
- Corr trigger: `60-65%`
- Drawdown trigger: `-10%` to `-12%`
- Report: `backtest_results/v6ab_sleeve_blend/v6ab_sleeve_blend_20260520_overlay_refined_v1.md`

Best refined result:

- Base: `70% V6-A / 30% V6-B guarded`
- Max overlay: `30%`
- Vol trigger: `28%`
- Corr trigger: `60%`
- Drawdown trigger: `-12%`
- Annualized return: `+29.5%`
- Max drawdown: `-18.6%`
- Sharpe: `1.14`

More conservative nearby candidate:

- Base: `65% V6-A / 25% V6-B guarded`
- Max overlay: `30%`
- Vol trigger: `28%`
- Corr trigger: `60%`
- Drawdown trigger: `-12%`
- Annualized return: `+29.4%`
- Max drawdown: `-18.4%`
- Sharpe: `1.14`

Interpretation:

- Dynamic overlay optimization improves Sharpe from about `1.12` to about `1.14`.
- This is progress, but not enough to call the system excellent.
- A Sharpe target around `1.2+` likely requires improving signal quality and correlation control, not just tuning overlay thresholds.
- Further optimization should focus on crisis-window attribution, V6-B off-switch / half-risk rules, and reducing A/B overlap when both are effectively long high-beta growth.

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

`V6-A stability + V6-B dynamic main-theme rotation + dynamic Hedge/Cash Overlay`

The best first-pass static allocation is:

`60% V6-A / 30% V6-B guarded / 10% GLD`

But the better system-level candidate is now:

`70% V6-A / 30% V6-B guarded`, with GLD/BIL used only by dynamic overlay triggers.

The refined research candidate is:

`70% V6-A / 30% V6-B guarded / max 30% dynamic GLD-or-BIL overlay`

This candidate is still only around Sharpe `1.14`. It is acceptable as a directionally correct research baseline, but below the desired `1.2+` quality bar.

The preferred paper-sim candidate is now the dynamic V6-B sizing version described below.

## Paper Sim Candidate

The first paper-sim candidate is now fixed as:

- Config: `v6_strategy_lab/configs/v6ab_sim_candidate_v1.json`
- Base: `70% V6-A / 30% V6-B guarded`
- Overlay: max `30%` dynamic GLD/BIL
- Vol trigger: `28%`
- Corr trigger: `60%`
- Drawdown trigger: `-12%`

Paper-sim metrics:

- Window: `2012-05-21` to `2026-05-19`
- Annualized return: `+29.5%`
- Max drawdown: `-18.6%`
- Sharpe: `1.14`
- Overlay active: `1228 / 3520` days
- GLD overlay: `903` days
- BIL overlay: `325` days
- Latest `2026-05-19` weights: `70% V6-A / 30% V6-B guarded`, no overlay.

Important failed experiment:

- Adding a simple V6-B 3-month momentum / V6-B drawdown off-switch did not improve the system.
- Best B-control variants fell to about Sharpe `1.11`.
- Conclusion: do not use simple B momentum shutoff in the sim candidate. It cuts too much trend exposure.

Stress window read:

| window | ann | maxDD | Sharpe | verdict |
| --- | ---: | ---: | ---: | --- |
| `2018Q4` | `-42.3%` | `-14.4%` | `-3.45` | weak |
| `2020 COVID` | `-16.5%` | `-18.6%` | `-0.69` | weak |
| `2022 Hike` | `-8.0%` | `-11.4%` | `-1.68` | weak |
| `2025` | `+55.9%` | `-10.0%` | `1.94` | strong |
| `2024-2026` | `+50.3%` | `-17.5%` | `1.62` | strong |

Verdict:

- This is good enough to start paper simulation.
- It is not good enough for live capital allocation.
- The next improvement must target crisis-regime risk reduction, not normal-market parameter tuning.

## Dynamic V6-B Sizing Candidate

The better candidate makes V6-B sleeve size regime-aware instead of holding it at a fixed `30%`.

Config:

- `v6_strategy_lab/configs/v6ab_sim_candidate_v2.json`
- Candidate ID: `V6AB_SIM_CANDIDATE_V2_DYNAMIC_B_SIZING`

Sizing rule:

- Default V6-B weight: `30%`
- High V6-B weight: `45%`
- Low V6-B weight: `5%`
- Raise to `45%` when V6-B 126-trading-day return is at least `+8%` and both SPY / QQQ are above their 200-day moving averages.
- Cut to `5%` when V6-B 63-trading-day return is below `-8%`, or when market is below trend and A/B 63-day correlation is at least `60%`.
- Remaining non-overlay capital goes to V6-A.
- Dynamic GLD/BIL overlay remains max `30%`.

Result:

- Report: `backtest_results/v6ab_sleeve_blend/v6ab_sleeve_blend_20260520_dynamic_b_sizing_v1.md`
- Window: `2012-05-21` to `2026-05-19`
- Annualized return: `+31.8%`
- Max drawdown: `-15.7%`
- Sharpe: `1.23`
- Overlay active: `1167 / 3520` days

Improvement versus fixed-30% V6-B candidate:

| version | ann | maxDD | Sharpe |
| --- | ---: | ---: | ---: |
| `V1 fixed B 30% + dynamic overlay` | `+29.5%` | `-18.6%` | `1.14` |
| `V2 dynamic B sizing + dynamic overlay` | `+31.8%` | `-15.7%` | `1.23` |

Interpretation:

- This confirms the hypothesis: V6-B is not an all-weather enhancer.
- The system improves when V6-B expands in main-trend years and shrinks in adverse regimes.
- This is the first candidate that clears the `1.2+` quality bar.
- It is still paper-sim only until daily target weights, paper execution, and live feasibility are verified.

This is not yet a production allocation. Before live allocation changes, the next required checks are:

1. Walk-forward sleeve sizing.
2. OOS validation by subperiod.
3. Crisis-window attribution for 2018Q4, 2020, 2022, and 2025.
4. Capital cap mapping from research weights to the current real-account V6-A pilot size.
5. Explicit rule for when V6-B sleeve is disabled or cut in half.
