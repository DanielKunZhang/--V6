# V6-B Quality Gate v1 Read

- Date: `2026-05-20`
- Objective: test whether stricter point-in-time stock quality gates can improve the V6-V3 real-stock path.
- Generator: `v6b_cross_theme_pit_generator.py --quality-profile v6b_quality_v1`
- PIT manifest: `v6_strategy_lab/configs/synthetic_history/20260520_v7_real_stock_pit_quality_v1/manifest.json`
- Quick compare: `backtest_results/v6ab_candidate_quick_compare/v6ab_candidate_quick_compare_20260520_real_stock_pit_v7_quality_v1.csv`
- Selection audit: `backtest_results/v6b_selection_quality/v6b_selection_quality_20260520_real_stock_pit_v7_quality_v1.md`

## What Changed

The generator now supports a named `quality_profile`.

Default behavior remains unchanged with `--quality-profile none`. The new `v6b_quality_v1` profile applies point-in-time filters only:

- minimum 60d momentum,
- minimum 120d momentum for slower/quality themes,
- minimum relative strength where needed,
- minimum candidate score,
- maximum drawdown-from-high threshold.

No forward returns are used in the live selection rule. Forward returns are used only afterward for diagnostic audit.

## Result

| candidate | standalone V6-B ann | standalone Sharpe | V6AB ann | V6AB maxDD | V6AB Sharpe | verdict |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| active V2 baseline | `25.67%` | `0.8416` | `31.83%` | `-15.68%` | `1.2345` | keep active |
| pruned real-stock hybrid v2 | `25.05%` | `0.8247` | `30.67%` | `-15.95%` | `1.1883` | not upgrade |
| quality-gated real-stock hybrid v1 | `26.33%` | `0.8576` | `30.76%` | `-16.02%` | `1.1910` | improved B, not V6-V3 |

## Selection Quality

The quality gate improved the diagnostic forward-return profile:

| theme | 63d avg after gate | note |
| --- | ---: | --- |
| `semis_ai` | `14.99%` | strongest convexity remains here |
| `technology` | `13.38%` | strong and persistent |
| `consumer_discretionary` | `10.18%` | quality gate materially helped |
| `precious_metals` | `9.94%` | still useful diversifier |
| `utilities_power` | `9.07%` | stable forward quality |
| `healthcare_biotech` | `8.08%` | better than v1/v2, but uneven |
| `energy_resources` | `6.57%` | improved but still cyclical |
| `financials` | `5.66%` | better but still not a high-alpha sleeve |

Remaining weak pairs include `VLO`, `COHR`, `DDOG`, `ISRG`, `REGN`, `BKR`, `DXCM`, and weaker financial/energy names. This suggests the next useful change is more selective per-theme name eligibility, not overlay tuning.

## Interpretation

This pass answers an important system question:

- Real-stock quality filtering can improve V6-B standalone alpha.
- The improvement is not enough to replace the active V2 in the V6AB combined system.
- The bottleneck is now less about broad theme coverage and more about which names each weaker theme is allowed to express.

So the current V6-V3 path is valid, but still research-only. The active paper simulation should remain on `V6AB_SIM_CANDIDATE_V2_DYNAMIC_B_SIZING`.

## Next Work

Continue at the stock-selection layer:

- add explicit per-theme allow/deny metadata to the universe config,
- require stronger eligibility for weak themes before they can replace V2 gap-fill names,
- check whether quality-gated B improves V6AB only in specific regime sleeves before considering any promotion.
