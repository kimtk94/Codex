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

`.github/workflows/kalman-daily20.yml` runs at 02:40 UTC Tue-Sat, manually by `workflow_dispatch`, and as a PR validation. There are no secrets or server credentials. Data refresh and training artifacts persist for 21 days in GitHub Actions, not in a server.

To run offline contracts: `python -m unittest discover -s research/kalman_daily20 -p 'test_*.py' -v`

The workflow:

1. Verifies universe schema and builds a derived 26-asset config without changing canonical `market-data-v2-universe.json`.
2. Downloads full US daily data using existing research collection code, no LIVE writes.
3. Computes existing TA-Lib features and checks each symbol's freshness, OHLC integrity, and feature availability.
4. Runs **fixed-parameter** per-symbol annual expanding out-of-sample logistic baseline (first test year 2024, four-session label purge, imputation/scaling fit only on the training window).
5. Reports per-symbol and per-year non-overlapping trade outcomes with 20bp total modeled cost. Does **not** claim a tradable portfolio MDD or independently replicate a QLD 15-minute entry.
6. Uploads QC and aggregate research artifacts. A missing, stale, or incomplete symbol blocks the training step.

## Known limitations / next gates

- Full-history requests are intentionally slower than incremental refresh; improve by private immutable data store with revisioned daily increments **after** stable initial runs.
- Model labels refer to a 4-session *daily* hold, not a 4-day intraday triple-barrier; this is a baseline only. True minute-level TP/SL requires verified 1-minute bars.
- We have **not yet established profitable out-of-sample performance**. No trading order is generated.
- Additional model families, regime attribution, hyperparameter tuning (nested CV), independent provider reconciliation, portfolio-level costs/exposure/MDD, and private Drive persistence are future milestones.
