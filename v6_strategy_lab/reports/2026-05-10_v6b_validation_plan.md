# V6-B Validation Plan

- Date: 2026-05-10
- Status: active plan
- Purpose: keep V6-B honest by separating live-forward validation from historical synthetic validation.

## Core Problem

The current Radar pool contains names that are attractive *today*. That does not mean those same names would have been attractive in earlier years. Therefore, V6-B cannot be validated by mechanically dropping today’s Radar winners into past periods.

## Track A: Live-Forward

Use the current Radar universe from `2026-05-10` onward.

Plan:

1. Keep the current Radar universe point-in-time.
2. Run V6-B in simulation only.
3. Record weekly holdings, selection dates, weights, exits, drawdowns, and missed names.
4. After about one month of clean execution, consider a very small pilot.
5. Keep pilot size intentionally small so failure is cheap.

What this proves:

- Whether the system works on the current regime.
- Whether the engineering pipeline is stable.
- Whether the scorecard and allocator behave as intended.

## Track B: Synthetic Historical

Build historical Radar-like universes from contemporaneous data.

Plan:

1. For each month or quarter in history, reconstruct a Radar candidate pool from data available at that time.
2. Apply the same scoring and selection logic.
3. Compare the resulting V6-B sleeve to V6-A and to benchmarks.
4. Use the same no-lookahead rules as live-forward.

What this proves:

- Whether the Radar rules are structurally valid across past regimes.
- Whether the pool construction logic avoids overfitting to one era.
- Whether V6-B improves risk-adjusted return when used as a challenger.

## Hard Boundary

- Do not use current Radar winners as if they existed earlier.
- Do not merge live-forward and synthetic results into one number.
- Do not promote V6-B until both tracks are acceptable.

## Current Status

- Live-forward: ready to start in simulation.
- Synthetic historical: design complete, data-dependent.
- Live real-account pilot: only after simulation stability and explicit approval.
