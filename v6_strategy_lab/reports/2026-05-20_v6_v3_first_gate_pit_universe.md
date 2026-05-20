# V6-V3 First Gate: Point-in-Time Universe

- Date: `2026-05-20`
- Baseline: `V6AB_SIM_CANDIDATE_V2_DYNAMIC_B_SIZING`
- Test artifact: `backtest_results/v6ab_sleeve_blend/v6ab_sleeve_blend_20260520_v6_v3_pit_first_pass.csv`
- Data policy: local cached prices only; no Futu historical quota used.

## What Changed

V6-B theme-to-stock expression now supports an optional point-in-time universe manifest.
This directly addresses the static-universe flaw: historical tests should not blindly use the current COHR/LITE/MU-style candidate set for earlier regimes.

The first implementation maps the `semis_ai` theme to the synthetic historical Radar tracks:

- `core_reacceleration`
- `bottleneck_diffusion`
- `optics_and_interconnect`
- `turnaround_momentum`

Manifest used:

`v6_strategy_lab/configs/synthetic_history/20260520_v3_dynamic_optics/manifest.json`

## Result

| candidate | ann | maxDD | Sharpe | verdict |
| --- | ---: | ---: | ---: | --- |
| V2 static theme-stock sleeve + dynamic B sizing | `31.8%` | `-15.7%` | `1.23` | remains baseline |
| PIT semis/AI sleeve + dynamic B sizing | `29.8%` | `-16.3%` | `1.19` | research input, not upgrade |

## Decision

This is not promoted to V6-V3 production or paper-sim replacement.

The PIT universe layer is a methodological improvement and should stay in the research engine, but the first PIT semis/AI manifest does not beat V2 after V6-A + overlay integration.

## Implications

- V2 remains the active V6AB paper-sim candidate.
- V3 should not be defined as a parameter tweak unless it passes V2 on return, drawdown, Sharpe, and stress-window behavior.
- The next real V3 work should improve alpha selection quality:
  - broaden point-in-time universe construction beyond AI infrastructure,
  - add cross-theme PIT candidates for healthcare, energy/resources, financials, industrials, utilities/power, and precious metals,
  - connect external inputs only when they change actual candidate pools, filters, sizing, or risk controls.

## Gate For Future V3

A V3 candidate must clear all of these before replacing the paper-sim version:

- Full-window Sharpe higher than V2 by at least `0.05`.
- Full-window max drawdown no worse than V2 by more than `1.0` percentage point.
- Annualized return not lower than V2 unless drawdown reduction is material.
- 2018Q4, 2020 COVID, 2022 hikes, and 2024-2026 subperiods reviewed explicitly.
- No broad historical-K quota sweep; use local cache first and fetch only targeted missing symbols.
