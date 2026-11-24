# Sequential crash-end engine: three-filter local audit

Research only; no change to live trading. Input: complete 190 still-listed cohorts, 130559 fifteen-minute candles from GitHub Actions artifact 12555802314. 2026 data already studied extensively, not independent holdout.

At each completed 15-minute bar, after >=20% drop from prior observed high, >=4 completed bars without fresh low, and >=3% recovery from post-crash low, apply:
- Volatility contraction: latest four-bar average (high-low)/close < 0.8x preceding four-bar average.
- Turnover cooling: latest four-bar mean KRW traded value < 0.75x preceding four bars.
- Price structure: current close above completed 16-bar volume-weighted price (turnover-weighted close proxy, NOT trade-level VWAP) and most recent two-bar minimum low higher than preceding two-bar minimum low.
- Combined: all three above.

Only trade after past-data signal at next 15-minute open, +10% take, -3% stop, 7-day latest exit, fee 0.05% and slip 0.15% each side. Stop-first if both bounds crossed in same candle.

| Filter | Training 2023–25 (n=110) mean net | 2026 exploratory (n=60) mean net | 2026 win % |
|---|---:|---:|---:|
| Baseline | -1.7098% | -1.4238% | 15.00% |
| Volatility | -1.8277% | -1.7132% | 13.33% |
| Turnover cooling | -1.3561% | -0.7028% | 20.00% |
| Price structure | -1.5919% | -0.5593% | 21.67% |
| All three | -0.8846% | -0.3750% | 23.33% |

**Critical qualifier:** these are *delay-until-pass* filters, not reject-if-fail. All 170 baseline signals eventually met each filter in the selected historical weeks. Compared with baseline, the all-three condition deferred 167/170 entries, and only 3 remained at the same bar. No trades were brought earlier. Do not interpret unchanged sample count as a selectivity result.

Trade-level mean remains negative for every strategy. Do not use live. Some entry timing can be very late relative to listing. Need explicit deadline and no-trade branch, strictly bounded seven-day candle window, fresh validation, delisted market inclusion, real spreads/depth, per-minute ambiguity review, portfolio capital and drawdown audit.

Local code: upbit_regime_engine/filter_audit.py, local artifacts filter_results/trades.csv and summary.csv, not yet uploaded to GitHub or independently reproduced in CI.
