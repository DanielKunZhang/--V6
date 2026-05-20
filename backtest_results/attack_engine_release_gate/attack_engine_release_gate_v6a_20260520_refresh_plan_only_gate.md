# V6 Release Gate

- Generated: `2026-05-20T12:18:05`
- Strategy: `V6-A ATTACK_EQUAL_REPLAY`
- Gate result: `PASS`
- As-of date: `2026-05-20`

## Summary

| metric | value |
| --- | ---: |
| full_ann_ret | 29.8 |
| oos_ann_ret | 36.43 |
| full_max_dd | -21.13 |
| oos_sharpe | 1.18 |
| min_equity_pct | 94.41 |
| rolling_3y_worst_ann | 7.2 |
| latest_signal_date | 2026-05-19 |

## Checks

| check | result | severity | detail |
| --- | --- | --- | --- |
| replay_composite_exists | PASS | info | backtest_results/attack_engine_replay/attack_replay_composite_20260520_live_refreshed.csv |
| full_ann_gate | PASS | blocker | 29.80% >= 25.00% |
| oos_ann_gate | PASS | blocker | 36.43% >= 18.00% |
| drawdown_gate | PASS | blocker | -21.13% >= -30.00% |
| oos_sharpe_gate | PASS | blocker | 1.18 >= 0.80 |
| min_equity_gate | PASS | blocker | 94.41% >= 70.00% |
| rolling_3y_gate | PASS | blocker | 7.20% >= 0.00% |
| signal_freshness_gate | PASS | blocker | signal_date=2026-05-19, asof=2026-05-20, age_days=1, max=7 |
| live_preview_orders_exist | PASS | blocker | backtest_results/attack_engine_live_preview/attack_live_order_preview_orders_v6a_20260520_refresh_plan_only_preview.csv |
| live_preview_has_executable_orders | PASS | info | buy_notional=1496.08, executable_notional=3371.28 |
| order_value_gate | PASS | blocker | bad_order_value_lines=0 |
| live_quotes_gate | PASS | blocker | warnings=[] |
| live_quotes_complete_gate | PASS | blocker | quote_count=6 |
| live_account_gate | PASS | blocker | warnings=[] |

## Decision

- V6-A is eligible for small-capital live launch preview. Manual approval is still required before placing orders.
