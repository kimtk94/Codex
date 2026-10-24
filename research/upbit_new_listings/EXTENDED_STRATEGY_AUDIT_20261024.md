# Extended 190-coin first-week strategy check — 2026-10-24

Data source: GitHub Actions run 40081400856 / artifact 12555802314, 130559 fifteen-minute OHLCV records for 190 qualifying still-listed KRW markets. Research only. Local recomputation, not yet a GitHub CI test.

All policies use +10% TP, -3% SL, entry/exit assumed slippage 0.15% each, commission 0.05% each, same stop-first intrabar handling. Entries remain inside the first 7 days after first observed candle.

| Policy | 2023–25 n | Train avg net % | 2026 n | 2026 avg net % | 2026 win % |
| --- | ---: | ---: | ---: | ---: | ---: |
| 60m | 120 | -1.339 | 70 | -2.185 | 10.00 |
| 4h | 120 | -1.556 | 70 | -0.892 | 20.00 |
| 4h, volume cooled | 113 | -1.452 | 68 | -0.822 | 20.59 |
| Drop-then-rebound | 116 | -2.236 | 61 | -0.691 | 19.67 |
| Drop-then-rebound + volume surge | 115 | -2.115 | 61 | -1.754 | 11.48 |

Precisely defined experimental rules:
- 4h volume cooling: mean KRW traded value in 15m bars 4–15 < 0.5 × mean traded value in bars 0–3. Enter bar 16 open.
- Drop/rebound: beginning at bar 16 up to bar 191, an observed high-to-low drawdown of at least 15% in prior bars, nondecreasing lows over prior 3 bars, and close of last completed bar above highs of the prior two bars. Enter following bar open. The more stringent version additionally requires last completed bar's KRW turnover > 1.5× the median turnover of previous 4 bars.
- Reference 60m and 4h: bar 4 / bar 16 opening price with adverse entry slippage.

Cautions:
- 2026 has been inspected during strategy development. Thus the 2026 slice is no longer an untouched out-of-sample holdout for these additional rules.
- All average returns are negative. No support for live deployment.
- Delisted coins omitted, order-book impact unknown, candle-level stop-first conservative, missing observations, overlapping portfolios and portfolio drawdown not modeled.
- A genuine next test needs frozen hypotheses and later unseen listings or purged walk-forward folds, plus a comprehensive survivor-bias audit.
