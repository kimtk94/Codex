# Minute-data research source contract

Verified from the Parquet embedded schema, 2026-10-24.

TSLA historical intraday fragment columns:
timestamp (UTC), open, high, low, close, volume, trade_count, vwap.

R5.2 historical research ledger columns:
timestamp, target_timestamp_4b, expected_seq, fold, symbol, weight, stock, qqq, universe, net10_return, qqq_net10_return, universe_net10_return, log_excess_vs_qqq, log_excess_vs_universe, candidate.

Important: R5.2 ledger is not a minute-level execution ledger. Do not infer staged intraminute fills or triple-barrier outcomes from the four-bucket target timestamp.

The minute-file's timestamp interval and continuity have NOT been verified by actual row decoding. Parquet schema alone cannot confirm the frequency. QQQ and QLD Drive source names presently document 15m and longer aggregations, not validated 1m.

Next: in a runtime with pyarrow, validate raw bar spacing, missing intervals and OHLC consistency before running staggered-entry analysis. Preserve trading strategy versions, date coverage and labels. The candidate horizon 100 minutes remains exploratory, not a fixed maximum. No execution or portfolio performance claims until source and fills validate.
