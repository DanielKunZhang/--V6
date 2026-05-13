# V6-B Profile Search Attribution v1

- Date: `2026-05-13`
- Sample: `2018-01-01 ~ 2025-12-31`
- Manifest: `v6_strategy_lab/configs/synthetic_history/20260513_v1c_2025e/manifest.json`
- Baseline reference: `V6-A baseline = AnnR +26.2% / MaxDD -26.1% / Sharpe 0.88`

## Why This Report Exists

The first track-aware profile search showed several `V6-B overlay` candidates beating the current baseline. That result was directionally useful, but not sufficient.

The missing control was:

- `same-parameter V6-A base-only`

Without that control, we cannot tell whether the improvement came from:

- better parameters for the existing V6-A pool, or
- real incremental value from the dynamic track itself.

This report corrects that.

## Method Correction

For every profile-search row, we now compare the overlay result against two references:

1. `current V6-A baseline`
2. `same-parameter V6-A base-only control`

Interpretation rule:

- `vs baseline` answers whether the candidate is better than today's production-style reference.
- `track increment` answers whether the dynamic track adds real value beyond parameter changes alone.

## Track Coverage Context

Synthetic historical snapshot coverage matters because sparse tracks can look cleaner than they really are.

| track | non-empty snapshots | avg names / snapshot | max names |
| --- | ---: | ---: | ---: |
| `core_reacceleration` | 69 / 96 | 1.30 | 3 |
| `bottleneck_diffusion` | 52 / 96 | 1.01 | 3 |
| `turnaround_momentum` | 23 / 96 | 0.24 | 1 |

## Corrected Results

| track | best config | full result | vs baseline | vs same-param base-only | decision |
| --- | --- | --- | --- | --- | --- |
| `core_reaccel` | `mom60 top2 trend120 mkt180 dd10 rebal10` | `AnnR +36.8% / MaxDD -29.0% / Sharpe 1.04` | `+10.6 ann / +0.16 sh / +2.9 dd` | `+5.3 ann / +0.08 sh / -1.7 dd` | real track alpha; promote |
| `bottleneck` | `mom60 top3 trend150 mkt200 dd10 rebal10` | `AnnR +34.4% / MaxDD -28.8% / Sharpe 0.97` | `+8.2 ann / +0.09 sh / +2.8 dd` | `+0.4 ann / -0.13 sh / +6.5 dd` | false positive after control; freeze |
| `turnaround` | `mom60 top2 trend150 mkt200 dd08 rebal10` | `AnnR +35.9% / MaxDD -24.5% / Sharpe 1.07` | `+9.7 ann / +0.19 sh / -1.5 dd` | `+1.3 ann / +0.03 sh / +0.0 dd` | modest real alpha; secondary challenger |

Notes:

- `core_reaccel` is the only track where the dynamic overlay still looks clearly valuable after controlling for parameter changes.
- `turnaround` still adds value after control, but the effect is much smaller and the track is sparse. This is not yet a production-grade sleeve.
- `bottleneck` fails the attribution test. Its apparent improvement versus baseline mostly came from better engine parameters, not from the bottleneck names themselves.

## Critical Attribution Example

The clearest warning sign came from `bottleneck_diffusion`.

- `base-only` with bottleneck-style parameters:
  - `AnnR +34.0% / MaxDD -22.3% / Sharpe 1.11`
- `bottleneck overlay` with the same parameters:
  - `AnnR +34.4% / MaxDD -28.8% / Sharpe 0.97`

This means the dynamic bottleneck names added:

- only a tiny return increment,
- while making drawdown materially worse,
- and reducing Sharpe.

That is not allocator-worthy.

## What Changed Strategically

The first clean synthetic historical run said:

- `current V6-B standalone is not good enough`

This attribution-corrected run adds a more precise conclusion:

- `some track-aware overlays are useful`
- but `not all apparent overlay wins are true V6-B wins`

The practical ranking is now:

1. `V6-A baseline` remains the anchor.
2. `core_reaccel overlay` is the first serious V6-B challenger.
3. `turnaround overlay` is a low-confidence secondary challenger.
4. `bottleneck overlay` should stay research-only and frozen for allocator purposes.

## Immediate Next Actions

1. Promote `core_reaccel overlay` to formal challenger review.
2. Keep `turnaround` as secondary research, but do not allocate capital to it.
3. Freeze `bottleneck` until universe quality or exit logic improves.
4. Start a separate `V6-A parameter challenger` workstream, because same-parameter base-only controls showed that part of the uplift comes from engine profile changes even without V6-B names.

## Source Outputs

- `backtest_results/v6b_profile_search/core_reaccel_profile_20260513_core_v2.md`
- `backtest_results/v6b_profile_search/bottleneck_diffusion_profile_20260513_bottle_v2.md`
- `backtest_results/v6b_profile_search/turnaround_momentum_profile_20260513_turn_v2.md`
