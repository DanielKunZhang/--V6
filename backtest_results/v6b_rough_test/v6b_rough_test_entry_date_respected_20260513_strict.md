# V6-B Rough Test — Yahoo Finance Data

- Generated: `2026-05-13T19:11:16`
- Status: **ENTRY_DATE_RESPECTED_PROBE**
- Data: Yahoo Finance daily OHLCV (yfinance)
- Scope: 2018-01-01 – 2026-05-12
- OOS split: 2024-01-01 – 2026-05-12

> ⚠️  This is NOT a formal point-in-time historical backtest.
> The probe respects `entry_date` from the 2026-05-10 V6-B seed, so V6-B names are inactive before that date.
> Interpretation: this can test whether earlier rough-test conclusions were inflated by premature activation, but it still cannot validate long-term V6-B edge.

## Section 1 — Pool Comparison (base engine params, mom60 top3 dd10%)

| Config | Pool | AnnR | OOS | MaxDD | Sharpe | OOS-Sh | Final$ | Gate |
|--------|------|-----:|----:|------:|-------:|-------:|-------:|:----:|
| V6-A  (ai_mega)           [base    (mom60  top3 dd10%)] | NVDA+AVGO+MSFT+AMZN+META+GOOGL | +26.4% | +47.7% | -26.1% | 0.89 | 1.30 | $65,169 | ✓ |
| V6-B  (core_reaccel)      [base    (mom60  top3 dd10%)] | AMD+ANET+TSM | +9.0% | +21.3% | -9.3% | 0.57 | 1.87 | $19,912 |   |
| V6-B  (bottleneck)        [base    (mom60  top3 dd10%)] | MU+WDC+AMKR | +9.0% | +21.3% | -9.3% | 0.57 | 1.87 | $19,912 |   |
| V6-B  (full seed)         [base    (mom60  top3 dd10%)] | AMD+ANET+TSM+MU+WDC+AMKR | +9.0% | +21.3% | -9.3% | 0.57 | 1.87 | $19,912 |   |
| V6-B  (full+watch)        [base    (mom60  top3 dd10%)] | AMD+ANET+TSM+MU+WDC+AMKR+COHR | +9.0% | +21.3% | -9.3% | 0.57 | 1.87 | $19,912 |   |
| V6-AB (blended)           [base    (mom60  top3 dd10%)] | NVDA+AVGO+MSFT+AMZN+META+GOOGL+AMD+ANET+TSM+MU+WDC+AMKR | +26.4% | +47.7% | -26.1% | 0.89 | 1.30 | $65,169 | ✓ |
| V6-B  (turnaround ctrl)   [base    (mom60  top3 dd10%)] | INTC | +9.0% | +21.3% | -9.3% | 0.57 | 1.87 | $19,912 |   |
| Benchmark: QQQ buy-hold | QQQ | +20.4% | +27.7% | -35.1% | 0.69 | 1.05 | $47,213 |   |
| Benchmark: SPY buy-hold | SPY | +14.5% | +22.0% | -33.7% | 0.54 | 1.02 | $31,085 |   |

## Section 2 — V6-B Full Seed: Parameter Sensitivity

| Config | Pool | AnnR | OOS | MaxDD | Sharpe | OOS-Sh | Final$ | Gate |
|--------|------|-----:|----:|------:|-------:|-------:|-------:|:----:|
| V6-B full seed  [base    (mom60  top3 dd10%)] | AMD+ANET+TSM+MU+WDC+AMKR | +9.0% | +21.3% | -9.3% | 0.57 | 1.87 | $19,912 |   |
| V6-B full seed  [slow    (mom120 top3 dd10%)] | AMD+ANET+TSM+MU+WDC+AMKR | +9.0% | +21.3% | -9.3% | 0.57 | 1.87 | $19,912 |   |
| V6-B full seed  [conc    (mom60  top2 dd10%)] | AMD+ANET+TSM+MU+WDC+AMKR | +9.0% | +21.3% | -9.3% | 0.57 | 1.87 | $19,912 |   |
| V6-B full seed  [loose   (mom60  top3 dd15%)] | AMD+ANET+TSM+MU+WDC+AMKR | +9.0% | +21.3% | -9.3% | 0.57 | 1.87 | $19,912 |   |

## Section 3 — Individual Ticker Buy-Hold (raw alpha signal, no engine)

| Config | Pool | AnnR | OOS | MaxDD | Sharpe | OOS-Sh | Final$ | Gate |
|--------|------|-----:|----:|------:|-------:|-------:|-------:|:----:|
| AMD      buy-hold  [core_reaccel] | AMD | +55.9% | +64.5% | -65.4% | 0.98 | 1.06 | $408,279 |   |
| ANET     buy-hold  [core_reaccel] | ANET | +31.5% | +46.6% | -52.2% | 0.72 | 0.91 | $98,716 |   |
| TSM      buy-hold  [core_reaccel] | TSM | +37.8% | +82.3% | -59.8% | 0.86 | 1.54 | $145,671 |   |
| MU       buy-hold  [bottleneck] | MU | +41.8% | +159.1% | -57.9% | 0.84 | 1.79 | $185,254 |   |
| WDC      buy-hold  [bottleneck] | WDC | +24.9% | +162.1% | -72.2% | 0.60 | 1.90 | $63,946 |   |
| AMKR     buy-hold  [bottleneck] | AMKR | +29.6% | +44.5% | -70.1% | 0.65 | 0.84 | $87,009 |   |
| COHR     buy-hold  [watch] | COHR | +93.8% | +152.5% | -54.8% | 1.25 | 1.63 | $83,821 |   |
| INTC     buy-hold  [turnaround] | INTC | +14.4% | +48.6% | -72.0% | 0.42 | 0.86 | $30,843 |   |
| NVDA     buy-hold  [V6-A ref] | NVDA | +57.7% | +91.0% | -66.3% | 1.06 | 1.47 | $448,981 |   |
| AVGO     buy-hold  [V6-A ref] | AVGO | +43.1% | +80.5% | -48.3% | 0.95 | 1.31 | $199,839 |   |

## Section 4 — V6-A vs V6-B Head-to-Head (same engine, different pools)

| Config | Pool | AnnR | OOS | MaxDD | Sharpe | OOS-Sh | Final$ | Gate |
|--------|------|-----:|----:|------:|-------:|-------:|-------:|:----:|
| V6-A  [base    (mom60  top3 dd10%)] | NVDA+AVGO+MSFT+AMZN+META+GOOGL | +26.4% | +47.7% | -26.1% | 0.89 | 1.30 | $65,169 | ✓ |
| V6-B  [base    (mom60  top3 dd10%)] | AMD+ANET+TSM+MU+WDC+AMKR | +9.0% | +21.3% | -9.3% | 0.57 | 1.87 | $19,912 |   |
| V6-A  [slow    (mom120 top3 dd10%)] | NVDA+AVGO+MSFT+AMZN+META+GOOGL | +24.2% | +32.0% | -31.7% | 0.81 | 0.89 | $56,590 | ✓ |
| V6-B  [slow    (mom120 top3 dd10%)] | AMD+ANET+TSM+MU+WDC+AMKR | +9.0% | +21.3% | -9.3% | 0.57 | 1.87 | $19,912 |   |
| V6-A  [conc    (mom60  top2 dd10%)] | NVDA+AVGO+MSFT+AMZN+META+GOOGL | +26.9% | +42.4% | -31.7% | 0.83 | 1.08 | $67,244 | ✓ |
| V6-B  [conc    (mom60  top2 dd10%)] | AMD+ANET+TSM+MU+WDC+AMKR | +9.0% | +21.3% | -9.3% | 0.57 | 1.87 | $19,912 |   |
| V6-A  [loose   (mom60  top3 dd15%)] | NVDA+AVGO+MSFT+AMZN+META+GOOGL | +26.4% | +47.7% | -26.1% | 0.89 | 1.30 | $65,169 | ✓ |
| V6-B  [loose   (mom60  top3 dd15%)] | AMD+ANET+TSM+MU+WDC+AMKR | +9.0% | +21.3% | -9.3% | 0.57 | 1.87 | $19,912 |   |
