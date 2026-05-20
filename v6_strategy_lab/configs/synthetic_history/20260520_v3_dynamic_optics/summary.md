# V6-B Synthetic Historical Radar Generator

- Generated: `2026-05-20T12:53:02`
- Policy: `V6B_SYNTHETIC_HISTORICAL_RADAR_GENERATOR_V1`
- Snapshots: `101` monthly point-in-time universes
- Boundary: price-only synthetic reconstruction; useful for no-lookahead research, not a final live approval.

## Data Coverage

| ticker | first_date | last_date | bars |
| --- | --- | --- | ---: |
| `US.AAOI` | `2018-01-02` | `2026-05-19` | 2106 |
| `US.AMD` | `2018-01-02` | `2026-05-19` | 2106 |
| `US.AMKR` | `2018-01-02` | `2026-05-19` | 2106 |
| `US.ANET` | `2018-01-02` | `2026-05-19` | 2106 |
| `US.COHR` | `2018-01-02` | `2026-05-19` | 2106 |
| `US.INTC` | `2018-01-02` | `2026-05-19` | 2106 |
| `US.LITE` | `2018-01-02` | `2026-05-19` | 2106 |
| `US.MU` | `2018-01-02` | `2026-05-19` | 2106 |
| `US.QQQ` | `2018-01-02` | `2026-05-19` | 2106 |
| `US.SMH` | `2018-01-02` | `2026-05-19` | 2106 |
| `US.SPY` | `2018-01-02` | `2026-05-19` | 2106 |
| `US.TSM` | `2018-01-02` | `2026-05-19` | 2106 |
| `US.WDC` | `2018-01-02` | `2026-05-19` | 2106 |

## Selection Summary

| ticker | track | first_selected | last_selected | selected_months |
| --- | --- | --- | --- | ---: |
| `US.AMKR` | `bottleneck_diffusion` | `2019-03-29` | `2026-05-19` | 37 |
| `US.MU` | `bottleneck_diffusion` | `2019-04-30` | `2026-05-19` | 42 |
| `US.WDC` | `bottleneck_diffusion` | `2019-07-31` | `2026-05-19` | 31 |
| `US.AMD` | `core_reacceleration` | `2019-01-31` | `2026-05-19` | 40 |
| `US.ANET` | `core_reacceleration` | `2019-02-28` | `2026-04-30` | 46 |
| `US.TSM` | `core_reacceleration` | `2019-04-30` | `2026-04-30` | 49 |
| `US.AAOI` | `optics_and_interconnect` | `2019-12-31` | `2026-05-19` | 19 |
| `US.COHR` | `optics_and_interconnect` | `2019-07-31` | `2026-05-19` | 26 |
| `US.LITE` | `optics_and_interconnect` | `2019-04-30` | `2026-04-30` | 30 |
| `US.INTC` | `turnaround_momentum` | `2019-02-28` | `2026-05-19` | 28 |

## Sample Snapshots

| as_of | entries | core_reacceleration | bottleneck_diffusion | optics_and_interconnect | turnaround_momentum |
| --- | ---: | --- | --- | --- | --- |
| `2018-01-31` | 0 | `` | `` | `` | `` |
| `2018-02-28` | 0 | `` | `` | `` | `` |
| `2026-03-31` | 7 | `US.TSM` | `US.WDC, US.MU, US.AMKR` | `US.LITE, US.AAOI` | `US.INTC` |
| `2026-04-30` | 9 | `US.AMD, US.ANET, US.TSM` | `US.WDC, US.AMKR, US.MU` | `US.AAOI, US.LITE` | `US.INTC` |
| `2026-05-19` | 7 | `US.AMD` | `US.MU, US.WDC, US.AMKR` | `US.AAOI, US.COHR` | `US.INTC` |
