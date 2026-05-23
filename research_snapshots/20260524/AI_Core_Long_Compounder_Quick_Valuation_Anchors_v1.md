# AI Core Long Compounder Quick Valuation Anchors v1

- Date: `2026-05-24`
- Framework: `AI-Core SOP v2.6`
- Purpose: Fill missing valuation anchors for AI Core Long Compounder Radar so the weekly table has a price discipline, not just a company-quality ranking.
- Scope: quick first-pass anchors, not full standalone valuation reports.

## Rules

- `V_base` controls common-stock buying discipline.
- `V_option` can raise research priority, but cannot justify buying above `V_base`.
- `Watch Position`: price <= `V_base`.
- `Starter Core`: price <= `V_base * 0.90`.
- `Core Build`: price <= `V_base * 0.80`.
- `High Conviction Core`: price <= `V_floor * 1.10`.
- For semiconductor / hardware / geopolitical names, WACC is not below `10.5%` in this quick anchor set.

## New Anchors

| Ticker | Latest fact anchor | Price used | V_floor | V_base | V_bull | Current gate |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| `META` | Q1 2026 revenue $56.3B, operating income $22.9B, FCF $12.4B | 608.81 | 380 | 620 | 850 | Watch review only, near V_base |
| `AVGO` | FY26 Q1 FCF $8.01B, Q2 revenue guide $22.0B | 413.04 | 225 | 385 | 560 | Above V_base, wait |
| `TSM` | Q1 2026 revenue $35.9B, Q2 guide $39.0B-$40.2B, gross margin 66.2% | 404.52 | 215 | 330 | 500 | Above V_base, wait |
| `ASML` | Q1 2026 net sales EUR8.8B, net income EUR2.8B, 2026 sales guide EUR36B-EUR40B | 1632.25 | 700 | 1120 | 1650 | Near bull ceiling, do not chase |
| `ANET` | Q1 2026 revenue $2.709B, non-GAAP EPS $0.87, Q2 revenue guide about $2.8B | 148.59 | 75 | 125 | 175 | Above V_base, wait |
| `AMD` | Q1 2026 revenue $10.253B, data center revenue $5.775B, FCF $2.566B | 449.59 | 165 | 290 | 475 | Near bull, do not chase |

## Interpretation

`META` is the only newly-valued candidate close enough to `V_base` to deserve immediate qualitative review. It is not an automatic buy because the AI infrastructure spend and Reality Labs drag still need monitoring.

`AVGO / TSM / ANET` are high-quality AI infrastructure compounder candidates, but current prices are above base-case value. The right action is to keep them in the radar and wait for a better price or a post-earnings base-case upgrade.

`ASML / AMD` are currently too close to the bull case for our common-stock discipline. They can remain important AI-era companies and V6AB/Radar evidence anchors, but AI Core should not chase them at these prices.

## System Feedback

- Updated `investment_screener/watchlist.json` with `META / AVGO / TSM / ASML / ANET / AMD`.
- Updated `valuation_sop_router_config.json` so `ANET / AMD` route to `AI_Core_SOP_v2.6`.
- Run `ai_core_long_compounder_radar.py` after this update to refresh the latest table.
