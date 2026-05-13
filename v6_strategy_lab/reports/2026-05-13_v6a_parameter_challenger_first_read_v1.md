# V6-A Parameter Challenger First Read v1

- Date: `2026-05-13`
- Search policy: `v6_strategy_lab/configs/v6a_parameter_challenger_v1.json`
- Sample: `2018-01-01 ~ 2025-12-31`
- Output: `backtest_results/v6a_parameter_challenger/v6a_parameter_challenger_20260513_v1.{csv,md}`

## One-Line Conclusion

`V6-A baseline` 很可能不是当前最优 anchor。

第一轮 bounded search 显示，`base-only` 就存在一批明显优于当前 baseline 的参数候选，而且其中有几组提升并不只是“赌更猛”，而是同时改善了 `Sharpe`、`OOS Sharpe`，甚至改善了 `MaxDD`。

## Current Baseline

- Params: `mom60 top3 trend100 mkt150 dd10 rebal5`
- Metrics: `AnnR +26.2% / MaxDD -26.1% / Sharpe 0.88 / OOS Sharpe 1.28`

## Search Size

- Grid size: `432` combinations
- Gate distribution:
  - `promising_core_upgrade`: `124`
  - `full_sample_upgrade`: `96`
  - `safer_but_not_faster`: `24`
  - `return_plus_candidate`: `8`
  - `not_ready`: `180`

This is a strong signal that the current baseline is not sitting on a tiny fragile local optimum.

## Three Important Reads

## 1. Best Raw Return Upgrade

- Config: `mom120 top2 trend150 mkt200 rebal10`
- Result: `AnnR +37.5% / MaxDD -26.3% / Sharpe 1.09 / OOS Sharpe 1.35`
- Relative to baseline:
  - `Ann +11.3%`
  - `Sharpe +0.21`
  - `MaxDD` only `0.3%` worse
  - `OOS ann +14.3%`
  - `OOS Sharpe +0.07`

Interpretation:

- This is the strongest raw challenger.
- But it is also more concentrated (`top2`) and slower (`mom120`), so it should not be promoted on headline performance alone.

## 2. Best Balanced Quality Upgrade

- Config: `mom60 top3 trend150 mkt200 rebal10`
- Result: `AnnR +34.0% / MaxDD -22.3% / Sharpe 1.11 / OOS Sharpe 1.52`
- Relative to baseline:
  - `Ann +7.8%`
  - `Sharpe +0.23`
  - `MaxDD` improved by `3.7%`
  - `OOS ann +12.6%`
  - `OOS Sharpe +0.24`

Interpretation:

- This is probably the most interesting candidate right now.
- It keeps `top3` diversification, materially improves `Sharpe`, and actually improves `MaxDD`.
- If we care about `V6 = relatively safer annual return enhancer`, this profile currently looks more on-message than the highest-return `top2` version.

## 3. Directional Structural Signal

Across the top rows, three patterns repeat:

1. `rebal10` dominates `rebal5`
2. `trend150` dominates `trend100`
3. `market200` / `180` often beats `150`

Interpretation:

- The current baseline likely reacts too quickly.
- A slower trend filter plus slower rebalance appears to fit the `V6-A core pool` better on the clean sample.

## Important Caveat

`dd_stop` barely changes the top rows.

That usually means one of two things:

1. the stop is not binding often in the strongest candidate regimes, or
2. drawdown control is being driven more by market trend gating than by the local `dd_stop` value.

So we should not over-interpret `dd08 vs dd10 vs dd12 vs dd15` from this run.

## Practical Ranking

Current shortlist for formal follow-up:

1. `mom60 top3 trend150 mkt200 rebal10`
   - best balanced core-upgrade read
2. `mom120 top2 trend150 mkt200 rebal10`
   - strongest raw performance challenger
3. `mom120 top3 trend150 mkt200 rebal10`
   - middle ground between concentration and return

## What This Changes

Before this run, the working assumption was:

- `V6-A baseline` is the anchor, and maybe V6-B is where most future improvement comes from

After this run, the more accurate framing is:

- `V6-A baseline` remains the production anchor for now
- but `V6-A parameter challenger` is now a real parallel upgrade path
- and it may produce earlier, cleaner gains than V6-B allocator work

## Next Required Checks

No parameter should be promoted yet.

Before any promotion discussion, these three checks are mandatory:

1. `turnover / cost re-audit`
   - especially `rebal10` candidates versus current live execution assumptions

2. `parameter neighbor robustness`
   - confirm the winners are not isolated sharp peaks

3. `baseline vs challenger formal board`
   - compare current baseline and shortlisted challengers side by side using one consistent review card

## Decision

Current decision:

- `Do not change production baseline yet`
- `Promote V6-A parameter challenger to active formal research`
- `Use the balanced candidate as the first comparison anchor`
