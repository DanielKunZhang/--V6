# 2026-05-20 V6-A / V6-B Quota Refresh Execution Update

## Executive Status

- V6-A: OpenD historical K-line issue cleared. Policy now points to the `20260520_live_refreshed` deterministic replay artifacts.
- V6-A real guarded run: executed under the existing 5K automation boundary. First reconciliation shows all six orders are `WAITING_SUBMIT`, with zero filled quantity at the check time because orders are DAY/RTH.
- V6-B: Radar and Missing Opportunity Review were refreshed through 2026-05-19. AI compute / data-center remains the top theme and is in second-order diffusion.
- V6-B decision: do not ask for manual universe construction. Universe is determined from registry status, independent Radar discovery, Missing Opportunity Review, scorecard, and cache-only challenger results.

## V6-A Reconciliation Outcome

- First reconciliation tag: `v6a_20260520_refreshed_auto_recon1`
- Remaining pending orders: `6`
- Filled quantity: `0`
- Managed positions were not changed by reconciliation because no order had filled.
- Operational interpretation: this is expected while DAY/RTH orders wait for the regular session. Next action is to run reconciliation after RTH opens or after order status changes, not to resubmit.

## V6-B Universe Decision

Changes applied:

- `US.COHR`: promoted from `watch_add_candidate` to `active_research`.
- `US.AAOI`: upgraded from `observe_only` to `watch_add_candidate`, but remains external-sample tainted and high-volatility. No direct chase.
- `US.MRVL`: remains `watch_add_candidate`; cache is stale and chase risk is high.
- `US.NOK`: remains `observe_only`; used for external attribution, not active research.

Point-in-time rule:

- COHR active entry date is `2026-05-20`, based on 2026-05-19 data. This avoids backfilling today’s decision into the 2026-05-10 seed.

## V6-B Challenger Result

Minimal quota refresh:

- Added/refreshed only the watch-plus requirement: `US.COHR`, `US.WDC`, `US.INTC`, `US.AMKR`, `US.SMH`, `US.SOXX`.
- Did not fetch low-score `US.AMBA` / `US.CEVA` because they are not needed for the current high-priority decision.

Coverage after refresh:

- `v6a_base_only`: PASS
- `v6b_eligible_only`: PASS
- `v6b_watch_plus`: PASS
- `v6b_full_active`: missing low-score `US.AMBA`, `US.CEVA`

Result:

- Current V6-B direct expansion does not beat V6-A baseline.
- Best V6-A baseline sample: OOS annual return about `40.07%`, OOS max drawdown about `-22.80%`, OOS Sharpe about `1.33`.
- Best refreshed V6-B watch-plus sample: OOS annual return about `33.60%`, OOS max drawdown about `-39.59%`, OOS Sharpe about `0.89`.

Decision:

- V6-B allocation remains `0%` for live use.
- V6-B next stage is not broader universe expansion. It should become a filtered satellite research sleeve: Radar discovery -> valuation/catalyst/overheat filter -> small sleeve candidate -> allocator gate.
- V6-A remains the production automation baseline under the current 5K monitored setup.

