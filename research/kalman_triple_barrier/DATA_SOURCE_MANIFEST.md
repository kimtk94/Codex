# Minute-bar data source manifest — research only

Updated: 2026-10-24

## Actual identified sources

| Source | Drive file id | State | Notes |
| --- | --- | --- | --- |
| TSLA intraday fragment | `1TQaaCu0x96CcqF0wKoHHLLnZttRjgDbL` | NOT YET VALIDATED | 37,401-byte parquet for 2023-01-13–2023-01-18 filename window, data cadence unknown |
| NVDA intraday fragment | `1cUlmmpHw_yX3E7s1koQ_ZxizkiHKEb07` | NOT YET VALIDATED | 14,221-byte parquet, data cadence unknown |
| R5.2 trade ledger | `1gTiZyC18o8omdHZB2Wl_bptANtaPgu4f` | SCHEMA NOT VERIFIED | Cannot assume minute entry timestamps |
| QQQ intraday | Drive folder `1q9f1sfFSnYx_B-eweGGQCtxlxukk0hYC` | 15m/60m/195m/240m | Not suitable as a 1-minute proxy |
| QLD intraday | Drive folder `19DHXnwnm7ULN2Pah0febWS9li3Z7hzoZ` | 15m/60m/195m/240m | Not suitable as a 1-minute proxy |
| KRW-BTC 1m | Drive folder `17Htfuxw6itl6mMlmIE8bekuNbVMbDTu4` | Separate market | Available 2025/2026 monthly files; not evidence for U.S. equity signal behavior |

## Integration gate

1. Retrieve original parquet in an authorized CI environment, without exposing raw files or secrets in a public GitHub repo.
2. Read schema and time-series edge intervals, verify true consecutive 60-second bars.
3. Verify market hours, timezone, split adjustment, source integrity, trading-day gaps.
4. Produce a clean 1-minute OHLC **private CI artifact**.
5. Execute staggered entry with several provisional horizons. **100 minutes is not a maximum**.
6. Run walk-forward and non-overlapping portfolio-level stress/position accounting.
7. Publish **aggregate result metrics only** to the Vercel view; do not publish broker credentials, proprietary raw inputs or strategy-sensitive signal-level ledgers.

Unit tests passing are not market-data validation. Currently empirical staggered backtest is NOT COMPLETE.
