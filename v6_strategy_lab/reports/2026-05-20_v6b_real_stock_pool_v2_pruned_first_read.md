# V6-B Real Stock Pool v2 Pruned First Read

- Date: `2026-05-20`
- Objective: improve the V6-V3 research candidate by pruning weak real-stock PIT candidates, without changing the V6AB overlay.
- Universe config: `v6_strategy_lab/configs/v6b_real_stock_theme_universe_v2.json`
- PIT manifest: `v6_strategy_lab/configs/synthetic_history/20260520_v6_real_stock_pit_pruned/manifest.json`
- Selection audit: `backtest_results/v6b_selection_quality/v6b_selection_quality_20260520_real_stock_pit_v1.md`
- Quick compare: `backtest_results/v6ab_candidate_quick_compare/v6ab_candidate_quick_compare_20260520_real_stock_pit_v2_pruned.csv`

## What Changed

This pass did not tune the V6AB overlay. It tightened the stock pool itself.

The v1 PIT audit showed that the useful V6-B expansion was concentrated in several high-convexity pairs:

- `semis_ai`: `LITE`, `MU`, `NVDA`, `VRT`, `TSM`, `AVGO`
- `technology`: `PLTR`, `APP`, `NET`, `NFLX`, `META`
- `utilities_power`: `GEV`, `VST`, `PWR`, `TLN`, `ETN`
- `precious_metals`: `SBSW`, `CDE`, `AEM`, `GOLD`
- `energy_resources`: `DVN`, `OXY`, `FANG`

The same audit showed recurring dilution from slow or weak forward-return selections such as `U`, `PATH`, `SNOW`, `AMKR`, `SLB`, `HAL`, `BRK.B`, `CME`, `TMO`, `BSY`, `UNH`, `ABBV`, `CCL`, `NKE`, `HD`, and `MAR`.

v2 therefore prunes the universe toward stocks that can actually provide V6-B style elasticity inside each theme. ETFs still remain outside the executable pool.

## Result

| candidate | V6AB ann | V6AB maxDD | V6AB Sharpe | verdict |
| --- | ---: | ---: | ---: | --- |
| active V2 baseline | `31.83%` | `-15.68%` | `1.2345` | keep active |
| real-stock hybrid PIT v1 | `30.39%` | `-16.82%` | `1.1795` | not upgrade |
| real-stock hybrid PIT v2 pruned | `30.67%` | `-15.95%` | `1.1883` | improved, still not upgrade |

Standalone V6-B also remained below the active V2 baseline:

| candidate | standalone ann | standalone maxDD | standalone Sharpe |
| --- | ---: | ---: | ---: |
| active V2 baseline | `25.67%` | `-24.29%` | `0.8416` |
| real-stock hybrid PIT v2 pruned | `25.05%` | `-26.53%` | `0.8247` |

## Interpretation

The v2 pruning is directionally correct: it improves the real-stock hybrid candidate versus v1, especially drawdown. But it is not strong enough to replace the current V2 paper-sim strategy.

The important distinction:

- The real-stock pool work is useful and should continue.
- The current pruned candidate is not yet `V6-V3`.
- The active $50k paper simulation should remain on `V6AB_SIM_CANDIDATE_V2_DYNAMIC_B_SIZING` until a candidate beats V2 on full-window return, drawdown, Sharpe, and stress-window behavior.

## Next Work

Continue improving alpha at the stock-pool and selection layer:

- add per-theme quality gates rather than global overlay tweaks,
- penalize candidates with weak 63d or 126d forward-quality history,
- require stronger confirmation before allowing weaker themes like healthcare, financials, and consumer to enter the B sleeve,
- keep high-convexity themes open when their own breadth and trend are strong,
- compare every candidate directly against V2 before promotion.

This keeps V6-V3 development aligned with the system goal: V6-B should find the current market main line, while V6-A and the overlay keep the combined system investable.
