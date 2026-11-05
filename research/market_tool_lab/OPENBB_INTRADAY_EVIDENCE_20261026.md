# OpenBB V5 Cboe intraday empirical probe — 2026-10-26 KST

Source: [GitHub Actions run 40207354631](https://github.com/kimtk94/Codex/actions/runs/40207354631), artifact 12603904656, branch PR #268.

| Symbol | Interval | Source rows | Unique timestamps | Duplicate timestamp rows | Outcome |
|---|---|---:|---:|---:|---|
| QQQ | 1m | 389 | 389 | 0 | DATA |
| QLD | 1m | 776 | 388 | 388 | QUARANTINE raw input |
| QQQ | 15m/1h | — | — | — | Unsupported by Cboe |
| QLD | 15m/1h | — | — | — | Unsupported by Cboe |

Both 1m series have observed index range 2026-10-23 09:31 to 15:59 (source timestamps' timezone not established in the CSV). QLD duplicated timestamp groups (388 of 388 groups) have *identical OHLCV* on inspection; do not treat both copies as distinct minutes. Compare other columns before safe deduplication. QQQ has no duplicate index.

No backtest was performed using these bars. The OpenBB Cboe provider documents only `1m` and `1d`, with 1m limited to the most recent trading day. For 15m/1h, only derive aggregates from validated, unique and contiguous 1m data or use another suitable provider.

**Decision:** data source usable for short-range observational cross-check once duplicate/timezone reconciliation is implemented; cannot substitute for historical 2020–2026 1-minute backfills. No live trading changes.
