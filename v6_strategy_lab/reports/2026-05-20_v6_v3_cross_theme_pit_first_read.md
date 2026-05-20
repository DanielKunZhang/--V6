# V6-V3 Cross-Theme PIT First Read

- Date: `2026-05-20`
- Baseline: `V6AB_SIM_CANDIDATE_V2_DYNAMIC_B_SIZING`
- New generator: `v6b_cross_theme_pit_generator.py`
- New manifest: `v6_strategy_lab/configs/synthetic_history/20260520_v4_cross_theme_pit/manifest.json`
- Backtest artifacts:
  - `backtest_results/v6ab_sleeve_blend/v6ab_sleeve_blend_20260520_v6_v3_cross_theme_pit_first_pass.csv`
  - `backtest_results/v6ab_sleeve_blend/v6ab_sleeve_blend_20260520_v6_v3_hybrid_gap_pit_first_pass.csv`
- Data policy: local cached prices only; no Futu historical quota used.

## What Was Tested

The first PIT test only covered the AI infrastructure candidate pool. This test expands the idea to multiple themes:

- semis / AI compute
- technology / software / internet
- healthcare / biotech
- energy / commodities
- precious metals
- financials
- industrials / infrastructure
- utilities / power
- consumer discretionary

Two variants were tested:

1. `v6b_cross_pit_guarded_top3_90`
   - Replace theme-stock expression with cross-theme PIT pools wherever a theme has PIT candidates.
2. `v6b_hybrid_gap_pit_guarded_top3_90`
   - Keep V2 static AI/technology high-conviction pools.
   - Use cross-theme PIT only to fill sparse or empty theme gaps: healthcare, energy, precious metals, financials, industrials, utilities.

## Result

| candidate | ann | maxDD | Sharpe | verdict |
| --- | ---: | ---: | ---: | --- |
| V2 static theme-stock sleeve + dynamic B sizing | `31.8%` | `-15.7%` | `1.23` | remains baseline |
| AI-only PIT + dynamic B sizing | `29.8%` | `-16.3%` | `1.19` | useful but not upgrade |
| full cross-theme PIT + dynamic B sizing | `28.0%` | `-16.2%` | `1.12` | not upgrade |
| hybrid gap-fill PIT + dynamic B sizing | `29.9%` | `-16.0%` | `1.17` | better direction, still not upgrade |

## Interpretation

The direction is confirmed but not yet good enough.

Full cross-theme PIT underperformed because the current cross-theme watch universe contains many ETF/proxy entries. That makes the B sleeve more diversified and more realistic across regimes, but it dilutes the high-alpha convexity that made V6-B useful.

The hybrid gap-fill version performed better than full cross-theme PIT, which supports the architecture:

- keep the strong V2 AI/technology alpha pool where it is already effective,
- use PIT reconstruction to cover theme blind spots,
- do not replace proven high-alpha pools with broad proxies unless the replacement has better expected convexity.

## Decision

Do not promote either cross-theme PIT candidate to paper sim.

V2 remains the active V6AB paper-sim version.

Keep the new generator and manifests as research infrastructure. The next V3 attempt should improve candidate quality, not overlay parameters.

## Next V3 Work

The next useful upgrade is a stronger cross-theme candidate universe:

- replace ETF-only theme expressions with actual high-beta / high-quality stocks where available,
- add targeted energy, healthcare, financial, industrial, utilities/power, and precious-metal equity candidates,
- rank candidates with both price momentum and real alpha inputs such as X Radar, 13F learning, earnings revision, and Seeking Alpha evidence,
- keep every external input tied to executable effects: candidate inclusion, exclusion, sizing, or risk controls.

Future V3 promotion still requires beating V2 on full-window Sharpe, drawdown, annualized return, and stress windows.
