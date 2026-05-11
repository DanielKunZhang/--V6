# V6-B Strategy Spec v1

- Date: 2026-05-10
- Status: research spec
- Purpose: Define V6-B before historical backtest becomes available.

## One-Sentence Definition

V6-B is a systematic right-tail momentum sleeve: Radar supplies a point-in-time opportunity pool, the scorecard ranks candidates, the engine selects top names during risk-on regimes, and the allocator decides whether the sleeve receives any capital.

## Workflow

1. Radar updates point-in-time universe.
2. `v6b_universe_audit.py` checks no-lookahead fields.
3. `v6b_score_universe.py` scores active candidates.
4. `v6b_build_universe_config.py` generates backtest-compatible universe variants.
5. `v6b_radar_momentum_challenger.py` runs standalone V6-B backtest after data is available.
6. V6-A vs V6-B comparison is generated.
7. `v6_allocator.py` decides whether V6-B weight remains 0% or receives 20% / 30% / 50% research allocation.

## Validation Tracks

V6-B has two validation tracks:

1. Live-forward validation
   - Current Radar names are only valid from their `entry_date` onward.
   - The 2026-05-10 pool starts from 2026-05-10.
   - First run in simulation.
   - If roughly one month has no engineering problems, a very small pilot can be discussed.

2. Synthetic historical validation
   - Historical tests must generate Radar-like pools from data available at each historical date.
   - Today’s selected names cannot be mechanically used in earlier years.
   - This is the only valid way to estimate long-term historical behavior of the rules.

These tracks must not be merged into a single performance number.

Current generated config:

- `v6_strategy_lab/configs/generated/v6b_generated_universe_20260510_seed.json`
- Variants: `v6a_base_only`, `v6b_eligible_only`, `v6b_watch_plus`, `v6b_full_active`
- Current probe report: `backtest_results/v6b_radar_momentum/v6b_report_generated_seed_probe.md`
- Boundary: current probe only validates the pipeline and missing-data reporting. It does not validate V6-B performance.

## Buy Eligibility

V6-B cannot buy unless all are true:

- V6-B standalone passes.
- V6-A comparison passes.
- Point-in-time audit passes.
- Allocator gives V6-B non-zero weight.
- Market regime is risk-on.
- Latest preview exists.
- Live tradability passes.

## Selection

- Candidate source: active point-in-time Radar universe.
- Score threshold: eligible research names start at `>= 75`.
- Default holding count: top 2-4 names.
- Max same track: 2 names.
- Exclude names with insufficient price history, liquidity, or event-risk block.

## Sizing

- Allocator controls total V6-B budget.
- V6-B internal target is 3 names.
- Single name max: 40% of V6-B sleeve.
- Single name max total-account exposure: 3%.
- Exposure can be reduced by volatility scaling and drawdown brake.

## Exit

- Score below 60: reduce or exit.
- Score below 50: hard exit.
- Anti-thesis trigger: exit.
- Risk-off regime: switch to defensive sleeve.
- Stale research over 45 days: block from new buys until refreshed.

## Optimization Plan

When historical data is available, optimize only within bounded, explainable ranges:

| Parameter | Range | Reason |
| --- | --- | --- |
| top_n | 2-4 | Preserve right-tail concentration without single-name dependency. |
| asset_mom | 20 / 60 / 120 days | Classic momentum horizons. |
| trend_ma | 80-150 days | Medium-term risk filter. |
| market_ma | 120-200 days | Broad-market regime filter. |
| max_exposure | 1.0 / 1.25 | Avoid leverage-first optimization. |
| score_threshold | 70 / 75 / 80 | Test whether tighter score improves quality. |

Rules:

- Do not optimize ticker membership directly.
- Do not backfill winners before their entry_date.
- Do not select parameters only by full-period return.
- Prefer OOS Sharpe, drawdown stability, rolling 3y/5y, and composite benefit vs V6-A.

## Current Boundary

This spec is ready for future backtest, not for trading. Current V6-B allocation remains 0% until evidence exists.
