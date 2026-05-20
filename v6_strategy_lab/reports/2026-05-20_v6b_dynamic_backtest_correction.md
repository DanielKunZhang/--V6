# 2026-05-20 V6-B Dynamic Backtest Correction

## Correction

The earlier V6-B challenger using the 2026-05-20 generated list as a static historical pool is not a valid V6-B effectiveness test.

Valid V6-B validation must generate the candidate pool at each historical decision point using only information available at that time, then trade forward from that point. Static list testing is only a risk check for whether the current list should be directly merged into V6-A.

## Dynamic Test Run

- Generator: `v6b_synthetic_historical_radar_generator.py`
- Challenger: `v6b_synthetic_historical_challenger.py`
- Snapshot frequency: monthly last trading day
- Test window: `2018-01-01` to `2026-05-19`
- Snapshot count: `101`
- Boundary: price-only synthetic historical reconstruction. This is no-lookahead and materially better than static-list testing, but it is still not equivalent to a full historical news / fundamentals Radar reconstruction.

## System Fix

The synthetic historical generator previously covered:

- `core_reacceleration`
- `bottleneck_diffusion`
- `turnaround_momentum`

It did not cover the current V6-B AI infrastructure optics / interconnect layer. This was a system gap because current Radar and Missing Opportunity Review identify `COHR`, `LITE`, and `AAOI` as important second/third-order diffusion names.

Fix applied:

- Added `optics_and_interconnect` to `v6b_synthetic_historical_generator_policy_v1.json`
- Included `US.COHR`, `US.LITE`, `US.AAOI`
- Added `v6b_optics_track` and `v6ab_optics_overlay`
- Changed blended challenger variants to use all dynamic tracks from the snapshot manifest rather than hard-coded track names
- Updated synthetic generator summary output to display all policy tracks dynamically

## Dynamic Results After Optics Fix

Best baseline:

- `v6a_base_only`, mom60 top3
- Annualized return: about `+25.0%`
- OOS annualized return: about `+38.7%`
- Max drawdown: about `-26.1%`
- Sharpe: about `0.84`
- OOS Sharpe: about `1.12`

Most relevant V6-B overlay results:

- `v6ab_optics_overlay`, mom60 top3: annualized about `+32.9%`, OOS about `+86.1%`, max drawdown about `-29.3%`, Sharpe about `0.85`, OOS Sharpe about `1.47`
- `v6ab_blended_overlay`, mom120 top3: annualized about `+41.2%`, OOS about `+98.5%`, max drawdown about `-32.5%`, Sharpe about `0.89`, OOS Sharpe about `1.41`

Pure dynamic V6-B tracks can show high OOS upside but have unacceptable historical drawdowns when run standalone. The improvement is more credible as a controlled overlay / sleeve, not as a replacement for V6-A.

## Decision

- Do not use the static-list challenger as evidence against V6-B.
- Treat the dynamic synthetic result as supportive but not final: V6-B has evidence as a small overlay, especially optics / interconnect, but needs tighter drawdown control before live allocation.
- Next V6-B work should focus on sleeve sizing, drawdown brake, and catalyst / valuation / overheat filters, not broad static universe expansion.

