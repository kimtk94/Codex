# Official primary close publisher routes and Cboe VIX revision recheck — 2026-11-22

**Implementation 7/10 (70%); all 26 price finality decisions remain HOLD.**
This control is research-only. It is **not** a substitute for a licensed exchange session-close feed or for issuer-attested adjustments.

## Source product feasibility verified from publishers

| Venue/asset | Primary publisher product | URL | Current pipeline status |
|---|---|---|---|
| Nasdaq listings | Nasdaq Official Closing Price (NOCP) | https://www.nasdaq.com/market-activity/quotes/historical-nocp | Product exists; **no authenticated dated numeric NOCP feed connected** |
| NYSE, NYSE Arca, NYSE American | NYSE TAQ Closing Prices | https://www.nyse.com/data-products/catalog/taq-nyse-closing-prices | Published EOD records; historical file requires **licensed access** (NYSE page offers Purchase Now) |
| Cboe BZX | Cboe BZX auction / official closing summary | https://www.cboe.com/markets/us/equities/market-statistics/auction | Auction publication path known; historical dated authenticated BZX closing feed **not connected** |
| ^VIX | Cboe VIX Index Historical Data | https://www.cboe.com/tradable_products/vix/vix_historical_data | Public CSV accessible to automated read-only fetch; latest original and later dated close values re-compared on protected main; **no standalone certified 16:00 clock record** |

Nasdaq historical NOCP website may show "Data is currently not available": a product's existence does not establish programmatic historical numeric data access. Nasdaq/Nyse/Cboe documented exchange venues are **routing clues from Alpaca's current asset master, not proof of 2026-11-20 point-in-time listing**. Avoid hardcoding historical listed venues. `Cboe Market Close` matched executions for non-Cboe listings are not the home listing exchange's own closing auction.

## New automated evidence

`official_close_source_access.py` reads the exact session's existing `independent_feed.json`, `selected_reference.json`, `venue_identity.json`, `official_price_proof_obligations/report.json`, plus `universe.json`. It validates 26 unique assets, route coverage for all 25 equities/ETFs, zero finality/corporate factor promotions and matching current vendor M-selection statuses. Every input file is SHA-256 fingerprinted.

For **^VIX only**, protected main fetches the public Cboe raw history again, parses the exact previous US session with the existing strict parser, compares **the dated close value**, and records both original and new response SHA-256. Appending a new date changes the full CSV hash but not necessarily the old date's close, so a hash difference alone is **not** a revision. Any changed prior-day value is `CBOE_HISTORICAL_PUBLISHER_REVISION_HOLD` and is never overwritten. A Cboe outage is explicit `NETWORK_UNAVAILABLE_HOLD`. Original and later captures from the **same publisher do not establish two independent sources**.

Original public raw Cboe response is compressed into deterministic `cboe_vix_public_source.csv.gz` with a separate compressed-byte hash. Outputs live inside the research artifact and existing validated Drive ZIP:
- `research/official_close_access/report.json`
- `research/official_close_access/cboe_vix_public_source.csv.gz` when online source retrieved

PR CI does not fetch remote data and tests the same audit with synthetic indexed CSV histories. Protected main only uses public Cboe URL; no subscription request, additional API credential, order endpoint, price mutation, historical signal re-seal or live trading.

## Required scientific acceptance

1. A **properly licensed** primary exchange close per 25 stocks and ETFs with a verified session timestamp and primary venue identity; quote conventions (raw M / NOCP / TAQ last) must be compared on correct basis.
2. Primary issuer split/dividend ex-date and unit-basis reconstruction; QQQ 2018-06-18 and QLD 2023-09-20 stay specific HOLD cases.
3. Repeated prospective original first seal, stable same-session replay, and matured fourth-session outcomes before promotion.

**Do not advance scientific completion or the 7/10 milestone simply because this control or GitHub Actions succeeds.**
