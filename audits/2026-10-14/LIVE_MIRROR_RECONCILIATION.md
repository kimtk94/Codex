# Live mirror reconciliation — 2026-10-14 (read only)

## Observed from Neon Production
- Managed position mirror: OPEN symbol LRCX, remaining qty 0.049034, entry average 295.9079954725292654076763062 USD, updated 2026-10-14T12:30:05.253Z.
- Submitted executions: BUY 11, SELL 10 (21 total).
- Submitted executions directly joined by broker_order_id to managed_position_mirror entry_order_id or exit_order_id: 0 rows.
- Earlier read-only checks: trade_execution 96 rows (FILLED 75 / SUBMITTED 21), and broker/client ID count 96 unique each.
- 20 of 21 SUBMITTED records were created more than 7 days before the earlier inspection, but their updated_at was recently refreshed; not proof that 21 live open orders exist.

## Scientific / operational interpretation
- Neon state is a database mirror, **not broker ground truth**.
- A zero direct-ID join could reflect different event/position key conventions, not a failed order.
- No broker account or order endpoint was queried, so actual holdings and outstanding orders remain UNKNOWN.
- Pending classification: BROKER_RECONCILIATION_PENDING.

## Next read-only evidence
1. Obtain broker read-only open orders and positions through the existing server's approved authentication pathway (never print secrets).
2. Compare broker holdings against LRCX qty 0.049034 and compare avg price with any differing corporate-action adjustments.
3. Join order lifecycle using client order ID, broker ID, execution ID and event timestamps.
4. Separately validate LIVE systemd timers and runtime git SHA.
5. Preserve evidence as summarized aggregates and hashes without unnecessary personal account identifiers.

## Safety
No LIVE order or configuration changes authorized, no submitted records deleted or marked filled, no production deployment.
