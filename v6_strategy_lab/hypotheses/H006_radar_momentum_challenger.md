# H006: V6-B Radar Momentum Challenger

- Status: active-research
- Created: 2026-05-10
- Owner: Quant Agent / CIO review
- Config: `../configs/v6b_radar_universe_20260510.json`

## Hypothesis

Radar can act as a research-driven universe generator, while V6-B acts as the systematic execution layer.

The goal is not to replace V6-A immediately. The goal is to test whether adding a periodically refreshed Radar universe improves V6-A's ability to capture new AI/semi/data-center momentum without increasing drawdown, turnover, and overfitting risk.

## Why This Exists

V6-A currently captures AI mega momentum well, especially `NVDA / AVGO / AMZN / META / GOOGL / MSFT`.

It does not directly cover many Radar names:

- `AMD`
- `INTC`
- `ANET`
- `TSM`
- `WDC`
- `MU`
- `AMKR`
- `AMBA`
- `CEVA`
- `HIMX`

Radar should discover these names. V6-B should test whether the machine can select them better than manual small-position Radar execution.

## Research Design

V6-B compares four universe variants:

| Variant | Purpose |
| --- | --- |
| `v6a_base_only` | Baseline AI mega pool |
| `v6b_core_plus` | Adds first-order leader re-acceleration and semi ETFs |
| `v6b_radar_core` | Adds the most liquid Radar core names |
| `v6b_radar_full` | Adds full Radar universe including smaller satellites |

The engine should rank candidates by momentum and only hold top 2-4 names when market risk is on. Defensive assets remain `BIL / GLD / CASH`.

## Scoring System

Before market-data backtest is available, V6-B uses a research scorecard to rank Radar candidates. The scorecard is not a buy list.

Config and scripts:

- Policy: `../configs/v6b_entry_sizing_policy_v1.json`
- Manual seed scores: `../scorecards/v6b_score_overrides_20260510.csv`
- Runner: `../../v6b_score_universe.py`
- Latest seed report: `../scorecards/v6b_scorecard_20260510_seed.md`

Factors:

| Factor | Purpose |
| --- | --- |
| `theme_strength` | Whether the theme is a real multi-year force. |
| `fundamental_validation` | Whether revenue/order/customer/margin evidence has started to validate. |
| `expectation_revision` | Whether estimates and market expectations are still moving up. |
| `price_momentum` | Whether price action confirms institutional demand. |
| `liquidity_tradability` | Whether the name can be traded cleanly by the strategy. |
| `crowding_valuation_risk` | Whether the name is already too crowded or too valuation-stretched. |
| `anti_thesis_clarity` | Whether invalidation is clear enough to exit. |
| `portfolio_fit` | Whether it diversifies or improves the V6-A exposure. |

Thresholds:

- `>= 75`: `eligible_research`
- `60-75`: `watch`
- `50-60`: `research_only`
- `< 50`: `blocked`

Important boundary: final buying still requires V6-B standalone, V6-A comparison, allocator weight, risk-on regime, and live tradability.

## Required Proof

V6-B can only be promoted if it proves at least one of these:

- It beats V6-A on OOS return without worse drawdown or Sharpe.
- It is lower-correlated with V6-A and improves a composite V6-A + V6-B sleeve.
- It captures Radar names before or during major momentum moves without relying on one lucky ticker.

## Failure Conditions

V6-B fails if:

- OOS Sharpe is worse than V6-A.
- Max drawdown is more than 5 percentage points worse than V6-A.
- Incremental return mainly comes from one ticker or one short time window.
- The full Radar universe performs worse than `core_plus`, meaning satellites add noise.
- Required Radar tickers cannot be traded cleanly due to price, liquidity, or missing data.

## Operating Cadence

- Monthly: refresh Radar universe.
- Weekly: run V6-B preview once data is available.
- Quarterly: full replay, rolling 3y/5y, black swan windows, and live tradability.

## Validation Tracks

V6-B uses two separate validation tracks:

1. Live-forward track
   - Use the current Radar universe from `2026-05-10` onward.
   - Run it in simulation first.
   - After roughly one month of clean engineering behavior, consider a small pilot size.
   - This track is the only way to measure current Radar names honestly.

2. Synthetic historical track
   - Build historical Radar-like universes from contemporaneous data and signals.
   - Use that generator to test whether the Radar rules would have found good names in past regimes.
   - Do not use today’s selected tickers to backfill earlier years.

These tracks must remain separate in reports and decisions.

## Current Boundary

Research only. No live trading, no auto orders, no production replacement of V6-A.
