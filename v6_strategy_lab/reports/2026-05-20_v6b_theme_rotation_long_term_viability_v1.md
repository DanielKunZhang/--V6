# 2026-05-20 V6-B Theme Rotation Long-Term Viability v1

## Question

Can V6-B be a durable system that finds the next main market theme after AI infrastructure fades?

## Test Performed

- Layer tested: first-layer ETF theme rotation only.
- Window: `2012-01-01` to `2026-05-19`.
- Data refreshed through OpenD for 18 theme ETF / sector proxies.
- Purpose: verify whether the system can rotate across themes before stock-level selection.

This is not yet the full V6-B system. It tests the theme discovery layer, not the theme-internal stock selection layer.

## Long-Term Result

Best v0 by Sharpe:

- Config: `v0_top2_min0.02_risk100%`
- Annualized return: about `+13.7%`
- Max drawdown: about `-47.9%`
- Sharpe: about `0.45`

Highest-return v0:

- Config: `v0_top1_min0.02_risk100%`
- Annualized return: about `+14.3%`
- Max drawdown: about `-49.7%`
- Sharpe: about `0.43`

Best guarded variant:

- Config: `v1_guarded_top1_min0.02_risk100%`
- Annualized return: about `+10.9%`
- Max drawdown: about `-28.0%`
- Sharpe: about `0.38`

## Theme-to-Stock Follow-Up

After the ETF-only test, a first theme-to-stock expression was added:

- ETF / sector proxies still decide the active market themes.
- Only after a theme wins does the strategy rank stocks inside that theme by point-in-time relative strength and trend.
- If a theme does not yet have a stock pool, it falls back to the selected ETF proxy.
- Benchmarks are now written into the report: `US.SPY`, `US.QQQ`, `US.BRK.B`, `US.VTV`.

Long-term run:

- Script: `v6b_theme_rotation_backtest.py`
- Report: `backtest_results/v6b_theme_rotation/v6b_theme_rotation_20260520_theme_to_stock_v2.md`
- Window: `2012-01-01` to `2026-05-19`
- OpenD usage: `US.VTV` was refreshed to `2026-05-19`; the strategy run itself used local cache.

Best risk-adjusted theme-to-stock variant:

- Config: `v1_guarded_top3_min0.08_risk90%_stocks`
- Annualized return: about `+27.1%`
- Max drawdown: about `-24.3%`
- Sharpe: about `0.89`
- Final value on `$10,000`: about `$312,863`

Higher-return raw variant:

- Config: `v0_top3_min0.02_risk100%_stocks`
- Annualized return: about `+31.2%`
- Max drawdown: about `-31.6%`
- Sharpe: about `0.86`
- Final value on `$10,000`: about `$493,960`

Benchmarks over the same window:

| benchmark | ann | maxDD | Sharpe | final |
| --- | ---: | ---: | ---: | ---: |
| `US.SPY` | `+14.5%` | `-33.7%` | `0.60` | `$70,172` |
| `US.QQQ` | `+20.2%` | `-35.1%` | `0.76` | `$141,417` |
| `US.BRK.B` | `+13.5%` | `-29.6%` | `0.52` | `$61,851` |
| `US.VTV` | `+12.2%` | `-36.8%` | `0.50` | `$52,558` |

## Interpretation

The ETF theme rotation layer is useful as a theme radar, but not yet as a standalone long-term strategy.

What works:

- It is not locked into AI infrastructure.
- It rotates across technology, semiconductors, precious metals, energy/resources, healthcare/biotech, and broad beta.
- It captured strong environments such as 2020 and 2024-2026.
- It can show when current leadership is shifting, for example the latest 2026-05-19 top themes were `Semis / AI Compute`, `Energy / Resources`, and `Broad Beta`.

What fails:

- Long-run Sharpe is too low.
- Max drawdown is too high in the raw v0 versions.
- The guarded version lowers drawdown but sacrifices too much return and Sharpe.
- Buying ETF proxies directly is too blunt; it confirms theme direction but does not extract enough alpha.

The theme-to-stock follow-up changes the verdict materially:

- Pure ETF rotation does not beat the best simple growth benchmark convincingly.
- Theme-to-stock V6-B does beat `SPY`, `QQQ`, `BRK.B`, and `VTV` in this test.
- The guarded top-3 stock version improves both return and drawdown versus `SPY` and `QQQ`.
- The main remaining weakness is Sharpe below `1.0`, so this is a promising main trunk, not yet a fully allocator-ready production rule.

## Decision

ETF theme rotation should become V6-B's first-layer theme discovery engine, not its final execution engine.

The next V6-B version should:

1. Use ETF proxies to identify the current dominant theme.
2. Map the winning theme to a point-in-time stock candidate pool. The first working version now exists in `v6b_theme_rotation_backtest.py`.
3. Select within that theme by relative strength and trend first; add valuation/catalyst, overheat, and drawdown risk filters next.
4. Express through a limited V6-B sleeve alongside V6-A, not as a full-account live rotation until out-of-sample and walk-forward checks are stronger.

## Current Verdict

V6-B is now promising as a durable main-theme momentum trunk once ETF theme discovery is paired with theme-level stock expression.

It is not just an AI infrastructure strategy anymore. The current evidence says the full path should be:

`market regime -> ETF theme discovery -> theme stock pool -> stock relative strength/trend -> V6-A/V6-B sleeve sizing`

The result is strong enough to continue engineering and validation. It is not yet strong enough to trade live at meaningful capital size without walk-forward validation, broader theme pools, and stricter production risk gates.
