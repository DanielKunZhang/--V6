# V6-B Real Stock Pool v1 First Read

- Date: `2026-05-20`
- Objective: replace ETF/proxy-heavy cross-theme PIT with a real-stock V6-B candidate pool.
- Universe config: `v6_strategy_lab/configs/v6b_real_stock_theme_universe_v1.json`
- Price fetch report: `backtest_results/v6b_radar_momentum/v6b_real_stock_pool_fetch_20260520.json`
- PIT manifest: `v6_strategy_lab/configs/synthetic_history/20260520_v5_real_stock_pit/manifest.json`
- Quick compare: `backtest_results/v6ab_candidate_quick_compare/v6ab_candidate_quick_compare_20260520_real_stock_pit_v1.csv`

## Data Work

Built a 142-symbol cross-theme real-stock universe. ETFs remain benchmarks only.

Fetched 95 missing symbols from Futu historical K-line API:

- Pre-fetch quota: `59/1000` used, `941` remaining.
- Fetch result: `95/95` ok.
- Cache audit: `142/142` symbols available and fresh through the 2026-05-19 window.

## What Changed

The new pool adds real stocks across:

- AI compute / data center
- software / internet
- healthcare / biotech / medtech
- energy / commodities
- precious-metal miners
- financials / capital markets
- industrials / infrastructure / automation
- utilities / power / grid
- consumer discretionary / travel / leisure

The resulting PIT snapshots are materially better than the ETF/proxy version. Examples:

- 2020-06: `MRNA, DXCM, REGN`, `GOLD, PAAS, HMY`, `DDOG, NET, NOW`
- 2021-12: `DVN, CVX, FANG`, `VST, EXC, NEE`
- 2022-06: `OXY, VLO, XOM`, `LLY, VRTX, UNH`
- 2024-03: `VRT, NVDA, COHR`, `VST, CEG, NRG`, `KKR, C, BAC`
- 2026-05: `HAL, VLO, MPC`, `PWR, GEV, ETN`, `DDOG, GOOGL, AMZN`

## First Backtest Read

| candidate | standalone V6-B ann | standalone Sharpe | V6AB ann | V6AB maxDD | V6AB Sharpe | verdict |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| V2 static theme-stock | `25.7%` | `0.84` | `31.8%` | `-15.7%` | `1.23` | baseline |
| AI-only PIT | `21.6%` | `0.76` | `29.8%` | `-16.3%` | `1.19` | not upgrade |
| real-stock full PIT | `18.7%` | `0.69` | `27.7%` | `-17.2%` | `1.11` | not upgrade |
| real-stock hybrid gap-fill PIT | `25.4%` | `0.82` | `30.4%` | `-16.8%` | `1.18` | best new direction, not upgrade |

## Interpretation

This is the right direction, but v1 is not yet a V3 promotion.

The useful result is architectural:

- Full replacement still dilutes V6-B alpha.
- Hybrid gap-fill is much better: keep V2 AI/tech strength, use real-stock PIT to fill healthcare, energy, financials, industrials, utilities/power, and precious-metals gaps.
- Real stocks improve the quality of theme expression versus ETFs, but the scoring and membership still need tightening before it can beat V2.

## Decision

Do not replace the active V6AB paper-sim V2.

Keep `real-stock hybrid gap-fill PIT` as the leading V6-V3 research path.

## Next Work

Improve the real-stock pool itself:

- remove weak or slow candidates that dilute convexity,
- separate defensive/quality leaders from high-beta thrust candidates,
- add external alpha evidence only when it changes inclusion, exclusion, or ranking,
- test per-theme candidate quality before blending into V6AB,
- keep V2 as benchmark until a candidate clears full-window and stress-window gates.
