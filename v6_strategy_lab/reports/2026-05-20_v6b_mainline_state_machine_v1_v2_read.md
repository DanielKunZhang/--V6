# V6-B Mainline State Machine v1/v2 Read

- Date: `2026-05-20`
- Objective: convert the dominant-theme idea into a stateful mainline engine.
- Quick compare v1: `backtest_results/v6ab_candidate_quick_compare/v6ab_candidate_quick_compare_20260520_mainline_state_v1.csv`
- Quick compare v2: `backtest_results/v6ab_candidate_quick_compare/v6ab_candidate_quick_compare_20260520_mainline_state_v2.csv`
- PIT manifest: `v6_strategy_lab/configs/synthetic_history/20260520_v7_real_stock_pit_quality_v1/manifest.json`

## What Changed

Added two research-only selection modes:

- `mainline_state_v1`: starts in multi-theme fallback, confirms a single mainline after consecutive leadership, exits after deterioration.
- `mainline_state_v2`: replaces simple consecutive leadership with a persistence score. Themes accumulate score when they remain top-ranked with enough breadth and decay when they fall out of leadership.

Both modes keep V6-A and the current V6AB overlay unchanged. Only V6-B theme selection changes.

## Result

| candidate | standalone ann | standalone maxDD | standalone Sharpe | best V6AB ann | best V6AB maxDD | best V6AB Sharpe | 2024-2026 ann |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| active V2 baseline | `25.67%` | `-24.29%` | `0.8416` | `31.83%` | `-15.68%` | `1.2345` | `57.40%` |
| quality-gated hybrid PIT | `26.33%` | `-26.53%` | `0.8576` | `30.76%` | `-16.02%` | `1.1910` | `56.01%` |
| mainline state v1 | `24.94%` | `-32.29%` | `0.7328` | `29.22%` | `-21.28%` | `1.1054` | `59.46%` |
| mainline state v2 | `22.63%` | `-30.04%` | `0.6517` | `29.35%` | `-16.92%` | `1.0893` | `67.53%` |

## Interpretation

The architecture is moving in the right direction, but the current signal is not ready.

What improved:

- v2 confirmed AI/semis as the recent mainline more cleanly.
- v2 produced the best `2024-2026` V6AB annualized return among the new candidates: `67.53%`.
- v2 reduced the v1 drawdown problem materially in V6AB: `-16.92%` versus v1 `-21.28%`.

What failed:

- Full-window standalone V6-B dropped to `22.63%`.
- Full-window V6AB still trails the active V2 baseline by a wide margin.
- 2020 and 2022 stress behavior remains weak, which means the state machine is not yet robust across market regimes.

The reason is important: `theme_scores()` is currently a tactical monthly momentum score. It can help the radar, but it is not yet a true market-mainline classifier. A real mainline needs higher-level evidence:

- multi-quarter persistence,
- theme breadth at stock level,
- leadership versus broad beta,
- whether the theme is offensive or defensive/commodity spike,
- whether the theme can sustain enough high-quality stock expressions.

## Decision

Do not promote `mainline_state_v1` or `mainline_state_v2`.

Keep the active $50k paper simulation on `V6AB_SIM_CANDIDATE_V2_DYNAMIC_B_SIZING`.

Keep the mainline state machine as the correct V6-V3 architecture path, but replace the current monthly score with a real mainline classifier before further promotion tests.

## Next Work

Build a separate `mainline_classifier` layer:

- score themes over 3/6/12-month horizons, not only monthly rebalance score,
- require stock-level breadth and top-name quality,
- separate offensive growth mainlines from defensive/commodity spikes,
- use current V2 AI/infra expression as fallback when no superior mainline is confirmed,
- only allow a new theme to replace the B attack sleeve after starter-stage and confirmation-stage evidence.
