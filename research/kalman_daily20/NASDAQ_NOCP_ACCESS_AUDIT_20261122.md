# Nasdaq NOCP access audit for the current 16 Nasdaq venue hints — 2026-11-22

**Research only; 7/10 implementation milestones (70%); three core acceptance gates remain.**
This is an access study, not a reconstruction of 2026-11-20 NOCP prices.

## Primary publisher findings

- [Nasdaq Historical NOCP](https://www.nasdaq.com/market-activity/quotes/historical-nocp) identifies NOCP as a Nasdaq market-center-specific price. Nasdaq's [official listing FAQ #272](https://listingcenter.nasdaq.com/Material_Search.aspx?cid=71&mcd=lq&sub_cid=118,98,96,99,100,94) explicitly distinguishes the official closing price from other closing-price definitions.
- Public AAPL, NVDA, MSFT, and QQQ `historical-nocp` URLs showed the message **"Data is currently not available"** in the readable page. This alone does not mean a registered browser, client-side API, or subscription never has data.
- [Nasdaq Fundamental Data](https://nasdaqtrader.com/Trader.aspx?id=FD) explicitly includes **NOCP** separately from **Daily Last Sale Price**, as T+1 security master/market summary data. The current business month's files require an **approved monthly subscription and secure website/FTP login**. No subscription or exchange credential is currently configured in this repo. Do not automatically purchase, invent access, or scrape protected endpoints.
- [Nasdaq Basic Data Link NBPL](https://data.nasdaq.com/databases/NBPL) lists NOCP as a data component, but subscription scope, entitlement, exact history and data license **are not validated**. Do not equate its other OHLCV Bars endpoint with NOCP.
- Current primary-exchange routing in real [main #45028860891](https://github.com/kimtk94/Codex/actions/runs/45028860891): **16 Nasdaq, 3 NYSE, 6 NYSE Arca, plus ^VIX index** for 2026-11-20. Venue names come from a **current** Alpaca listing master, not contemporaneous historical proof. A transfer may legitimately change future counts.

## GitHub Actions integration

`nasdaq_nocp_access_audit.py` consumes the existing official-access JSON report and 26-asset universe, checks 16 Nasdaq candidates for the currently frozen 2026-11-20 date, and generates:
- `research/nasdaq_nocp_access/report.json`: immutable-as-run file SHA256s, official subscription links, per-symbol page status, no numeric NOCP admitted
- `research/nasdaq_nocp_access/public_portal_probe.csv`: exact per-asset access observations and source body hashes when available.

For protected `main` first-session runs (and explicit dispatch/push), it tries **one** unauthenticated public `historical-nocp` HTML page per currently Nasdaq-listed ticker. At most four bounded concurrent requests are made. The second same-session replay (04:40 UTC) and PR runs are **offline**, and merely generate a pending-HOLD access register.

An HTTP 200, a price-looking number inside HTML, general Nasdaq history, a Yahoo daily bar, and an Alpaca SIP M print **cannot** satisfy the NOCP numeric-data contract. A 403/429/timeout/redirect/empty response is recorded as a per-symbol access HOLD without overwriting any price or aborting unrelated market research. No code extracts prices from HTML, uses scraped prices in prediction, or changes the immutable 2026-11-20 observations.

This stage is placed **after** `official_close_source_access.py` and **before** unrelated issuer and OOS research. It requires 26 upstream access rows, no certified prices/factors, exact row/session identity, 16 frozen-date routes, and 16 probe records if the network test is requested. Any upstream claim of certification, duplicated symbol, wrong session or unknown probe symbol raises an error. PR regression tests simulate browser placeholders, misleading numeric HTML, all-blocked pages, and future venue transfers without network calls.

## Evidence required to complete this gate

1. Authorized **Nasdaq exchange original** dated NOCP data for all 16 on target session; collect source ID, subscription entitlement, extraction timestamp, official primary venue and unadjusted USD unit basis. No substitution from consolidated SIP last sale or generic historical OHLCV.
2. Separate independent 16:00 ET raw price and 25 issuer-verified corporate action factor chains; verify bridge to Yahoo adjusted/repaired model inputs. Corroboration does not automatically grant official finality until provenance and meaning agree.
3. Keep 2026-11-20 first sealed 60 forward signals immutable, and await genuine 2026-11-23 prospective seal and November 27/30 XNYS settlement dates. Source certification and forward alpha are distinct.

**Consequence:** Successfully probing 16 public URLs advances access visibility but cannot increase the **0/26 scientific finality** count or the **7/10 implementation milestones**.
