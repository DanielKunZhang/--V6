# AI Optical / Rack-scale Revenue Build Mechanism v1

- Date: 2026-05-24
- Purpose: Convert AI optical / rack-scale / AI cabinet supply-chain narratives into revenue, evidence, valuation absorption, and action discipline.
- Status: active research input
- Boundary: Not an auto-trading system. Does not replace `V6AB_SIM_CANDIDATE_V2_DYNAMIC_B_SIZING`.

## What It Does

This mechanism takes high-momentum themes such as AI optical, rack-scale systems, MLCC, PCB/ABF, liquid cooling, CPO, power/HVDC, and HBM, then forces them through a repeatable structure:

- revenue-line build
- official-source calibration
- Bear/Base/Upside rough valuation
- current price absorption check
- evidence-level labeling
- evidence gates before any pilot review
- daily email reminder for periodic review

The goal is not to predict short-term price movement. The goal is to prevent strong narratives from becoming unstructured chase behavior.

## Current Coverage

| ticker | role | action | note |
| --- | --- | --- | --- |
| `LITE` | AI optical / photonics product-line build | `DO_NOT_CHASE` | Strong line, but price is already above rough upside anchor. |
| `COHR` | AI optical / datacom segment-level build | `DO_NOT_CHASE` | Better official segment evidence, but still price-full. |
| `AAOI` | high-beta 800G/1.6T ramp sample | `DO_NOT_CHASE` | Highest beta, but highest dilution, customer concentration, and execution risk. |

## How To Reuse

1. Add a candidate company to `ai_optical_revenue_build_config.json`.
2. Include official sources, calibration fields, revenue lines, scenario assumptions, financial layer, price anchor, and evidence gates.
3. Run:

```bash
python3 ai_optical_revenue_build.py --all --asof YYYY-MM-DD
```

4. Review:
   - `/Users/zhangkun/Desktop/AI个人投资公司/报表输出/LATEST/AI_Optical_Revenue_Build_Compare_LATEST.html`
   - ticker-level `*_AI_Optical_Revenue_Build_LATEST.html`

## Reminder Path

`morning_brief.py` runs a Friday reminder for AI Optical / Rack-scale Revenue Build review. The reminder reads the compare JSON and highlights current `DO_NOT_CHASE` names.

For high-beta names such as `AAOI`, the reminder explicitly requires Q2/Q3 proof, dilution review, customer-concentration review, and crowding reset before any future pilot review.

## Investment Impact

- V6AB: improves fact precision for strong themes, but only as evidence input.
- A股 Radar: separates "theme is strong" from "stock is safe enough to pilot".
- Main portfolio: prevents high-beta controversial assets from taking high-trust compounder budget.
- User workflow: when a short-term group or article mentions a high-elasticity stock, the next step is to ask AI to structure it here, not to chase it.
