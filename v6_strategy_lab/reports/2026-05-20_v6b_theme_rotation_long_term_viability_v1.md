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

## Decision

ETF theme rotation should become V6-B's first-layer theme discovery engine, not its final execution engine.

The next V6-B version should:

1. Use ETF proxies to identify the current dominant theme.
2. Map the winning theme to a point-in-time stock candidate pool.
3. Select within that theme by relative strength, trend, valuation/catalyst filter, overheat filter, and drawdown risk.
4. Express through a limited V6-B sleeve alongside V6-A, not as a standalone full-account rotation.

## Current Verdict

V6-B is promising as a durable main-theme discovery framework, but the current ETF-only execution is not strong enough for long-term capital allocation.

