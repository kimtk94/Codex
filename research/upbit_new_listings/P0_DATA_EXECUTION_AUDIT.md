# P0 data / execution integrity audit — 2026-10-26

Reviewed archived GitHub Actions run 40081400856 artifact 12555802314.

Archive comprises 201 KRW new-listing candidates still listed: 190 labeled complete (>=600 observed 15m candles), 7 sparse, 4 incomplete. There are 197 markets with emitted candles and 130,559 recorded bars.

Independent OHLC/gap scan sorted by UTC candle time:
- 819 positive inter-candle gaps longer than 15 minutes;
- equivalent 1,820 missing 15m clock slots;
- gaps occur in 62 of the 197 markets having candle data;
- 0 impossible OHLC bars (open/close outside [low,high] or low>high);
- 0 duplicate/non-increasing timestamps after sorting.
Examples with frequent gaps: USDG 93, EURC 92, USDS 81, RLUSD 79, CRV 56. Upbit does not necessarily print candles when there is no trade; gaps do not necessarily indicate API failure.

New `execution_safety.py` provides integrity checks and conservative bar fills:
- gap-open below stop exits at the opening price, not the stop price;
- stop has precedence when a bar hits stop and target;
- trailing-stop update only after the bar is complete;
- inconsistent OHLC and non-15m intervals detected.
`test_execution_safety.py` includes seven deterministic unit tests, wired into the research workflow prior to data collection.

**Important**: these safeguards have NOT yet been wired into legacy study.py and reentry_audit.py fill engines; historical return figures are not corrected by adding tests alone. Existing results must be recomputed using the corrected common fill logic. Real intrabar order is still unknown, and only 1m / trade-level replay resolves it more reliably.

Further P0 gaps: historical delisted listings omitted; first traded minute potentially wrong if candle lookback is truncated; exact listing announcement time not verified; no actual order book impact calibration; 2026 has been repeatedly queried and cannot be an untouched holdout. No live trading changes.
