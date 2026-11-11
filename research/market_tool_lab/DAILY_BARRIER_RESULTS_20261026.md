# Observed daily triple-barrier event labels (2026-10-26)

Source: existing private Kalman file `QLD_QQQ_daily_alignment.csv`, 2,432 daily rows, dates 2017-01-03 through 2026-09-04. Raw source stays outside GitHub.

**Design:** all eligible daily closes are hypothetical long entries; evaluate next up to 4 daily OHLC bars. Fixed TP +3%, SL -3%, pessimistic SL-first when both touched on the same bar. Last 4 incomplete horizons excluded. All events overlap; this is **not a trading strategy**, actual win rate, or OOS model result. Fees and slippage absent.

| Label count | QQQ | QLD |
|---|---:|---:|
| Fully observed events | 2,428 | 2,428 |
| TP | 449 (18.5%) | 1,021 (42.1%) |
| SL | 474 (19.5%) | 918 (37.8%) |
| TIME (4 daily bars) | 1,505 (62.0%) | 489 (20.1%) |
| Same-bar both touched (included in SL) | 3 | 33 |
| Average gross event return (NOT strategy return) | +0.2572% | +0.2458% |

Manual independent direct-CSV calculation cross-checked the `triple_barrier_reference.py` semantics. Standalone executable in `daily_barrier_labels.py`; its CI test uses source-free unit tests and does not access user Drive files.

## Follow-up
- Obtain authenticated *actual* Kalman R5.1/R5.2 entry signals, with timestamp, price, symbol, regime, and execution policy.
- Enforce non-overlapping capital and order schedule, cost model (fees/slippage/spread), walk-forward OOS, trade-by-trade comparison.
- Test daily barrier convention vs exact actual intraday entry/exits; if not equivalent, do not label as strategy uplift.
