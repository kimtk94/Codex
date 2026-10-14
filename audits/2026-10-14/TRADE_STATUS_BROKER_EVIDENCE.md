# Kalman trade status discrepancy — broker telemetry vs Neon mirror

Audit date: 2026-10-14 KST
Scope: Neon production **SELECT-only evidence** and GitHub audit-branch-only patch. Not a LIVE deployment.

## VERIFIED read-only evidence
- Neon `public.trade_execution`: 96 rows; 75 `status=FILLED` from `managed_position` and 21 `status=SUBMITTED` from `order_guard`.
- In **all 21 SUBMITTED rows**, `metadata.execution_telemetry.broker_order` includes:
  - `status=FILLED`
  - broker order ID identical to `trade_execution.broker_order_id`
  - response metadata HTTP status 200
  - positive `filled_quantity` and nonempty `filled_at`
- However Neon `trade_execution.filled_quantity` and `average_filled_price` are NULL in **all 21** rows. They are present in the nested broker-order telemetry. These are mirror quality gaps, not evidence of 21 broker-open orders.
- All 96 Neon `trade_execution.updated_at` landed in the same 2026-10-14T13:00Z minute (22:00 KST), because `engine/trade_mirror.py` unconditionally sets `updated_at=now()` in its upsert. This timestamp is mirror sync provenance, **not a broker capture timestamp**.

## LRCX example, fills stored in Neon telemetry
- 2026-10-14 00:39 KST, BUY 0.025357 at $292.61, status FILLED, source managed_position
- 2026-10-14 01:39 KST, BUY 0.023677 at $299.44, status SUBMITTED but historical broker telemetry FILLED
- Sum 0.049034 shares equals Neon OPEN managed_position_mirror.remaining_quantity 0.049034.
- This supports inclusion of the second BUY in managed position aggregate **in the mirror**; it does not independently verify the present brokerage balance.

## Root cause in source (main, read only)
`kalman-toss-gateway/engine/trade_mirror.py` builds `pos_by_client` using only entry and exit client-order IDs. Unmatched orders return `order_guard.status` even when cached broker telemetry reports a completed fill. The mirror leaves `filled_quantity` and `average_filled_price` NULL for those records.

## Audit-only candidate patch
On `audit/kalman-control-20261014`:
- `kalman-toss-gateway/engine/broker_status_evidence.py` verifies historical broker fill with strict ID equality, status=FILLED, HTTP 200, positive finite filled quantity and timezone-aware filled timestamp.
- `kalman-toss-gateway/engine/trade_mirror.py` falls back to confirmed historical broker fill for unmatched SUBMITTED orders, sets `status_source=broker_order_telemetry`, and projects broker filled quantity/average price into the mirror.
- Never changes `order_guard.status` and still prefers managed-position entry/exit status when present.
- Offline GitHub Actions run 38569569243: **55 tests, OK**, audit branch only. https://github.com/kimtk94/Codex/actions/runs/38569569243

## Safety / release blockers
- Historical broker telemetry is not a real-time brokerage open-order snapshot. The actual current broker positions and open-order inventory are **UNKNOWN**.
- The offline patch **has NOT been deployed** and Neon Production values have **NOT been updated**.
- Before any production merge: compare dry-run diff of all 96 rows, validate fill ordering and corporate actions, confirm account-side positions/orders, check stale telemetry age/provenance, and obtain explicit live change approval.
- Avoid treating 96 historical FILLED telemetry records as 96 new trades or double-counting position add-ons.

Read-only SQL reproduction: `audits/2026-10-14/quality/provenance_audit.sql`.
