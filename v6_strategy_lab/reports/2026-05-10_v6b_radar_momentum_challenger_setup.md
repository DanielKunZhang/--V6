# 2026-05-10 V6-B Radar Momentum Challenger Setup

- Status: research-scaffold-ready
- Related Hypothesis: `../hypotheses/H006_radar_momentum_challenger.md`
- Config: `../configs/v6b_radar_universe_20260510.json`
- Script: `/Users/zhangkun/WorkBuddy/程序化/量化程序/v6b_radar_momentum_challenger.py`
- Smoke Report: `/Users/zhangkun/WorkBuddy/程序化/量化程序/backtest_results/v6b_radar_momentum/v6b_report_smoke_cache_20260510.md`

## What Was Built

V6-B is now a formal research challenger:

- Radar maintains the universe.
- V6-B consumes the approved Radar JSON universe.
- The backtest script compares V6-A base pool vs Radar-expanded pools.
- The first smoke run uses `--cache-only` to avoid accidental Futu calls.

## Current Universe Variants

| Variant | Purpose |
| --- | --- |
| `v6a_base_only` | Original AI mega baseline |
| `v6b_core_plus` | Adds first-order re-acceleration names and semi ETFs |
| `v6b_radar_core` | Adds liquid Radar core names |
| `v6b_radar_full` | Adds full Radar universe including satellites |

## Smoke Test Result

Command:

```bash
python3 v6b_radar_momentum_challenger.py --tag smoke_cache_20260510 --cache-only
```

Result:

- Script ran successfully.
- `v6a_base_only` ran and produced baseline results.
- Radar-expanded variants were blocked by missing price cache.

Best cache-only baseline result:

| Variant | Candidate | Full | OOS | Recent | Max DD | OOS Sharpe |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `v6a_base_only` | `V6B0009` | `31.03%` | `40.07%` | `48.08%` | `-22.80%` | `1.33` |

This confirms the engine is usable, but not yet able to evaluate Radar incremental value.

## Data Coverage Blocker

Missing Radar price cache:

```text
US.AMD
US.ANET
US.TSM
US.MU
US.WDC
US.INTC
US.AMKR
US.LITE
US.SITM
US.ETN
US.VRT
US.GEV
US.AMBA
US.SYNA
US.CEVA
US.HIMX
```

This is the next blocker. Without clean historical data, we cannot claim Radar improves V6.

## 2026-05-10 Data Source Update

Futu OpenAPI was checked after the user re-login:

- OpenD listens on `127.0.0.1:11111`.
- User historical K-line quota is `999/1000`, so Futu cannot be used for bulk Radar history today.
- Python SDK import works if `HOME=/private/tmp/futu_v6b_home` is used to avoid local log permission problems.
- `OpenQuoteContext` still hangs during initialization, so live snapshot/history are not currently usable from this process.

External source checks:

- Stooq direct CSV now requires an API key/captcha.
- Yahoo direct chart endpoint returns `403`.
- Local `yfinance` is installed, but current requests are rate-limited.

Engineering mitigation added:

- `v6b_fetch_radar_price_cache.py`: Futu cache fetcher with per-ticker timeout and resumable cache behavior.
- `import_price_csv_to_cache.py`: generic external CSV importer into local `price_cache`.

Research policy:

- Historical research data may come from a non-Futu source.
- Before any simulation/live promotion, Futu data must be used for cross-check or live tradability validation once quota/API availability recovers.

## Interpretation

V6-B is not yet a strategy. It is a research framework.

Current truth:

- V6-A already has strong baseline performance.
- Radar may improve capture of AMD/INTC/WDC/ANET/TSM-type opportunities.
- But this is unproven until full price data is loaded and OOS/rolling/crisis tests are run.

## Next Steps

1. Populate price cache for all Radar tickers using either Futu after quota refresh or approved external CSV import.
2. Cross-check with Futu once historical K-line quota/API availability recovers.
3. Run full V6-B backtest.
4. Compare `v6b_core_plus`, `v6b_radar_core`, and `v6b_radar_full` against `v6a_base_only`.
5. Only if V6-B passes, move to deterministic replay and live preview.

## Operating Boundary

No live trading. No simulation allocation yet. No replacement of V6-A.
