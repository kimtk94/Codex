# Kalman Daily 20 (research only)

A serverless, independent 20-symbol US daily research track. It does **not** deploy a web app, connect to Toss, update Neon, or change R5/R5.2 production code.

## Universe and data

- Core symbols: the **exactly 20** symbols in `universe.json`. Fixed as of 2026-11-21 (ex-post selection; beware survivorship / selection bias in historical tests).
- Context: SMH, ^VIX, HYG, LQD, TLT and GLD; **not trading candidates**.
- One canonical US daily close signal per session; earliest simulated entry is the **next session's daily open**; initial reference holding horizon is exit on the **fourth subsequent session's close**.
- Price source: existing Kalman YFinanceProvider, `auto_adjust=True` for stocks and ETFs; VIX unadjusted. Data are **research-grade Yahoo data, not exchange-grade certified quotes**. Corporate actions and revisions can change old adjusted prices.
- The existing `engine.features_v2_002.cli` builds TA-Lib RSI/MACD/ADX/NATR/Bollinger/ROC etc. The research code builds extra trend, momentum and volume features.
- Context series are lagged **one full US session** to avoid optimistic synchronization; no current-revision FRED values are used as historical point-in-time features.
- Every core and context symbol must pass freshness and OHLC QC; a single failure marks the run BLOCKED (fail-closed). The latest *fully closed* XNYS session with an additional 45-minute buffer is used, not the wall-clock date.
- Do not infer trade execution from a successful Actions job. The model run generates **research signals and retrospective OOS summaries only**.

## Workflow

`.github/workflows/kalman-daily20.yml` runs at 02:40 UTC Tue-Sat, manually by `workflow_dispatch`, and as a PR validation. Production credentials are not used. The serverless Drive restore/publish jobs use a scoped Google service account; the historical data and result archives persist in Drive, with short-lived GitHub artifacts only as handoff.

To run offline contracts: `python -m unittest discover -s research/kalman_daily20 -p 'test_*.py' -v`

The workflow:

1. Verifies universe schema and builds a derived 26-asset config without changing canonical `market-data-v2-universe.json`.
2. On main-branch scheduled/manual runs, restores the private, SHA-256-verified Google Drive history using a credential-isolated job; performs a 46-day overlap update except Saturday full-history reconciliation or detected price-scale revision. PR jobs do a full-history refresh with no Drive secrets. No LIVE writes.
3. Computes existing TA-Lib features and checks each symbol's freshness, OHLC integrity, and feature availability.
4. Runs **fixed-parameter** per-symbol annual expanding out-of-sample logistic baseline (first test year 2024, four-session label purge, imputation/scaling fit only on the training window).
5. Reports per-symbol and per-year non-overlapping trade outcomes with 20bp total modeled cost. Does **not** claim a tradable portfolio MDD or independently replicate a QLD 15-minute entry.
6. Uploads QC and aggregate research artifacts. A missing, stale, or incomplete symbol blocks the training step.

## Known limitations / next gates

- Incremental history uses 46 calendar days of overlap and full-history refetch each Saturday UTC or on adjusted-price-scale discrepancies. The latest Drive ZIP is updated in place; use Google Drive file revisions to retain recoverability. A failed cache download blocks the run rather than silently downgrading data provenance.
- Model labels refer to a 4-session *daily* hold, not a 4-day intraday triple-barrier; this is a baseline only. True minute-level TP/SL requires verified 1-minute bars.
- We have **not yet established profitable out-of-sample performance**. No trading order is generated.
- Additional model families, regime attribution, hyperparameter tuning (nested CV), independent provider reconciliation, portfolio-level costs/exposure/MDD, and private Drive persistence are future milestones.


## Durable Google Drive persistence

The primary Daily20 data store is now **Google Drive**, not an expiring GitHub Actions artifact. The existing artifact is only a temporary handoff.

- Folder: https://drive.google.com/drive/folders/1kJLk8sC2GDjtJjsdjeV-GhzsMYsFBhz7
- Immutable ID for current data ZIP: `1nWbyCiRSscJSqgZYvYhJ9DKHRlBwlKgE` (`daily20_data_latest.zip`)
- Immutable ID for current OOS results ZIP: `1l-e4OLKS4qlDjNsf8TdkMsd5w3QouF4w` (`daily20_results_latest.zip`)

GitHub Actions `persist-google-drive` runs only after `daily-research` succeeds and only on scheduled/manual runs, never untrusted pull requests. It downloads the freshly validated artifacts, checks 26 raw + 26 feature Parquet files and 20 scores, adds a reproducibility manifest (source commit, run ID, session, per-file SHA-256), and replaces only these two pre-shared research-only Drive files. A Drive MD5 readback is required. Failures leave a visible red CI job; no live trading, Neon, or server dependence is introduced.

Auth: existing `CKD_DRIVE_SA_JSON` or `GDRIVE_SA_JSON_B64` from the GitHub `TaehoonServer` environment. The publisher rejects an unexpected service-account identity. It must not use account-number or trading credentials. The two Drive files have writer access for that **specific** automation service account; the parent folder does not need to be shared.

No Google Sheets cells are used to store the long OHLCV time series; CSV summaries can later be synced into a small readable Sheet without changing the authoritative Parquet snapshots.


## Daily data incremental and secondary checks (v2)

1. The `restore-drive-cache` GitHub job has access only to the scoped research Drive account and downloads `daily20_data_latest.zip` by a fixed file ID. It verifies Drive MD5, archive path hygiene, every per-file SHA-256 from the manifest, and the exact 26 raw symbols. A separate short-lived Actions artifact carries this validated archive to the data job, **not credentials**.
2. The `daily-research` job uses `refresh_incremental.py` to fetch the most recent 46 calendar days from Yahoo, compares adjusted overlapping OHLC prices, and merges new timestamps with old history. A median repricing above 0.25%, a 95th-percentile repricing above 1%, or insufficient overlap triggers **a full 2017-present refetch**, avoiding inconsistent corporate-action adjustment scales. Missing snapshots or bad hashes fail closed.
3. Saturdays UTC (after the Friday US close) force a full-history revision reconciliation. Pull requests remain public-data-only full downloads, never consuming Drive credentials.
4. `secondary_qc.py` attempts an advisory 100-day FinanceDataReader comparison for SPY, QQQ, NVDA, XOM. It compares daily returns, explicitly labels provider independence **unverified** (FDR may use Yahoo internally), and reports unavailable data or disagreements separately. The primary data and models are not silently replaced by secondary quotes.
5. The canonical Google Drive two-file output IDs and existing production models remain unchanged. See `market/refresh_mode.json` and `secondary_qc.json` in the result artifact for provenance.

This is a data engineering milestone, not proof of strategy profitability or independent exchange-quality market quotes.
 

## Portfolio-level, out-of-sample cash ledger

`portfolio.py` runs **after** 20-symbol OOS trade generation but **before** research artifact publication and Drive updates. All 20 names compete for the same finite account. It does not trade live.

- Date scope: 2024 onward (all trades remain anchored to annual expanding, label-purged OOS forecasts). Uses only completed historical trades; the last unobservable four-session horizon cannot be treated as completed.
- At most 3 or 5 open long positions; gross target allocation 1/N with no borrowed money. Fractional shares, 0% cash interest. Current-session open marks are used for same-open sizing.
- Open at the next US session with half of the specified round-trip friction; exit at the predeclared fourth-session **close** with remaining half. Sale proceeds at close cannot finance entries at the earlier open.
- Same-open simultaneous entry competition: Logistic candidates ranked by their fixed OOS predicted probability, trend-rule candidates by the known 20-session closing-price momentum at signal date, then alphabetic ticker tie-break. Recomputed historical gross returns are reconciled against the existing out-of-sample label file; mismatches fail closed.
- 16 **predeclared** scenario combinations: `LOGISTIC` vs `TREND_RULE`, all-20 vs excluding QLD/COIN/MSTR/IONQ, maximum 3 vs 5 holdings, 20 vs 40 basis-point total modeled execution friction. This grid is diagnostic, not an ex-post champion selection.
- Exports `research/portfolio_scenarios.csv`, `research/portfolio_annual.csv`, `research/portfolio_daily_equity.csv`, `research/portfolio_executions.csv`, `research/portfolio_summary.json`. The existing Drive results ZIP automatically carries these files; publishing is blocked if any are missing.
- Metrics include annualized return, calendar-year returns, **end-of-day** equity MDD, annualized daily volatility, zero-risk-free Sharpe, active-day and average exposure, executed and rejected entries, SPY and QQQ buy-and-hold from first study date, plus signal-regime/volatility/tech-leadership attribution.

### Critical interpretation

All recorded baseline entry signals are **BULL-only** because the OOS candidate generator already filters on prior-session SPY>SMA200 and VIX<=35. Entry-regime BEAR performance therefore has **no observations**, even if the daily portfolio equity experiences bear sessions while holdings are open. Do not report bear-regime alpha.

EOD MDD misses intraday drawdowns, gaps, market impact, bid-ask volatility, borrow/funding and market-open delay. Holding fractional shares and buying leveraged QLD at adjusted open are sim assumptions, not verified broker fills. Benchmark assumes first-session-close purchase with no transaction costs; this comparison is imperfect but transparent.

The 2026-chosen fixed list creates historical survivor/selection bias; per-year and stress outcomes are descriptive and cannot certify forward alpha. No strategy auto-promotion: `tradable_strategy_approved=false`.
