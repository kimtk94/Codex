# P1 audit finding: inflated net returns on multi-entry Kalman LIVE mirrored positions

Audit observed 2026-10-14 KST. **Read-only Production SQL**, GitHub audit-branch-only candidate patch. No Production DML, live order, deployment, or broker token access.

## 1. Scope and affected surfaces
- Neon `public.v_live_trade_ledger` reads **only** `managed_position_mirror`; it has one row per `position_id` and does not aggregate `trade_execution`. Thus a projection changing 21 historical SUBMITTED order statuses does **not** itself change the number of rows in `v_live_trade_ledger`.
- The checked GitHub *build script* `kalman-toss-gateway/scripts/build_investment_hub_v7424_execution_telemetry.py` generates `api/assets.js` querying `v_live_trade_ledger` and `renderExecutionLedger()` displaying `net_return` as '순수익'. The exact **deployed** Vercel source/version remains unverified.
- `strategy_ledger` is a separate ledger (at inspection: 251 BACKTEST and 17 LIVE_SHADOW) and should not be mixed with these live managed-position metrics without a clear provenance filter.

## 2. Critical net-return integrity finding
Neon read-only results at inspection:
- Managed positions: 40 CLOSED / 0 OPEN.
- 40 have price-only gross return, 36 have `v_live_trade_ledger.net_return`; 4 net values already NULL.
- Exactly **5 of the 36 reported net returns** are based on incomplete entry fill coverage: `metadata.execution_quality.entry.filled_quantity < managed_position_mirror.entry_filled_quantity`.
- An additional quantitative sanity check showed no corresponding mismatch in the other 31 for entry/exit total fill quantities. This is **quantity-coverage evidence only**, not complete external fee/broker verification.
- Displayed 36-position simple mean `net_return*100` = **+15.960%**. Restricting to 31 quantity-covered records gives a different-sample mean of **-0.191%**. These averages use unequal sample sizes, so they are not alternative 40-position portfolio returns; no weighted P&L is implied.
- Five worst positions:

| Symbol | Price-only gross | Currently reported net | Issue |
|---|---:|---:|---|
| INTC | -0.212% | +198.697% | first-entry notional 1/3 of total |
| INTC | +0.026% | +100.119% | first-entry notional ~1/2 |
| AMD | -0.940% | +97.929% | first-entry notional ~1/2 |
| QCOM | -2.719% | +93.881% | first-entry notional ~1/2 |
| LRCX | -1.689% | +89.842% | first-entry notional ~1/2 |

## 3. Root cause in read-only GitHub source
`engine/trade_mirror.py::_round_trip_quality(entry_quality,exit_quality)` uses the first entry-order telemetry's `exact_notional` as total entry cost; the exit amount uses total exit quantity. The multi-entry position's managed aggregate entry quantity and weighted entry price are NOT used for the denominator. Example LRCX:
- managed position entry 0.049034 shares at ~$295.908; exit 0.049034 at $290.91.
- entry quality covers just 0.025357 shares (cost basis ~$7.5033), exit quality covers 0.049034 (~$14.2645).
- naive net_return is therefore ~+89.842%, despite -1.689% price-only gross.
- Add-on fees are not guaranteed to be included in the first entry telemetry. Do not invent precise fee-adjusted net P&L.

## 4. Audit branch mitigation (NOT DEPLOYED)
- `kalman-toss-gateway/engine/trade_mirror.py`: `_round_trip_quality` now receives full position record; before returning a net figure, verifies entry AND exit observed telemetry fill quantities match aggregate managed position quantities to tolerance 1e-8 shares.
- If coverage incomplete: **net_return=NULL**, `net_return_pct=NULL`, `round_trip_cost_bps=NULL`, `quality_status=INCOMPLETE_LEG_COVERAGE`; preserves *price-only* gross from position aggregate entry/exit average prices. Does not add or alter trades or positions.
- If coverage complete and position CLOSED: uses existing net formula and records `quality_status=FULL_LEG_COVERAGE`.
- If position not CLOSED: suppresses net `quality_status=POSITION_NOT_CLOSED`.
- No new external/API calls, no LIVE deployment, no data migration.
- Tests: `audits/2026-10-14/quality/test_net_return_coverage.py` covers add-on, price return, single-entry, missing leg, open position, partial exit, tolerances, callsite. GitHub Actions run https://github.com/kimtk94/Codex/actions/runs/38574638515 : **70 tests OK**.
- Reproducible Neon SELECT-only SQL: `audits/2026-10-14/quality/net_return_coverage_audit.sql`.

## 5. Release gates
**P1 / RELEASE_HOLD** pending:
1. Verify deployed Vercel `api/assets.js` and actual UI query against source; historic builder script isn't deployed-source proof.
2. For 5 multi-entry positions, reconstruct each add-on fill, commission/tax (fees across legs) and cash flows from an independently sourced event ledger; only then calculate fee-adjusted net return.
3. Validate 40 real managed positions in isolated read-only replay; add partial exits, corporate actions and same-day turnover cases.
4. Test UI missing-value rendering as 'unavailable/needs reconstruction' and never convert NULL to 0% or display misleading +90~199% values.
5. Get explicit user sign-off and deployment/runtime SHA attestation before any LIVE server/Neon/Vercel modification.

## 6. Caveats
- The **five corrupted net fields currently remain in Neon Production** because audit is SELECT-only.
- The current price-only gross return is based on mirrored entry/exit average prices and is NOT an independently reconciled broker statement.
- The 31 remaining net figures have leg quantity coverage, but they have not been independently reconciled to current account statements.
- `v_live_trade_ledger.realized_return_pct` is a *fraction* despite the column name (to show percent multiply by 100), consistent with the frontend's `pct(gross,100)`.

**Overall verdict:** Dashboard row-count duplicate risk from the 21 historical status corrections is conditional on consumer query; **proven P1 net-return inflation for 5 managed positions** demands a production-release hold.
