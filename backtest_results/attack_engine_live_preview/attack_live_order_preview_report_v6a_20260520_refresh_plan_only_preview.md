# V6 Attack Engine Live Order Preview

- Generated: `2026-05-20T12:17:44`
- Signal date: `2026-05-19`
- Strategy capital: `5,000.00`
- Max gross exposure: `1.00x`
- Net existing account positions: `False`
- Net V6 managed positions: `True`
- Managed state: `backtest_results/v6a_state/v6a_managed_positions_real_281756481449956811.json`
- Quote snapshot time: `2026-05-20 00:17:15.435`
- Account deployable cash estimate: `$25,069.23`
- Total preview buy notional: `$1,496.08`
- Warnings: `[]`

## Target Weights

| ticker | weight |
| --- | ---: |
| CASH | 13.60% |
| US.AMZN | 5.93% |
| US.AVGO | 12.38% |
| US.BIL | 5.83% |
| US.GLD | 7.50% |
| US.GOOGL | 30.34% |
| US.NVDA | 24.41% |

## Preview Orders

| ticker | side | target weight | target value | target qty | preview qty | price | value | bid/ask |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| US.AMZN | SELL | 5.93% | $296.69 | 1 | 3 | $259.01 | $777.03 | $259.01/$259.35 |
| US.AVGO | SELL | 12.38% | $619.18 | 1 | 1 | $411.52 | $411.52 | $411.52/$412.00 |
| US.BIL | SELL | 5.83% | $291.67 | 3 | 3 | $91.55 | $274.65 | $91.55/$91.56 |
| US.GLD | SELL | 7.50% | $375.00 | 0 | 1 | $412.00 | $412.00 | $412.00/$412.38 |
| US.GOOGL | BUY | 30.34% | $1,517.01 | 3 | 1 | $388.28 | $388.28 | $387.80/$388.28 |
| US.NVDA | BUY | 24.41% | $1,220.31 | 5 | 5 | $221.56 | $1,107.80 | $221.54/$221.56 |

## Interpretation

- This is read-only preview. It does not call `place_order`.
- Default mode does not net long-term account holdings, so V6 remains an independent small sleeve.
- The current V6 signal still comes from replay cache. Production should refresh historical bars to today before using this preview for live trading.
