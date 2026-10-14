# Kalman future ADD_ON position linkage — audit branch only

As of 2026-10-14. **Status: OFFLINE_CI_PASS / NOT_DEPLOYED / HISTORICAL_REPAIR_BLOCKED**

## Source-rooted problem
- `engine/auto_trade.py` knows `position['position_id']` when a same-symbol ADD_ON is reserved, but original `signal_context` did not persist it.
- `app/managed_positions.py::apply_add_on_fill` intentionally clears `add_on_client_order_id` and `add_on_order_id` after aggregating the fill. The original mirror maps order->position by the *current* entry/exit client order IDs only.
- The 21 historical orphan SUBMITTED Neon mirror rows have cached broker FILLED telemetry, but no durable explicit position link. **Do not backfill links from ticker/time alone.** None was reconstructed during this stage.

## Audit-only chain prepared
1. `engine/auto_trade.py` now tags *future* order `signal_context.managed_position_id` after a reserved position is available.
2. New pure `engine/order_position_link.py::explicit_buy_link` requires all of:
   - nonempty explicit position ID and exactly one matching managed position
   - BUY and permitted `entry_type` (INITIAL or ADD_ON)
   - signal-run/client-order-id consistency with `_client_order_id` deterministic naming
   - symbol equality across order, signal context and managed position
   - strategy version agreement, proper initial-run linkage or valid ADD_ON ordinal
3. `engine/trade_mirror.py` first uses preserved entry/exit client IDs; if not mapped, it uses the pure explicit link to assign `position_id` and `position_leg`, labeling `metadata.position_link_source=EXPLICIT_SIGNAL_CONTEXT`. Local linkage is *not* broker confirmation.
4. For explicitly linked ADD_ON records, the mirror now retains their own signal `run_id` and `signal_as_of`, not the initial entry's.
5. Historical broker FILLED evidence remains independently validated with strict broker order ID/status/HTTP/quantity/time. The audit branch's failed-leg quantity guard still suppresses fictitious multi-bagger `net_return`.

## Test evidence
- CI workflow at `.github/workflows/kalman-audit-quality.yml` invokes the new synthetic no-network `test_order_position_link_integration.py` alongside previous tests and source compile checks.
- Completed run **38589550924**: `Ran 95 tests ... OK`.
- https://github.com/kimtk94/Codex/actions/runs/38589550924

## Release gates
- **No production merge, deploy, or Neon edits executed.** The P1 overstatement in 5 historical multi-entry net-return rows remains present in Production.
- Existing historic orphan orders do not have the new tag and remain unlinked, regardless of matching symbol/time. Broker positions, full 97-record event replay and accurate add-on commission/tax reconstruction remain unverified.
- Production deployment would require **both** changed `auto_trade.py`, `trade_mirror.py`, new `order_position_link.py` AND `broker_status_evidence.py`, with pinned source version plus runtime attestation. Deploying only `trade_mirror.py` is unsafe (missing import).
- Obtain explicit operator approval for deployment and independently verify that all trading and mirror consumers preserve contract and fail-closed behavior.
