# Existing historical data inventory (2026-10-26)

Drive was inspected read-only; no raw historical data is being copied to this public repository.

| Location | Confirmed item | Size | Verified claim |
|---|---|---:|---|
| history_1h | [QQQ_1h_2017plus.parquet](https://drive.google.com/file/d/1SjaBtqZMDhDEcwxifXMYzBWO5FVb2oXi/view) | 653,842 bytes | File exists, modified 2026-10-15. Date range is **not independently validated**. |
| history_1h | multiple QQQ hourly pre-update snapshots | varies | Backup history exists, do not conflate duplicates with distinct series |
| history_1d | QQQ_1d_long.parquet | 130,215 bytes | File exists |
| history_1d | QLD_1d_long.parquet | 127,898 bytes | File exists |
| model_tests | upbit_eth_backtest_v3.zip | 8,588 bytes | Backtest artifact exists, not underlying intraday dataset |

## Next verification
1. Download QQQ hourly Parquet in an isolated environment with `pandas` and `pyarrow`, and run `parquet_history_audit.py` to report actual timestamp coverage, duplicates, OHLCV fields, hourly bars per session, and freshness. 
2. Search for QLD 1h and continuous 15m data separately; no inference from filename alone.
3. Confirm data source, adjustments, timezone and regular-vs-extended-session policy.
4. Only then decide whether an Alpaca backfill is necessary.

The current chat container does not have a Parquet engine and cannot reach package indexes; therefore file contents have **not** been decoded. The QA script is committed but not executed against real QQQ hourly data. Never claim it passed.
