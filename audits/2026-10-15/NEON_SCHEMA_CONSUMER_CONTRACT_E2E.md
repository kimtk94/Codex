# Kalman release hold — Neon schema + guarded consumer + E2E verification
Date: 2026-10-15 KST
**Verdict: ISOLATED_E2E_PASS / LIVE_NET_RETURN_P1_UNRESOLVED / PRODUCTION_HOLD**

## Scope and safe operations
- Production Neon: **SELECT-only** inspection of table schema, constraint/index metadata, RLS, triggers, ledger view SQL and aggregate counts.
- GitHub: commits ONLY on `audit/kalman-control-20261014`.
- GitHub Actions: disposable Postgres 16 and synthetic SQLite, synthetic account/order identifiers; no LIVE/Neon/real broker access.
- No production schema modifications, order submissions, token refresh, account access, server deployment, Vercel deploy, or Production DML.

## Confirmed Neon schema facts
- `managed_position_mirror` has PK `position_id`, JSONB `metadata`, and `idx_managed_position_mirror_state_updated`.
- `trade_execution` has UUID `execution_id` PK (default `gen_random_uuid()`), UNIQUE `client_order_id`, CHECK constraints `market='US'`, `side IN (BUY,SELL)`, `execution_mode IN (DRY_RUN,LIVE)`, and indexes on symbol/update and non-null position ID/update.
- Both are RLS-disabled, with no user triggers or table policies in the inspected schema. This does not attest connected application permissions, other views or remote deployment.
- Production `v_live_trade_ledger` is a view over `managed_position_mirror`, NOT `trade_execution`; computes gross price-return fraction as exit/entry average - 1, and reads `net_return` as `NULLIF(metadata #>> '{execution_quality,round_trip,net_return}','')::numeric` **without quantity, fee or provenance gates**.
- Exact read-only `pg_get_viewdef` captured under `quality/captured_live_trade_ledger_view.sql`, used only in CI disposable PG.
- Mock tables updated with the observed columns, data types, defaults, indexes, checks and unique keys; no full Production permissions/extensions/app consumers are reproduced.

## New P1 defect revealed by realistic view/E2E scenario
- A managed position had local `entry_status=FILLED` but the cached broker-order status was deliberately `SUBMITTED`. Its cached `filledQuantity`, price, fees and tax were still populated. The old audit-branch round-trip calculation could produce a numeric net return, even without confirmed terminal broker FILLED evidence.
- Fixed audit-branch `_round_trip_quality`: after full-leg coverage, requires explicit `broker_fills_verified=True`; `trade_mirror.main` computes this from **both** strict matching `historical_broker_fill(entry_order,...)` and `historical_broker_fill(exit_order,...)` proofs (order ID, terminal FILLED, HTTP 200, positive qty/price, timestamp).
- If evidence missing, `quality_status=BROKER_FILL_UNVERIFIED`, `net_return=NULL`, `net_return_pct=NULL`, and `round_trip_cost_bps=NULL`.
- Deliberately does NOT promote local managed-position FILLED status into broker proof. A ledger row may keep local FILLED while `order_fill_source=UNVERIFIED` and top-level per-order fill quantity NULL. This preserves provenance separation.

## Consumer safety candidate (staging ONLY)
- `quality/guarded_live_ledger_candidate.sql` creates **a new disposable view** `v_live_trade_ledger_guarded_candidate`, not a Production replacement.
- Requires CLOSED/zero-remaining position, full entry/exit fill quantity matches, valid nonnegative fee and tax values, explicit currency agreement, `FULL_LEG_COVERAGE` quality status, and `independent_order_manifest_verified=true` in round-trip metadata.
- If any source is missing, numeric `net_return` and cost basis points are NULL, preserving independent *price-only* gross return and reporting `UNVERIFIED`.
- **The currently deployed mirror does NOT generate the independent-manifest attestation**, and it must not be fabricated or auto-created from the same fills being evaluated. All 40 mock positions are initially masked; only one manually attested *synthetic* mock row becomes locally eligible in a rolled-back temporary PG test transaction.
- Also injected a mocked +198.697% stale P1 `net_return` into a disposable multi-entry row: original captured Production view exposed it, guarded candidate hid it. No Production value changed.

## E2E and stress evidence
Final GitHub Actions:
https://github.com/kimtk94/Codex/actions/runs/38641961383
**COMPLETED SUCCESS**:
- 150 ordinary unit/offline test methods, including nested 1,000 seeded valid cash-flow scenarios + 2,000 injected corruptions.
- 15 disposable PostgreSQL integration methods using real audit-branch `trade_mirror.py` process and a synthetic 40-position/97-order SQLite source.
- **165 unittest methods total**, with 3,000 scenario evaluations nested inside two of the methods. This is not a replay of real Production 104 trades.
- An earlier CI run failed because this integration exercise caught the real nonterminal-broker fill P1 gate defect; the source and test fixtures were corrected and the final run passed.

## Fresh SELECT-only Production mirror snapshot (during this audit)
| Metric | 2026-10-14 preceding snapshot | Fresh 2026-10-15 SELECT |
|---|---:|---:|
| managed position rows | 40 | **45** |
| OPEN mirrored positions | 0 | **3** |
| trade_execution rows | 97 | **104** |
| SUBMITTED mirror records | 21 | **21** |
| CLOSED positions with displayed net_return | 36 | **38** |
| displayed net_return with incomplete first-entry quantity | 5 | **5** |
| independent manifest verified in CLOSED displayed-net metadata | unknown previously | **0** |

These are **Neon mirror** values at two different points in time, not current brokerage holdings or a brokerage statement. New trades/positions arrived while we audited; none were caused by this audit.

## Release blockers
1. **P1 Production corrupted performance persists:** five incorrectly inflated multi-entry net returns remain.
2. Real account positions/open order status not independently reconciled; no complete historical order-ID/fee evidence.
3. Actual Toss fee/tax denomination still unverified; no documented `feeCurrency` property in archived public OrderExecution schema.
4. `independent_order_manifest_verified` is a **future attestable contract**, not a current source field; do not fabricate it. Staging-only safe view is not wired to frontend.
5. Actual Vercel deployed runtime JS bundle/source and Kalman server Git SHA not attested; GitHub audit branch and main diverged.
6. Historical 104 real order replay, row-level diff, application consumer rendering and release/rollback rehearsal not yet performed.

**Overall decision: P1 PRODUCTION RELEASE HOLD.** No merge, production deploy, or Production data updates.
