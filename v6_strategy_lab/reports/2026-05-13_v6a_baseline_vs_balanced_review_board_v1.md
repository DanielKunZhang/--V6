# V6-A Baseline vs Balanced Challenger Review Board v1

- Date: `2026-05-13`
- Scope: pre-production comparison between current `V6-A baseline` and the preferred `balanced V6-A challenger`

## One-Line Decision

`Balanced challenger wins the pre-production research board.`

But:

- it does **not** replace the live baseline immediately;
- it should advance to `implementation / replay / preview` queue first.

## Candidates

## Current Baseline

- Label: `v6a_core_baseline`
- Params: `mom60 top3 trend100 mkt150 dd10 rebal5`

## Balanced Challenger

- Label: `mom60 top3 trend150 mkt200 dd10 rebal10`
- Why this one:
  - keeps `top3` diversification
  - improves `Sharpe`
  - improves `MaxDD`
  - survives turnover/cost re-audit
  - passes first local robustness check

## Evidence Board

| dimension | baseline | balanced challenger | verdict |
| --- | --- | --- | --- |
| Full return | `+26.2%` | `+34.0%` | challenger |
| Full maxDD | `-26.1%` | `-22.3%` | challenger |
| Full Sharpe | `0.88` | `1.11` | challenger |
| OOS ann | `+47.1%` | `+59.7%` | challenger |
| OOS Sharpe | `1.28` | `1.52` | challenger |
| 25bps full ann | `+23.5%` | `+32.4%` | challenger |
| 25bps OOS Sharpe | `1.20` | `1.47` | challenger |
| Annual turnover | `8.88` | `5.00` | challenger |
| Rebalances / year | `17.0` | `10.6` | challenger |
| Robustness | production anchor | `stable_neighbor_cluster` | challenger passes |

## What This Means

The most important result is not just that the challenger is faster.

It is better on the things that matter for your stated objective:

- higher annual return
- higher Sharpe
- lower drawdown
- lower annual turnover
- lower rebalance frequency
- still stronger after cost assumptions

So this is not a “take more risk to chase more return” candidate.

It currently looks like a better expression of:

- `V6 = relatively safer annual return enhancer`

## Why It Still Does Not Replace Production Immediately

Three reasons:

1. `research engine != production engine`
   - current challenger evidence comes from the clean synthetic/base-only research framework
   - it is not yet an implemented production replay inside the live V6-A execution stack

2. `execution path still needs parity`
   - the live sleeve currently runs the existing baseline logic
   - challenger needs deterministic replay / preview / release-gate style evidence inside the same operational path

3. `pilot phase priority remains execution quality`
   - current live sleeve is still in manual pilot
   - we should not mix “execution validation” and “baseline replacement” into one rushed step

## Board Decision

Current board decision:

1. `Keep current baseline live`
2. `Promote balanced challenger to formal implementation queue`
3. `Do not spend more primary attention on raw-best top2 candidate yet`

## New Priority Order

For V6-A specifically:

1. `execution-quality evidence`
2. `balanced challenger implementation / replay / preview`
3. `only after that, discuss baseline promotion`

## Required Next Steps

1. Implement the balanced challenger inside the real `V6-A` replay stack
2. Run deterministic replay with the same evidence standards as the baseline
3. Produce a side-by-side preview / release style board
4. Only then decide whether to replace the production baseline
