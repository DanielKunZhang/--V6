# V6-B Dominant Theme Mode v0 Read

- Date: `2026-05-20`
- Objective: test whether V6-B should behave as a dominant-theme attack engine instead of a multi-theme gap-fill sleeve.
- Quick compare: `backtest_results/v6ab_candidate_quick_compare/v6ab_candidate_quick_compare_20260520_dominant_theme_confirmed_v0.csv`
- PIT manifest: `v6_strategy_lab/configs/synthetic_history/20260520_v7_real_stock_pit_quality_v1/manifest.json`

## What Was Tested

Two minimal dominant-theme candidates were added for research only:

- `v6b_extra_real_stock_dominant_pit_guarded_top1_90`: each rebalance owns only the highest-scoring theme.
- `v6b_extra_real_stock_dominant_confirmed_pit_top1_90`: keeps an incumbent main theme unless a challenger leads by `0.08` for 2 consecutive months, or the incumbent falls below top 3.

Both use the quality-gated real-stock PIT pool and hold up to 3 stocks inside the selected theme.

## Result

| candidate | standalone ann | standalone maxDD | standalone Sharpe | V6AB ann | V6AB maxDD | V6AB Sharpe |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| active V2 baseline | `25.67%` | `-24.29%` | `0.8416` | `31.83%` | `-15.68%` | `1.2345` |
| quality-gated hybrid PIT | `26.33%` | `-26.53%` | `0.8576` | `30.76%` | `-16.02%` | `1.1910` |
| naive dominant top1 | `18.69%` | `-30.39%` | `0.5903` | `28.65%` | `-16.82%` | `1.1136` |
| confirmed dominant top1 | `19.33%` | `-28.53%` | `0.5882` | `27.64%` | `-16.43%` | `1.0778` |

## Interpretation

This does not invalidate the dominant-theme direction. It invalidates the naive implementation.

The current monthly theme score is too tactical for a one-theme engine. It frequently lets short-term spikes in precious metals, energy, or high-beta proxies steal the mainline from the broader market leadership. That behavior is acceptable in a multi-theme sleeve, but too noisy when it becomes the sole V6-B attack sleeve.

The correct architecture is still:

- `Theme Radar`: detect candidates for the next market mainline.
- `Dominant Theme State`: maintain one primary mainline across months/quarters.
- `Transition Logic`: move from observe to starter sleeve to full B sleeve only after confirmation.
- `Fallback`: if no mainline is confirmed, revert to current V2-style AI/tech strength or defensive mode.

## Decision

Do not promote dominant-theme v0.

Keep active paper simulation on `V6AB_SIM_CANDIDATE_V2_DYNAMIC_B_SIZING`.

Use this result to redefine V6-V3: not "top monthly theme", but "confirmed market mainline with lifecycle state."

## Next Work

Build a real mainline state machine:

- classify each theme into `candidate`, `confirmed`, `aging`, `failed`;
- require multi-month leadership, breadth, and stock-level confirmation before full B sleeve allocation;
- prevent commodity/defensive spikes from becoming the primary attack theme unless they persist;
- keep the current V2 AI/infra expression as fallback while no superior mainline is confirmed.
