# Daily20 price-basis and provenance bridge — 2026-11-22

**Research only. All 26 assets remain finality HOLD until an authenticated, independently certified consolidated or exchange regular-session close and an independent split/dividend adjustment factor are both documented.**

## Purpose

Four distinct series have different semantics:

| Series | Precise source | Stored field / output | Interpretation |
| --- | --- | --- | --- |
| Market-center closing auction | Alpaca SIP primary-listing exchange-selected M condition | `raw_primary_M_auction_price` | Raw M auction reference, **not a certified consolidated closing price** |
| Yahoo un-repaired Close | yfinance `history(auto_adjust=False, repair=False)` | `vendor_unrepaired_split_adjusted_close` | Yahoo split-adjusted price, **not independently attested raw price** |
| Yahoo un-repaired Adj Close | Same Yahoo download | `vendor_unrepaired_dividend_adjusted_close` | Dividend + split adjusted; `Adj Close / Close` is **same-vendor derived** |
| Daily20 model close | Archived auto-adjusted research Parquet; original provider has repair policy | `model_input_auto_adjust_close` | Actual model input, may differ from un-repaired Yahoo diagnostics |

### Code and files

- Analyzer: [price_basis_bridge.py](price_basis_bridge.py), test: [test_price_basis_bridge.py](test_price_basis_bridge.py).
- Input proof (all already in pipeline): `output/daily20/research/source_finality/report.json`, `source_finality/venue_identity.json`, `factor_lineage/report.json`, and each available hashed `factor_lineage/<ticker>.csv.gz`.
- Output: `output/daily20/research/price_basis_bridge/report.json`; automatically in GitHub `kalman-daily20-research` artifact and, after a protected main Daily20 success and Drive verification, in the existing [Google Drive latest results ZIP](https://drive.google.com/file/d/1l-e4OLKS4qlDjNsf8TdkMsd5w3QouF4w/view).
- The analysis reads **26 source-finality rows**, **25 venue rows**, and **25 Yahoo lineage rows**, records each vendor CSV's SHA-256 (checked against the decompressed original bytes), and emits 26 documented asset records including **^VIX** as a separate index with no stock split/dividend adjustment factor.
- Mismatched source sessions, conflicting raw M venue/reference prices, invalid or tampered vendor CSV hashes, duplicate symbols, invalid price values, or mixed adjustment semantics are hard errors that block publication. Lack of a Yahoo trace or unavailable M venue is explicitly marked HOLD without inventing a price or an adjustment factor.
- The indicator `research_raw_M_minus_vendor_close_usd` is **diagnostic only**. It is *not* a certified exchange-vs-Yahoo discrepancy since Yahoo historical Close can already be split-adjusted. `model_minus_vendor_adjusted_usd` is diagnostic of different data collection/repair snapshots, not proof of Yahoo correction.
- Do **not** divide or multiply historical prices by this Yahoo-only ratio to construct certifiable execution prices.

## Closing the scientific gate

1. Confirm the venue's **official 16:00 regular session close** for each of 25 stocks/ETFs and Cboe official index publication for VIX. Primary venue `M` is useful but not necessarily consolidated official price.
2. Independently attest split and ex-date cash distributions with issuer/fund transfer-agent documents, original unit basis, and time-bounded mapping; especially unresolved QQQ 2018-06-18 and QLD 2023-09-20 event cash.
3. Reconcile source evidence against **raw**, **split-adjusted**, **dividend-adjusted**, and model **repair-adjusted** versions without rewriting stored signal history. Keep any unresolved asset/source factor HOLD. Forward OOS validation remains separate.

## Progress

Daily20 overall remains **7/10 implementation milestones (70%)**. This module improves evidence lineage within one unresolved milestone, not a new completed milestone; **research source certification is still 0/26**. An operational success of this new diagnostic never authorizes live orders or model promotion.
