# Kalman multi-leg cash-flow reconstruction — independent offline gate
Recorded: 2026-10-15 KST. Audit-only. **No actual broker reconciliation, production code changes, or Neon DML.**

## Objective
Prevent the known 5-position P1 inflated net-return problem (first BUY tranche denominator vs total SELL proceeds). Calculate historical fee-adjusted return only where **all** buying/selling events, the linkage, and every event's fee basis have been independently verified.

## Implementation
- Pure module: `audits/2026-10-14/quality/multileg_cashflow.py`.
- Tests: `audits/2026-10-14/quality/test_multileg_cashflow.py`.
- Neither uses production services, API tokens, network, databases, disk writes, nor `trade_mirror.main`.
- Accepts an externally attested, complete broker order-ID manifest; refuses to calculate if missing, duplicate, or inconsistent with supplied fills.
- Requires explicit order->position link basis (initial/exit client order ID or future explicitly persisted position ID). Symbol/time correlation is **not sufficient**.
- Requires matching broker order ID in telemetry, terminal FILLED evidence, HTTP 200, positive finite quantity and price, timezone-aware execution time, explicitly recorded nonnegative commission and tax, and matching fee/trade currencies.
- Rejects duplicate orders, missing legs, sells before available buys, unbalanced cumulative quantities, mismatched position aggregate entry/exit quantities and weighted prices, open positions and negative/missing fees.
- Uses exact Decimal arithmetic, returns native-currency entry/exit notional, fees, gross/net P&L and net return.
- Does NOT estimate FX, exchange-rate slippage, account P&L or current outstanding orders.

## Verification
Final Actions run: https://github.com/kimtk94/Codex/actions/runs/38594348592
**Completed/SUCCESS, 121 tests, OK.**
An earlier CI iteration had one faulty test assertion: removal of the second buy triggered the earlier oversell guard, which is correct. Updated and validated. Subsequently strengthened the tool to require an independently sourced complete order-ID manifest.

### Synthetic LRCX-shaped test (NOT actual fees)
- BUY 0.025357 at $292.61
- BUY 0.023677 at $299.44
- SELL 0.049034 at $290.91
- Historical gross USD P/L: -$0.24507171.
- The test assigns hypothetical fees of **$0.01 to each of the three orders**, producing illustrative net P/L of **-$0.27507171**.
- This **is not actual LRCX net P/L**, nor a broker-confirmed order inventory.

## Production blockers / status
1. No independently attested complete order-ID manifest for the five historical multi-entry positions. Historic 21 unmatched orders may contain fills but still lack enduring explicit position links; no inference by symbol/time.
2. Real per-order commission and tax completeness for each of the 5 positions is not established.
3. No validated live broker inventory or exact deployed runtime SHA.
4. The current Neon Production `v_live_trade_ledger.net_return` values for the 5 positions remain overestimated. 31 other covered values have not been externally broker-audited.
5. The offline calculator **is not wired into LIVE trade mirror**, and should not be until a staging replay and production approval.

**Verdict:** `OFFLINE_PNL_GATE_PASS / HISTORICAL_5_POSITIONS_UNVERIFIED / PRODUCTION_RELEASE_HOLD`.

## Related findings
- `NET_RETURN_OVERSTATEMENT_P1.md` — five affected positions, root cause and anomalous percentages.
- `FUTURE_ADD_ON_POSITION_LINK_V1.md` — future position ID evidence.
- `quality/net_return_coverage_audit.sql` — read-only completeness checks.
