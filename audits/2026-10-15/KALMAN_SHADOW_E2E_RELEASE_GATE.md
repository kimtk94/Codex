# Kalman larger-scope shadow integration audit — 2026-10-15 KST

**Verdict: ISOLATED_E2E_PASS / SOURCE_RELEASE_HOLD / P1_LIVE_DATA_UNFIXED**

## Purpose and audit boundary
Advance beyond AST/unit checks and synthetic single functions by executing the actual audit-branch
`kalman-toss-gateway/engine/trade_mirror.py` process against a disposable PostgreSQL 16
service and locally generated SQLite order/managed-position tables.

- **NO** LIVE Kalman code deployment, Toss order/API call, OAuth refresh, user server
  access, Neon Production query or write, Vercel deployment, or real brokerage credentials.
- The CI service uses a fixed disposable loopback PostgreSQL DSN
  `postgresql://audit:audit@127.0.0.1:5432/kalman_audit`.
- The integration harness refuses arbitrary connection strings and generates
  mock order IDs and made-up fees only.
- The PostgreSQL schema is **purpose-built for the projection**, not a validated
  copy of current Neon constraints, triggers, views, permissions, or RLS.

## Data volume and tests
- `test_shadow_mirror_postgres.py` creates **40 synthetic CLOSED positions**,
  **97 synthetic orders**, and replays the **real audit-branch mirror process twice**.
- 39 positions use synthetic single-entry/single-exit orders; one LRCX-shaped
  position has two entry orders and one exit order.
- 16 orphan orders deliberately lack explicit position linkage:
  15 have historical FILLED evidence and one remains SUBMITTED.
- Synthetic PostgreSQL output at first run:
  - `managed_position_mirror=40`, `trade_execution=97`
  - Historical order status projection `FILLED=96`, `SUBMITTED=1`
  - This **does not mirror the real production 76 FILLED/21 SUBMITTED
    observation**: they are different synthetic scenarios.
- LRCX-shaped position:
  - INITIAL BUY = **0.025357**, ADD_ON BUY = **0.023677**,
    total BUY = **0.049034**, SELL = **0.049034**, remaining = 0.
  - Per-order mirror quantity comes exclusively from verified broker-order
    telemetry, never the managed aggregate (prevents double counting).
  - ADD_ON receives explicit `position_id`, `position_leg=ADD_ON`,
    `position_link_source=EXPLICIT_SIGNAL_CONTEXT`, own signal run ID.
  - Historical unlinked orders remain `position_id=NULL` even if they
    share symbol/time with a managed position.
  - Multi-entry net P&L remains NULL under
    `INCOMPLETE_LEG_COVERAGE`; price-only return remains negative.
  - Missing fee denomination results in
    `UNVERIFIED_FEE_CURRENCY`, not a fabricated net return.
  - When matched managed-position status is FILLED but broker-order
    evidence is absent, **event-level filled_quantity=NULL** with
    `order_fill_source=UNVERIFIED` (aggregate qty not substituted).
- A second mirror run updates existing rows without increasing row counts,
  verifying the UPSERT is idempotent on this fixture.

## More comprehensive deterministic cash-flow stress
- `test_multileg_randomized.py` contains:
  - **1,000 seeded multi-leg scenarios** with Decimal reference P&L
    and 1–4 BUY orders + SELL order per position.
  - **500 seeded base inventories**, each tested with 4 separate
    corruption mutations (**2,000 negative cases**) for missing orders,
    missing fees, unverifiable position links, and duplicates.
  - These are scenarios inside 2 Python unit-test methods, **not 3,000
    individual unittest test-method counts**.
- `trade_mirror._dec` now rejects boolean and NaN/Infinity inputs,
  with regression coverage.

## Source changes limited to audit branch
1. `kalman-toss-gateway/engine/trade_mirror.py`: per-order
   `filled_quantity` and average price derive from verified broker
   historical order telemetry, not aggregate managed-position quantity.
   `metadata.order_fill_source` explicitly describes the origin.
   First-entry execution quality uses first-entry broker price, not the
   combined position average.
2. `audits/2026-10-14/quality/shadow_mirror_schema.sql`: ephemeral test schema.
3. `audits/2026-10-14/quality/test_shadow_mirror_postgres.py`: executable
   end-to-end replay, provenance, duplicate, fee and P1 tests.
4. `audits/2026-10-14/quality/test_multileg_randomized.py`: large deterministic
   mathematical reference and fail-closed mutations.
5. `.github/workflows/kalman-audit-quality.yml`: PostgreSQL 16 service,
   pinned psycopg/python-dotenv, two-phase checks, no production secrets.

## CI evidence
**GitHub Actions run 38639332645 — COMPLETED/SUCCESS**:
https://github.com/kimtk94/Codex/actions/runs/38639332645

Verified job logs:
- **149 ordinary/offline unittest methods: OK**, including 1,000 valid
  multi-leg + 2,000 invalid-case evaluations.
- **10 PostgreSQL real-process integration test methods: OK**.
- **159 test methods total** across two test invocations, in addition to the
  3,000 seeded evaluation scenarios inside two of those methods.
- A prior integration CI run failed on `psycopg` interpreting SQL LIKE '%'
  with empty bound parameter tuples; test-only query execution was fixed.
  The final run passed all checks.

## Material remaining blockers
1. **P1 real values not repaired**: five historical multi-entry Production
   net returns remain overestimated. This test uses only synthetic data.
2. **Proven fee currency missing**: public archived Toss API
   `OrderExecution` schema does not document `feeCurrency`; the audit-branch
   conservative gate suppresses net P&L when denomination is unverified.
3. **LIVE data provenance missing**: current account positions/open orders,
   broker statement and complete historical order-to-position and fee
   evidence were not independently verified.
4. **Production SQL compatibility unverified**: isolated schema has no
   production triggers/RLS/views/constraints; do not infer deployment safety
   from passing shadow replay alone.
5. **Consumers may require migration**: changing entry-order filled quantity
   from aggregate to per-order semantics may affect downstream dashboard
   counts and reporting; per-order vs position-level metric contracts need
   explicit consumer review and signoff.
6. **Actual deployed source SHA unknown**, GitHub main/audit branches have
   diverged, and Vercel source/runtime provenance remains unverified.
7. No production merges, Neon migrations, or live deployments are
   authorized by this audit step.

**Recommendation:** retain P1 PRODUCTION RELEASE HOLD. Next milestone is
read-only attested production schema/consumer contract comparison and
isolated replay of appropriately redacted real event rows *after* safe
evidence access, followed by operator-approved deployment planning.
