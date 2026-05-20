# V6 Attack Engine Deterministic Replay

- Generated: `2026-05-20T12:17:11`
- Purpose: convert robust ATK candidates from headline backtest metrics into replayable daily holdings and rebalance logs.
- Scope: baseline ATK logic only. Five-line overlays are excluded from this production candidate replay.

## Composite Check

| composite | full | OOS | recent | Sharpe full/OOS | max DD | min equity | 3y worst ann |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| ATTACK_EQUAL_REPLAY | 29.80% / -21.13% | 36.43% / -21.13% | 54.24% / -21.13% | 1.04 / 1.18 | -21.13% | 94.41% | 7.20% |

## Candidate Replay Summary

| candidate | status | full | OOS | recent | max DD | worst day | ann turnover | max gross | levered days | latest weights |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| ATK00059 | attack_candidate | 30.25% / -37.32% | 48.29% / -27.40% | 67.04% / -24.34% | -37.32% | -10.61% 2018-07-26 | 21.70x | 1.50 | 57.82% | {"US.AMZN": 0.3560325, "US.AVGO": 0.3560325, "US.GOOGL": 0.3560325} |
| ATK00161 | attack_candidate | 27.82% / -21.89% | 32.62% / -21.50% | 51.38% / -21.50% | -21.89% | -8.13% 2017-02-23 | 9.97x | 1.50 | 23.86% | {"CASH": 0.31019492, "US.GOOGL": 0.34490254, "US.NVDA": 0.34490254} |
| ATK00028 | attack_candidate | 29.58% / -28.83% | 29.80% / -24.12% | 63.90% / -24.12% | -28.83% | -9.09% 2024-07-17 | 30.36x | 1.25 | 51.55% | {"CASH": 0.2, "US.BIL": 0.35, "US.GLD": 0.45} |
| ATK00100 | attack_candidate | 25.37% / -25.16% | 36.46% / -25.16% | 44.79% / -25.16% | -25.16% | -9.97% 2018-07-26 | 23.72x | 1.50 | 54.93% | {"US.AVGO": 0.38698624, "US.GOOGL": 0.38698624, "US.NVDA": 0.38698624} |
| ATK00014 | attack_candidate | 30.51% / -29.77% | 28.82% / -29.77% | 48.03% / -29.77% | -29.77% | -9.13% 2024-07-17 | 28.80x | 1.50 | 45.87% | {"CASH": 0.1892993, "US.GOOGL": 0.40535035, "US.NVDA": 0.40535035} |
| ATK00074 | attack_candidate | 29.65% / -33.16% | 37.65% / -33.16% | 44.27% / -24.38% | -33.16% | -9.09% 2024-07-17 | 7.52x | 1.25 | 42.60% | {"CASH": 0.34572506, "US.GOOGL": 0.32713747, "US.NVDA": 0.32713747} |

## Files

- `attack_replay_daily_<tag>.csv`: daily equity, return, drawdown, exposure, and weights JSON.
- `attack_replay_rebalances_<tag>.csv`: every rebalance decision with reason, chosen assets, turnover, risk-on flags, and weights JSON.
- `attack_replay_summary_<tag>.csv`: candidate-level replay and live-feasibility summary.

## Interpretation

- This report verifies deterministic replay, not live readiness by itself.
- Next gate should convert target weights into order-level sizing under the real small-account cap, lot rules, buying power, and current holdings.
