# Broker reconciliation — source-code audit (2026-10-14)

## Verified implementation
- `kalman-toss-gateway/app/toss_client.py` supplies `TossClient.holdings(symbol)`, `orders(status="OPEN",symbol)`, `order(order_id)`, `sellable_quantity(symbol)`; these invoke HTTP GET.
- `kalman-toss-gateway/engine/execution_telemetry_sync.py` invokes order GET but also constructs `TradeLedger(state_db)` and calls `ledger.patch_telemetry(...)`; constructor can migrate SQLite schema. **Not read-only** and must not be used for this audit.
- Token handling in `TossClient` may update a shared token cache; therefore HTTP GET alone is insufficient to assert a zero-write local process.

## Available Neon observations
- OPEN mirror LRCX remaining 0.049034 shares, entry average 295.9079954725292654076763062 USD.
- trade_execution aggregate: 96 events (75 FILLED / 21 SUBMITTED); 20 SUBMITTED created >7 days before check. Direct SUBMITTED broker-order-id to position mirror entry/exit order-id joins = 0.
- Mirror events are **not** proof of the broker's current holdings or order status.

## Required safe follow-up
1. Use an approved existing broker read-only reporting channel that has been verified not to alter local state; avoid `execution_telemetry_sync.py`.
2. Return minimal sanitized aggregates: holdings LRCX quantity, broker open order count per symbol, and lifecycle outcomes for historical submitted orders (no credentials or account IDs).
3. Compare broker evidence to Neon only after gathering both at near-matched timestamps.
4. If no truly read-only broker access is available, retain UNKNOWN and do not mutate LIVE.

Status: CODE_PATH_CONFIRMED / BROKER_DATA_UNVERIFIED.
