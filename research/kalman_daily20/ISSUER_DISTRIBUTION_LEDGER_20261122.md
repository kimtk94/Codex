# Daily20 unresolved issuer distribution events — source-grade ledger (2026-11-22)

This is a **research-only, date-bounded evidence ledger**. Corporate-action factor promotion and daily trading signals are forbidden by this note. The full original-source bytes and SHA-256 are stored in the Daily20 results archive when source retrieval succeeds.

| Case | Proven source | Observed amount | Evidence scope | Outcome |
|---|---|---|---|---|
| QQQ 2018-06-18 | [Invesco QQQ FY2018 SEC-filed annual report](https://www.sec.gov/Archives/edgar/data/1067839/000119312518355790/d638310dn30b2.htm) | **$1.31 per share for FY ended 2018-09-30** | Aggregate across fiscal year. Not a one-day payout. Annual row hashed and verified in `issuer_qqq2018_fiscal/report.json` when available | **Specific June cash amount HOLD** |
| QQQ 2018-06-18 | [Original sponsor/trustee ex-date amendment](https://www.sec.gov/Archives/edgar/data/1067839/000119312518023862/d423471dex99a3f.htm) | No amount | Ex-date rule implies 2018-06-18, not declared/paid cash | **Specific June cash amount HOLD** |
| QQQ 2018-06-18 | SEC-hosted later third-party structured-note table, Tiingo and other vendors | $0.37837 candidate; a conflicting lower-precision $0.3764 source also exists | Third-party event or quarterly table, not direct first-party event payment record | **Reconcile original issuer payment note before certification** |
| QLD 2023-09-20 | [ProShares issuer year-scoped API](https://www.proshares.com/api/distributionsummary?fund=QLD&year=2023) | Latest inspected response showed only Dec 20 row | Coverage gap: missing Sep row is *not evidence of nonpayment* | **September cash HOLD** |
| QLD 2023-09-20 | [ETFIQ QLD payout history](https://etfiq.com/funds/qld/dividends/) and [StockAnalysis](https://stockanalysis.com/etf/qld/dividend/) | $0.176282 unadjusted candidate; $0.08814 adjusted candidate | Third-party, approximate 2:1 split math; 2025 issuer Form 8937 certifies split context only, not 2023 cash | **Split-adjustment factor HOLD** |

## Machine-checkable controls

- The FY2018 report parser checks a 2018 Financial Highlights table, its fiscal-year columns, the net investment income distribution row, original HTML bytes and SHA-256. It does **not** interpret the $1.31 annual number as the 2018-06-18 dividend.
- Pull-request tests use offline fixtures and no issuer network access. The protected main workflow fetches the pinned historical report, records the response SHA and archives raw bytes to `output/daily20/research/issuer_qqq2018_fiscal/` (subsequently included in the existing Google Drive **results** ZIP).
- Network outages, source body changes, missing year/row and conflicting records fail into HOLD states, not an invented paid cash amount.
- No changes to OHLCV, Yahoo auto-adjust policy, OOS labels, portfolio selection, model weights, strategy promotion or broker execution.

## Closure evidence required for either case

A direct issuer/fund trustee record confirming the **exact event date, declared/payable amount, share-unit basis**, and independently reconciled split/dividend adjustment chain. Separately certify raw 16:00 regular-session closing prices. Until then, **0/26 source-finality certified and research HOLD** remain valid.
