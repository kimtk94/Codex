# Kalman Trade Status Patch — 96-row Production SELECT-only dry-run
Date: 2026-10-14 KST
Scope: read-only SELECTs on Neon production; simulated projection of audit-branch candidate. NO UPDATE/DEPLOY/ORDER SUBMISSION.

## Before/after (actual Neon metadata, no mutation)
| Existing status | Proposed projection | Records | Filled qty column NULL -> populated | Avg fill price NULL -> populated |
|---|---|---:|---:|---:|
| FILLED | FILLED | 75 | 0 | 0 |
| SUBMITTED | FILLED | 21 | 21 | 21 |
| **Total** | | **96** | **21** | **21** |

All 21 projected records meet historical evidence conditions:
- Cached broker status = FILLED, HTTP status 200, matching broker order IDs
- Positive broker filled quantity, positive average fill price, timestamp format present
- No order filled >30 seconds before local submitted event among those 21
- 21/21 have NULL `trade_execution.filled_quantity` and `trade_execution.average_filled_price` before patch
- Existing 75 records remain unchanged by projection

## Aggregate scope (historical, NOT NEW executions)
- Projected old SUBMITTED BUY: 11 orders; sum of broker filled quantities **0.272564 shares across different tickers**; aggregate notional ~$43.5768
- Projected old SUBMITTED SELL: 10 orders; sum of broker filled quantities **0.186591 shares across different tickers**; aggregate notional ~$41.1723
- Do **not** use cross-ticker share sums as a meaningful exposure metric, nor count these as new trades/P&L.

## LRCX reconciliation using mirrored broker telemetry
- LRCX recent BUY #1: 0.025357 at $292.61 (2026-10-14 00:39 KST)
- LRCX recent BUY #2: 0.023677 at $299.44 (2026-10-14 01:39 KST), main mirror status SUBMITTED but cached broker status FILLED
- Current-episode buys sum 0.049034; quantity weighted average $295.907995473.
- Neon OPEN LRCX mirror remaining quantity 0.049034; entry average $295.907995472529...
- Position mirror already incorporates the second purchase in its aggregated quantity/price. Status backfill must **not add any quantities to managed_position_mirror or re-execute orders**.

## Root cause & provenance
- Main source `engine/trade_mirror.py`: `_execution_status` falls back to `order_guard.status` for unmatched managed position orders, ignoring historical broker fill telemetry. The mirror's `updated_at=now()` is a sync timestamp. In the observed batch all 96 executions were refreshed in the 2026-10-14T13:00Z minute.
- Managed positions store includes `add_on_client_order_id`, which can be cleared after applying add-on fills; the main mirror maps only entry/exit client-order IDs.
- Historical status-source mapping: 75 FILLED from managed_position; 21 SUBMITTED from order_guard.
- Broker balances/current open-order book remain **unverified**.

## Proposed audit-branch code (NOT DEPLOYED)
- `kalman-toss-gateway/engine/broker_status_evidence.py`: validate cached broker fill ID/status/quantity/price/timestamp/HTTP response.
- `kalman-toss-gateway/engine/trade_mirror.py`: project historical broker evidence only for unmatched SUBMITTED, preserve managed position precedence, populate missing fill quantity and average price.
- Offline CI https://github.com/kimtk94/Codex/actions/runs/38569569243: 55 tests OK. This is not 96 live DB integration tests.
- Reproducible SELECT-only SQL: `quality/trade_status_dryrun_96.sql`.

## Before release: safety and quality gates
1. Verify current LIVE deployed git SHA, server-local SQLite schema and telemetry records are equivalent to GitHub main.
2. Obtain real broker positions and current open orders, timestamp aligned with source mirror observations; never conflate `updated_at` with broker observation time.
3. Dry-run against a production snapshot in an isolated non-live environment; compare all 96 event IDs before/after and run policy-specific regression tests.
4. Confirm chart/report consumers' state semantics and trade-count calculations; avoid counting 21 old fill events again.
5. Explicit user approval before a production deployment or data migration; no live orders or Neon changes during audit.

### Verdict
**DRY_RUN_PASS_WITH_RELEASE_BLOCKERS**: The 96-row SELECT projection yields 21 historically corroborated status/fill-column corrections and 75 unchanged rows. Broker account ground truth is UNKNOWN and LIVE deployment is NOT APPROVED.
