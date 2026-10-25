# Entry timing and +20% opportunity audit

Based on 170 signals for the combined sequential post-crash filters; 190 still-listed complete KRW cohorts. Signal timing binned by observed 15-minute bar index (may differ from elapsed wall clock when missing candles). Labels are ex-post +20% price reach before first -3% stop candle; ordering within a 15m candle is not recoverable. Mean realized trading PnL comes from the fixed +10% / -3% baseline, **not** a +20%-target backtest.

| Period | Entry bin | n | Ex-post +20% pre-stop | Mean baseline net |
|---|---|---:|---:|---:|
| 2023–25 | 0–4h | 4 | 50.0% | +3.241% |
| 2023–25 | 4–12h | 42 | 16.67% | -0.772% |
| 2023–25 | 12–24h | 29 | 3.45% | -1.901% |
| 2023–25 | 24–48h | 17 | 5.88% | -0.191% |
| 2023–25 | 48h+ | 18 | 16.67% | -1.081% |
| 2026 explored | 0–4h | 1 | 0% | +9.725% |
| 2026 explored | 4–12h | 19 | 15.79% | +0.170% |
| 2026 explored | 12–24h | 23 | 8.70% | -1.551% |
| 2026 explored | 24–48h | 8 | 0% | -1.338% |
| 2026 explored | 48h+ | 9 | 22.22% | +1.213% |

Total 21/170 oracle pre-stop +20% opportunities, with ambiguous intrabar execution. Sample counts <20 must not be used to choose trading rules. 2026 reused for exploratory analysis and not fresh holdout. No statistically supported +20% average realized net return. No live policy changes. Future: obtain delisted cohorts and new listings, implement feature extraction as-of each bar, frozen chronological validation and execution-cost calibration.