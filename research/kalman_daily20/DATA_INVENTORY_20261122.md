# Kalman Daily20 — data inventory and progress (2026-11-22 KST)

**Scope:** 20 US stocks/ETFs, serverless daily research only. Operational PASS is separate from strategy approval. No web, Toss, Neon, or live trading changes.

## Latest verified Daily20 run

[GitHub Actions #45003032896](https://github.com/kimtk94/Codex/actions/runs/45003032896) succeeded on 2026-11-22, for the 2026-11-20 US session. The contracts, Drive restore, daily research, and Drive publisher jobs all succeeded, including remote readback.

Core 20: SPY, QQQ, QLD, IWM, AAPL, MSFT, AMZN, GOOGL, META, NVDA, AMD, AVGO, MU, TSLA, PLTR, IONQ, COIN, MSTR, JPM, XOM. Context-only 6: SMH, ^VIX, HYG, LQD, TLT, GLD. [Universe config](universe.json).

The run logged 26 asset refreshes, 1,499 per-symbol OOS research trades, 20 research scores, 16 portfolio scenarios, 20 bear-challenger scenarios, and 114 Monte Carlo result rows. Representative simulated 2024+ cumulative returns (5 maximum positions, 20bp modeled total costs): Logistic all-20 **-24.173%**, EOD MDD **-27.918%**; Logistic without QLD/IONQ/COIN/MSTR **+5.903%**, EOD MDD **-14.651%**. No winner may be selected as tradable based on this comparison.

**Critical HOLDs:** 0/26 independent official regular closes certified; 4 replay stability incidents; 20 frozen forward-shadow replay drifts; 0 forward signals settled. Primary-exchange M-print selection of 25/25 is not independent regular-close or dividend adjustment certification.

## Source-of-truth data locations

| Data | Location | Evidence and state |
| --- | --- | --- |
| Current Daily20 market archive | [Drive data ZIP](https://drive.google.com/file/d/1nWbyCiRSscJSqgZYvYhJ9DKHRlBwlKgE/view) | Modified Nov 22 08:32 UTC; 26 assets, CI verified as-of Nov 20; research-grade source |
| Current model, OOS and forward outcomes | [Drive results ZIP](https://drive.google.com/file/d/1l-e4OLKS4qlDjNsf8TdkMsd5w3QouF4w/view) | Modified Nov 22 08:32 UTC; Drive readback verified; scientific HOLD |
| Historical immutable action archives | [Drive archived evidence](https://drive.google.com/drive/folders/1txOxTaWBo-2Ilns9dedk6SruGpoKl-6p) | Nov 20 run snapshots backed up Nov 21; preserve SHA and old prices |
| Existing full inventory workbook | [Drive inventory spreadsheet](https://drive.google.com/file/d/11A8Iyg3M5r-9Tx05--DHAtet1SLegQcG/view) | Nov 21; existence verified, content not reaudited here |
| Legacy aligned QLD/QQQ day bars | [Drive CSV](https://drive.google.com/file/d/1v9mM0l0-jLpXu81v6wfwJXHK3kSREsL-/view) | 2,432 rows; 2017-01-03 to 2026-09-04; stale |
| Legacy ETF latest bars | [Drive CSV](https://drive.google.com/file/d/1331d3hAjNx-81rr6kfEGe30Kz5nQIutH/view) | 10 rows; last 2026-09-04; stale |
| S&P 100 membership | [Drive snapshot](https://drive.google.com/file/d/18LCkOKDp1J5YTTCFiaT4BUBASPMiRUDk/view) | 2026-09-01 101-ticker snapshot; not current |
| Long daily Parquet | [Drive history_1d](https://drive.google.com/drive/folders/1k8pziSSrTcPbSNwPd4E40n-J9Uj6Y1hB) | 5 historic ticker data files, last modified Aug 31 |
| Long hourly Parquet | [Drive history_1h](https://drive.google.com/drive/folders/16HdGCP3FBM10ssPz51vlFSl6J71zASCs) | 68 files including many QQQ revision backups, not 68 unique symbols |
| Broader market and macro ZIP | [Drive latest market ZIP](https://drive.google.com/file/d/1aUhvIAsE2x2-LuKv5nSxmDGX0Uo4mqYd/view) | Last modified 2026-10-31; stale; FRED current-revision history is not PIT |
| Archived V7/V8 testing | [Drive model tests](https://drive.google.com/drive/folders/1R2pJb0E-HttK6rF_aL9JuKpkOCxpwxqO) | Nov 15 files; results not recertified here |
| Issuer distributions and listing evidence | [Issuer sources](issuer_ca_primary_sources.json) and [listing references](historical_listing_sources.json) | Cash amount/corporate-action adjustments not independently certified |

Do not use legacy exports as the current 20-symbol signal input. The latest data and results ZIPs are the canonical research persistence, not a price feed certified for orders.

## Completion checklist: 7/10 implementation milestones = 70%

- DONE: fixed 20 core + 6 market context; 26-asset daily update; fail-closed technical feature/OHLCV QC; Drive cache restore/publish/readback; annual purged OOS; portfolio/regime scenario analyses; Monte Carlo sensitivity engine.
- HOLD: independently certified 26 regular closes and adjustments (0/26); stable frozen replay and source-vintage lineage (4 incidents and drift); matured forward data and human-approved strategy (0 settled).

This equally weighted 70% is **implementation coverage**, not prediction accuracy, market-source integrity, model validity, or percentage of investment readiness. Research approval remains HOLD.

## Highest priority remaining work

1. Pursue source-corroborated payout information for QQQ 2018-06-18 and QLD 2023-09-20; keep CASH_HOLD if the first-party cash amount and split-unit conversion cannot be certified.
2. Certify 26 regular 16:00 market closes and price/corporate-action factor lineage; keep raw, adjusted and vintage versions separate.
3. Eliminate unexplained same-session OHLCV/feature changes and frozen-score replay drift; accumulate mature prospective signals before any strategy decision.

## New independent monitoring workflow in this PR

The new read-only workflow triggers after Daily20 finishes, has a Tue-Sat 04:15 UTC backup schedule, and can be dispatched manually. It reads GitHub Actions jobs/log evidence only, publishes an ops_readiness.json artifact and run summary, and reports operational PASS independently from research HOLD. It makes no Drive, broker, order or strategy writes. Automatic scheduling starts **only if merged into main**.
