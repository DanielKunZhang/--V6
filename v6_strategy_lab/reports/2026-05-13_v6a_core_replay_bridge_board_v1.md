# V6-A Core Replay Bridge Board v1

- Date: `2026-05-13`
- Scope: bridge the `V6-A core baseline / balanced challenger` research lane into runner-compatible replay artifacts
- Boundary: this does **not** modify the current live `V6-A ATTACK_EQUAL_REPLAY` manual pilot

## One-Line Decision

`Balanced challenger wins the replay bridge board too.`

That matters because this is no longer only a clean research-engine result. It now survives one more step closer to production artifacts.

## Why This Board Exists

There was a structural mismatch:

- current live sleeve = legacy `V6-A ATTACK_EQUAL_REPLAY`
- current upgrade candidate = `V6-A core engine` parameter challenger

Treating them as the same thing would blur:

1. `execution-quality validation`
2. `baseline replacement research`

So this bridge was required before any production-promotion discussion.

## Inputs

- Script: `python3 v6a_core_deterministic_replay.py --config v6_strategy_lab/configs/v6a_core_replay_bridge_v1.json --tag 20260513_bridge_v1`
- Config: `v6_strategy_lab/configs/v6a_core_replay_bridge_v1.json`
- Main artifacts:
  - `backtest_results/v6a_core_replay/v6a_core_replay_summary_20260513_bridge_v1.csv`
  - `backtest_results/v6a_core_replay/v6a_core_replay_manifest_20260513_bridge_v1.json`

## Evidence Board

| dimension | baseline | balanced challenger | verdict |
| --- | --- | --- | --- |
| Full ann | `+26.18%` | `+33.97%` | challenger |
| Full maxDD | `-26.06%` | `-22.34%` | challenger |
| Full Sharpe | `0.88` | `1.11` | challenger |
| OOS ann | `+36.78%` | `+44.18%` | challenger |
| OOS Sharpe | `1.13` | `1.30` | challenger |
| Recent ann | `+47.08%` | `+59.66%` | challenger |
| Recent maxDD | `-24.64%` | `-18.16%` | challenger |
| Annual turnover | `9.01x` | `5.25x` | challenger |
| Rebalances / year | `50.38` | `25.19` | challenger |
| Latest holdings | `AMZN / AVGO / GOOGL` | `AMZN / AVGO / NVDA` | diagnostic |

## Release-Style Read

Using the current numeric gate style:

- `balanced challenger` passes the key metric thresholds:
  - `full_ann_ret +33.97%`
  - `oos_ann_ret +44.18%`
  - `full_max_dd -22.34%`
  - `oos_sharpe 1.30`
  - `min_equity_pct 87.06%`
  - `rolling_3y_worst_ann +0.78%`
- baseline still misses the rolling durability read:
  - `rolling_3y_worst_ann = -4.73%`

But neither profile should be called `preview-ready` yet, because the bridge replay currently reaches only `2026-05-05`. Relative to `2026-05-13`, signal freshness is still stale.

## What This Changes

Two things are now clearer:

1. For near-term production-path advancement, `balanced challenger` is stronger than current `V6-B`
2. `V6-A core upgrade lane` must be managed separately from the current live ATTACK pilot

So the right interpretation is:

- keep the current ATTACK manual pilot stable
- keep V6-B strategically important, but not first in the production queue
- move the balanced V6-A challenger into `runner wiring / dry-run preview`

## Board Decision

1. `Do not touch the current live ATTACK pilot`
2. `Promote balanced challenger to single-candidate runner wiring candidate`
3. `Do not promote baseline replacement directly from this board`

## Immediate Next Step

The next concrete step is not another parameter search.

It is:

`wire the single-candidate balanced artifacts into a guarded-runner dry-run / preview path once fresh replay rows are available`

