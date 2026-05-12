# V6-A Pilot Review Dashboard Spec

- Created: 2026-05-12
- Owner split: GPT defines fields and review criteria; Claude implements aggregation and report generation.
- Pilot review date: 2026-05-26
- Implementation status: spec only, no production code change.

## Purpose

Create an evidence pack for the 2-week V6-A real pilot review.

The review must decide whether V6-A remains:

```text
CONTINUE_MANUAL_PILOT
PAUSE
PROMOTE_TO_SMALL_AUTO_PILOT
```

This dashboard is not a trading system. It is a review artifact.

## Scope

Pilot account:

```text
Futu real account: 281756481449956811
V6-A state file: backtest_results/v6a_state/v6a_managed_positions_real_281756481449956811.json
```

Managed symbols at pilot start:

```text
US.AMZN
US.AVGO
US.BIL
US.GLD
US.GOOGL
```

Pilot start:

```text
2026-05-11
```

Pilot review:

```text
2026-05-26
```

## Inputs

Primary artifacts:

```text
backtest_results/v6a_state/v6a_managed_positions_real_281756481449956811.json
backtest_results/v6a_reconciliation/*.json
backtest_results/v6a_guarded_runner/runs/*.json
backtest_results/attack_engine_real_pilot_executor/*.json
backtest_results/v6_reporting/runs/v6_report_daily_*.json
backtest_results/v6_daily_report_runner/*.json
```

Optional inputs:

```text
backtest_results/attack_engine_live_preview/*.csv
backtest_results/attack_engine_live_preview/*.json
morning_brief outputs if available
```

The dashboard must only evaluate V6-A managed positions. It must not infer V6 performance from full account holdings.

## Daily Rows

Create one row per calendar day during the pilot.

Required columns:

- `date`
- `runner_status`
- `reconciliation_status`
- `daily_report_status`
- `email_sent`
- `managed_positions_json`
- `pending_order_count`
- `target_symbols`
- `managed_symbols`
- `preview_buy_notional`
- `preview_sell_notional`
- `executable_order_count`
- `blockers`
- `decision`
- `notes`

## Execution Quality Metrics

Report:

- total submitted orders
- filled orders
- cancelled / failed orders
- orders still pending after reconciliation
- average time from submission to final status if timestamps are available
- average and worst slippage vs preview limit price
- integer rounding drift
- unmanaged sell attempts, expected always 0
- account or quote warning count
- OpenD / dependency failures
- missed daily report count

Slippage definition:

```text
buy_slippage_pct = (dealt_avg_price - preview_limit_price) / preview_limit_price
sell_slippage_pct = (preview_limit_price - dealt_avg_price) / preview_limit_price
```

If preview price cannot be joined reliably, report `slippage_unavailable` and list missing fields.

## Performance Metrics

Use managed positions only.

Report:

- start cost basis
- latest market value
- unrealized P/L
- unrealized P/L %
- worst observed unrealized P/L during pilot if daily prices exist
- contribution by ticker

If latest market prices are not available in local artifacts, the script may use the latest Futu account snapshot command, but must write the query time and source.

## Target vs Actual

For each day:

- parse latest V6-A plan-only preview
- compare `target_qty` vs `managed state qty`
- report drift by ticker
- identify whether drift is expected due to integer rounding or a true execution issue

Expected states:

```text
MATCHED
ROUNDING_DRIFT
PENDING_ORDERS
MISMATCH_BLOCKED
DATA_UNAVAILABLE
```

## Output Files

Claude should generate:

```text
backtest_results/v6a_pilot_review/v6a_pilot_review_<tag>.json
backtest_results/v6a_pilot_review/v6a_pilot_review_daily_<tag>.csv
backtest_results/v6a_pilot_review/v6a_pilot_review_<tag>.md
backtest_results/v6a_pilot_review/v6a_pilot_review_<tag>.html
```

Recommended script:

```text
v6a_pilot_review_dashboard.py
```

Suggested command:

```bash
python3 v6a_pilot_review_dashboard.py --tag 20260526_review
```

## Report Structure

The markdown/html report must include:

1. Review decision: `CONTINUE / PAUSE / PROMOTE_CANDIDATE`
2. Pilot timeline table
3. Managed state summary
4. Orders and reconciliation summary
5. Target vs actual drift table
6. Slippage and cost table
7. P/L by ticker
8. Operational incidents
9. Recommendation for next phase

## Promotion Criteria

Eligible for `PROMOTE_TO_SMALL_AUTO_PILOT` only if all are true:

- no unmanaged sell attempt
- no failed reconciliation unresolved at review time
- no pending order older than 1 trading day
- daily report runner succeeds at least 8 of 10 trading days, or all failures are explained and fixed
- no account/quote warning that would have caused a wrong order
- actual managed state matches target or drift is explained by integer rounding
- user has reviewed the turnover/cost audit
- automation preflight gate spec is implemented and tested

PAUSE if any are true:

- unmanaged sell attempt
- repeated dependency failure
- state mismatch not explained by rounding
- order remains pending without human resolution
- managed state file corrupt or strategy mismatch

## Boundaries

- Do not execute trades.
- Do not mutate managed state.
- Do not use total Futu account P/L as V6 P/L.
- Do not promote automation solely because P/L is positive.
- Do not pause solely because P/L is negative if execution quality is sound.

## Claude Deliverable

Claude should implement the dashboard generator, run it once immediately for a partial pilot report, and schedule/prepare it for the 2026-05-26 review.
