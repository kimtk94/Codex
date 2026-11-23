# Kalman research data integrity and backfill candidate matrix — 2026-11-23 KST

**Implementation status:** Kalman Daily20 7/10 (70%). Three scientific acceptance gates remain. The data-inventory/backfill diagnostic is distinct from an approved strategy. No live trades, prospectively sealed events, existing Drive price files or research outcomes are rewritten.

## Actually checked, original Google Drive ZIP bytes

| Source | Drive ID | Date/contents | Manifest integrity |
|---|---|---|---|
| Daily20 latest price/TA ZIP | `1nWbyCiRSscJSqgZYvYhJ9DKHRlBwlKgE` | 26 raw prices + 26 TA features, through U.S. 2026-11-20 | **52/52 member hashes PASS** |
| Wider market + macro research ZIP | `1aUhvIAsE2x2-LuKv5nSxmDGX0Uo4mqYd` | 19 prices + 19 TA features + 12 FRED latest-revised series; historical market latest XNYS 2026-10-30; published Oct 31 | **40/40 member hashes PASS** |
| Daily20 results ZIP | `1l-e4OLKS4qlDjNsf8TdkMsd5w3QouF4w` | as-of 2026-11-20, immutable 60-event legacy research journal, 0 formally settled 4-session OOS outcomes | publisher SHA readback PASS, scientific HOLD |
| Old QLD/QQQ alignment | `1v9mM0l0-jLpXu81v6wfwJXHK3kSREsL-` | 2,432 rows through 2026-09-04 | historical fixed-source hash PASS, GitHub SA file-scope access [#1018](https://github.com/kimtk94/Codex/issues/1018) HOLD |
| Historical ETF CSV | `1331d3hAjNx-81rr6kfEGe30Kz5nQIutH` | ten ticker snapshots through 2026-09-04 | historical reference only, stale |
| S&P100 membership | `18LCkOKDp1J5YTTCFiaT4BUBASPMiRUDk` | 2026-09-01 dated snapshot | historical membership only; do not apply retroactively |
| Long daily parquet folder | [history_1d](https://drive.google.com/drive/folders/1k8pziSSrTcPbSNwPd4E40n-J9Uj6Y1hB) | 5 symbols, source files last modified Aug31; health JSON Sep1 | staleness noted; need session-gap and point-in-time recon |
| Long hourly parquet folder | [history_1h](https://drive.google.com/drive/folders/16HdGCP3FBM10ssPz51vlFSl6J71zASCs) | 68 files, many timestamped QQQ backup revisions; latest Oct15 | do **not** interpret 68 files as 68 tickers |

The 19-wide market ZIP **lags the latest Daily20 by 15 U.S. exchange sessions**, 2026-11-02 through 2026-11-20. The 9 common price members are GLD, HYG, IWM, LQD, QQQ, SMH, SPY, TLT, and VIX (same `yfinance` provider; NOT independent market-close evidence). The 10 wide-market-only price members are BTC, DIA, DXY, IXIC, KOSDAQ, KOSPI, SOXX, SP500, TNX, USDKRW. These each need source- and exchange-calendar-specific collection: BTC 24/7, Korea XKRX, FX weekdays, equity/XNYS; no false weekend-session fills.

## Automated read-only backfill **candidate stage**

On protected `main`, the pre-existing [market missingness audit](https://github.com/kimtk94/Codex/actions/workflows/kalman-market-missingness-audit.yml) now fetches two **explicitly allowlisted** original private Drive ZIP files, verifying Drive metadata, original MD5 and every internal SHA256 before computing any plan. The added `backfill_queue.py`:

1. **For 9 overlapping raw series**: verifies timestamps/date uniqueness, declared adjustment basis, true market-specific date counts, the current archive has genuine subsequent sessions, and 46 most recent overlapping session OHLC numbers for source repricing. Emits observed candidate row counts and separate **price-revision HOLD** statistics; candidates are *not* inserted into the old market ZIP. Even identical Yahoo bars do not independently certify 16:00 ET close or original issuer adjustment factors.
2. **For 10 market-only series**: emits `INDEPENDENT_SOURCE_REFETCH_AND_QC_REQUIRED`; no future-price fills, fabricated sessions, weekend-equity bars, or pretending Daily20 covers absent assets.
3. **For 12 FRED series**: emits `REFETCH_PUBLICATION_FREQUENCY_AWARE` with `latest_revised_NOT_ALFRED_PIT` and `point_in_time_training_eligible=false`. FRED economic release frequencies and holidays matter; do not fill sparse weekly/monthly releases as missing daily values. The existing USDKRW OHLC and FRED H.10 NULL masks remain active.
4. **For 19 technical feature tables**: source backfill first, then regenerate TA-Lib from correctly ordered complete input, retain warmup nulls and verify indicator source/runtime hashes. Never concatenate old-vintage features with new-vintage price corrections without a new model experiment.
5. **For long-history/legacy snapshots**: retain originals with their snapshot dates; the current 20 core symbols do not imply historical SP100 membership or one-hour source coverage. Separate vintage-proof backfill is required if these are promoted as research features.

The protected audit publishes **only JSON and CSV metadata** as GitHub Actions evidence (the same audit already emits calendar-based missing-date matrices). This is a staging/proposal, **not a completed price backfill**. The original 19+12 ZIP is untouched and remains research-not-PIT. No prospective Daily20 first-seal journal, model training sample, or LIVE operation is changed.

## Next gated recovery execution

First classify missing dates and source basis using the newly generated `backfill_plan.json` + `backfill_market_queue.csv` + `backfill_fred_queue.csv`. Then acquire complete, independent new raw bars for 10 absent assets and released/latest-revised 12 FRED series; attach source timestamps and per-asset SHA, certify adjustments or mark revised-feed HOLD. Only after that generate a **new versioned candidate market archive in a separate Drive object**, compare all new/overlapping historical prices, regenerate 19 features, run 2024–2026 walk-forward re-evaluation without lookahead and carry missingness gates. Explicit approval needed before replacing the old stable ZIP or enabling any training on revised macro series. No service account write permission is requested or expanded by this PR.

Prior archived 2026-11-20 QLD/QQQ dividends still need independent primary issuer proof; Daily20 0/26 official-close factor and 0/25 issuer-adjustment factor certification remain HOLD. Four-XNYS-session original prospective settlement is not backfilled by any historical recomputation.
