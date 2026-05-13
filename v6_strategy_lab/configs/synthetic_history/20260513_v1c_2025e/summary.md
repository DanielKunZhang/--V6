# V6-B Synthetic Historical Radar Generator

- Generated: `2026-05-13T20:32:15`
- Policy: `V6B_SYNTHETIC_HISTORICAL_RADAR_GENERATOR_V1`
- Snapshots: `96` monthly point-in-time universes
- Boundary: price-only synthetic reconstruction; useful for no-lookahead research, not a final live approval.

## Data Coverage

| ticker | first_date | last_date | bars |
| --- | --- | --- | ---: |
| `US.AMD` | `2018-01-02` | `2025-12-31` | 2011 |
| `US.AMKR` | `2018-01-02` | `2025-12-31` | 2011 |
| `US.ANET` | `2018-01-02` | `2025-12-31` | 2011 |
| `US.INTC` | `2018-01-02` | `2025-12-31` | 2011 |
| `US.MU` | `2018-01-02` | `2025-12-31` | 2011 |
| `US.QQQ` | `2018-01-02` | `2025-12-31` | 2011 |
| `US.SMH` | `2018-01-02` | `2025-12-31` | 2011 |
| `US.SPY` | `2018-01-02` | `2025-12-31` | 2011 |
| `US.TSM` | `2018-01-02` | `2025-12-31` | 2011 |
| `US.WDC` | `2018-01-02` | `2025-12-31` | 2011 |

## Selection Summary

| ticker | track | first_selected | last_selected | selected_months |
| --- | --- | --- | --- | ---: |
| `US.AMKR` | `bottleneck_diffusion` | `2019-02-28` | `2025-12-31` | 32 |
| `US.MU` | `bottleneck_diffusion` | `2019-07-31` | `2025-12-31` | 36 |
| `US.WDC` | `bottleneck_diffusion` | `2019-07-31` | `2025-12-31` | 29 |
| `US.AMD` | `core_reacceleration` | `2019-01-31` | `2025-12-31` | 38 |
| `US.ANET` | `core_reacceleration` | `2019-02-28` | `2025-10-31` | 45 |
| `US.TSM` | `core_reacceleration` | `2019-04-30` | `2025-12-31` | 42 |
| `US.INTC` | `turnaround_momentum` | `2019-02-28` | `2025-11-28` | 23 |

## Sample Snapshots

| as_of | entries | core | bottleneck | turnaround |
| --- | ---: | --- | --- | --- |
| `2018-01-31` | 0 | `` | `` | `` |
| `2018-02-28` | 0 | `` | `` | `` |
| `2025-10-31` | 7 | `US.AMD, US.TSM, US.ANET` | `US.MU, US.WDC, US.AMKR` | `US.INTC` |
| `2025-11-28` | 5 | `US.TSM` | `US.WDC, US.MU, US.AMKR` | `US.INTC` |
| `2025-12-31` | 5 | `US.AMD, US.TSM` | `US.MU, US.WDC, US.AMKR` | `` |
