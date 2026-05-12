# V6-A Turnover / Cost Audit Spec

- Created: 2026-05-12
- Owner split: GPT defines metrics and acceptance criteria; Claude implements scripts and reports.
- Implementation status: spec only, no production code change.

## Purpose

Quantify whether V6-A `ATTACK_EQUAL_REPLAY` is practically tradable after turnover, commission, spread, slippage, and tax/friction assumptions.

This audit answers:

- How often does V6-A rebalance?
- How large is annual turnover?
- How much historical performance depends on ignoring real trading friction?
- What cost/slippage level would materially damage the strategy?
- Is V6-A suitable for small-account automation with the current notional cap?

## Inputs

Primary replay inputs:

```text
backtest_results/attack_engine_replay/attack_replay_rebalances_20260506_live_refreshed.csv
backtest_results/attack_engine_replay/attack_replay_daily_20260506_live_refreshed.csv
backtest_results/attack_engine_replay/attack_replay_composite_20260506_live_refreshed.csv
```

Required columns:

- `date`
- `candidate_id`
- `turnover`
- `transaction_cost`
- `equity_after_cost`
- `weights_json`
- `risk_on`
- `reason`
- `gross_exposure`
- `cash_weight`

Target candidate:

```text
candidate_id = ATTACK_EQUAL_REPLAY
```

If the replay files contain component candidates such as `ATK00014`, `ATK00028`, etc., the script must separate them from `ATTACK_EQUAL_REPLAY` and report them in a secondary section only.

## Required Metrics

### 1. Rebalance frequency

Report:

- total rebalance rows
- non-zero turnover rebalance rows
- average rebalance interval in calendar days
- median rebalance interval in calendar days
- max interval without rebalance
- number of rebalances per year

Definition:

```text
non_zero_rebalance = turnover > 0.0001
```

### 2. Turnover

Report:

- full-period annualized turnover
- OOS annualized turnover
- recent 2-year annualized turnover
- worst calendar-year turnover
- median calendar-year turnover
- top 10 largest single rebalance turnover events

Definition:

```text
annual_turnover = sum(turnover during period) / years_in_period
```

Interpretation:

- `turnover = 1.0` means 100% one-way portfolio turnover in the replay convention unless existing code defines otherwise.
- If replay convention differs, Claude must document the convention in the report before interpreting results.

### 3. Cost sensitivity

Stress test assumed round-trip/friction levels:

```text
0 bps
5 bps
10 bps
25 bps
50 bps
100 bps
```

For each cost level, estimate:

- annual return after cost
- full max drawdown after cost
- OOS annual return after cost
- OOS Sharpe after cost if daily returns are available
- terminal equity decay vs baseline

Expected calculation:

```text
extra_cost_return_on_rebalance_day = turnover * cost_bps / 10000
adjusted_daily_return = original_daily_return - extra_cost_return_on_rebalance_day
```

If only rebalance rows contain turnover, join rebalance turnover onto daily rows by `date`, defaulting missing turnover to 0.

### 4. Practical account-size check

For current pilot and future scale:

```text
pilot_notional_usd = 5_000
future_notional_usd = 25_000
future_notional_usd = 50_000
future_notional_usd = 100_000
```

Report estimated average and worst rebalance notional:

```text
rebalance_notional = turnover * strategy_notional
```

Also report minimum order feasibility risks:

- names with high share price causing rounding drift
- target weights that produce 0 shares at 5k
- recurring under-invested cash from integer share rounding

## Output Files

Claude should generate:

```text
backtest_results/v6a_turnover_cost_audit/v6a_turnover_cost_audit_<tag>.json
backtest_results/v6a_turnover_cost_audit/v6a_turnover_cost_audit_<tag>.csv
backtest_results/v6a_turnover_cost_audit/v6a_turnover_cost_audit_<tag>.md
```

Recommended script:

```text
v6a_turnover_cost_audit.py
```

Suggested command:

```bash
python3 v6a_turnover_cost_audit.py --tag 20260512_initial
```

## Report Structure

The markdown report must include:

1. Executive conclusion: `PASS / WATCH / FAIL`
2. Turnover summary table
3. Cost sensitivity table
4. Worst turnover events
5. Small-account feasibility section
6. Automation implication
7. Data caveats

## Acceptance Criteria

PASS:

- OOS annual return remains above 25% after 25 bps assumed cost.
- OOS max drawdown does not worsen by more than 3 percentage points under 25 bps.
- Annualized turnover is explainable and not extreme relative to weekly/monthly momentum systems.
- 5k pilot has no systematic target positions rounded to zero for core names.

WATCH:

- OOS annual return remains above 18% but below 25% after 25 bps.
- Rounding drift at 5k is material but acceptable at 25k+.
- Worst-year turnover is high but occurs in understandable regime transitions.

FAIL:

- OOS annual return falls below 18% after 25 bps.
- Max drawdown worsens materially due to turnover cost.
- Strategy relies on frequent high-turnover switching that is unlikely to survive real execution.

## Boundaries

- Do not change V6-A engine rules.
- Do not consume Futu historical K-line quota.
- Do not use current live account holdings for historical turnover.
- Do not include V6-B candidates in the main result.
- Do not treat this audit as permission to enable automated trading.

## Claude Deliverable

Claude should implement the script, run it once, and return:

- generated report paths
- `PASS / WATCH / FAIL`
- one-paragraph interpretation
- any code or data caveats
