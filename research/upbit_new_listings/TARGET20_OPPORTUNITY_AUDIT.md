# Post-crash opportunity ceiling audit (2026-10-26)

Data: artifact 12555802314, 190 complete still-listed KRW listing cohorts. Replay via pre-existing local causal filter_audit.sim() and original first-seven-day 15m OHLCV. This is **not** a trading result: the post-entry max price is an oracle upper bound, and ignores sequencing of intra-bar high vs low.

For all-three regime filters, n=110 2023-25 and n=60 2026:
- Ex-post max >=+20% net: 29.09% train, 23.33% 2026.
- Ex-post max >=+50% net: 10.91% train, 6.67% 2026.
- Ex-post maximum net return mean: +20.35% train, +15.16% 2026.
- Ex-post maximum net return median: +8.90% train, +6.71% 2026.
- Observed +20% before first -3% stop candle inclusive: 12.73% train, 11.67% 2026; intrabar order UNKNOWN and this is not guaranteed executable.
- Realized baseline mean: -0.88% train, -0.37% 2026.

For comparison, base filter post-entry +20% oracle opportunity: 28.18% train and 23.33% 2026.
Neither the oracle opportunity nor any actual historical rule demonstrates +20% average realized trade return. Do not deploy live.

Methodological caveats: analysis reuses exploratory 2026; excludes delisted markets; execution slippage assumed 0.15%/side plus 0.05% fee/side; candle open entry, high-based oracle exits, snapshot OHLCV cannot determine within-bar event order; fresh holdout needed. Order execution capacity unverified.

Next experiment: conditional opportunity labels at signal time (top +20% before adverse excursion -3%) with purged chronological model tests, plus capped entry deadlines and no-trade option; compare against selective-entry baseline with a minimum sample size and validate future unseen listing cohorts. Never optimize on the oracle maximum as actual attainable PnL.
