# Kalman trade mirror — production release gate (2026-10-14 22:35 KST)

**Decision: HOLD — NOT APPROVED FOR LIVE MERGE/DEPLOYMENT**

This is an audit-only analysis. No production SSH command, broker order, token request, or Neon DML was executed.

## 1. Git branch comparison
GitHub compare: `main` vs `audit/kalman-control-20261014` returned **diverged**, audit ahead **41** commits and behind **6**.
- Audit changes: 27 files shown, primarily `audits/2026-10-14/**` and audit CI, plus 2 trade engine changes: new `engine/broker_status_evidence.py`, modified `engine/trade_mirror.py`.
- main-only changes relative to merge base: SSH audit workflow `.github/workflows/server-readonly-audit.yml` and 2 trigger files; no conflicting changes observed in trade engine source.
- Source blob SHA for `engine/position_manager.py` and `app/managed_positions.py` is identical on main and audit. `trade_mirror.py` differs by candidate changes as intended.
- **The deployed runtime git SHA on /opt/kalman/app is NOT verified.** GitHub comparison is NOT server-source attestation.
- Merge/rebase must preserve existing main SSH audit workflow; do not force-push or replace main.

## 2. Live read-only mirror evidence changed during audit
- In the previous 96-event dry-run: 75 FILLED, 21 SUBMITTED, 1 OPEN LRCX (0.049034 shares).
- During this session, an additional historical-execution row appeared, `LRCX SELL FILLED` at 2026-10-14T13:30:05.945Z (22:30:05 KST), quantity 0.049034, average price $290.91.
- LRCX local managed position is now CLOSED with `remaining_quantity=0`, `exit_filled_quantity=0.049034`, `exit_status=FILLED`, and `exit_reason=MAX_HOLD_4_BUCKETS`.
- LRCX recorded entry quantity weighted average $295.907995472529..., exit average $290.91. Simple **gross** price return `(290.91/295.907995472529 - 1) * 100 = -1.68903698%`, gross USD P/L approximately -$0.2451 on 0.049034 shares, **before** commissions, FX conversion, and tax. This is historical mirror P/L, not verified broker balance.
- Last snapshot in this session: **97 trade_execution events**, 76 FILLED, 21 SUBMITTED, **0 OPEN mirrored managed positions**; trade_execution sync timestamp 2026-10-14T13:35:22Z. State may change with trading cycles.

## 3. Corrected projection on live 97 rows (Neon SELECT-only)
- 76 previously FILLED remain FILLED (36 BUY, 40 SELL), all 76 have managed position_id.
- 21 previously SUBMITTED project to FILLED based on matching cached broker historical FILLED telemetry (11 BUY, 10 SELL); all 21 have NULL position_id, missing top-level fill qty/avg price.
- Current patch fills the top-level quantity/price and records `status_source=broker_order_telemetry`, **but does not reconstruct missing position_id**. Consumers aggregating all FILLED trades would see 76 -> 97, although these 21 are **not new executions**.
- Before any release, separately audit dashboard KPIs and exposure/P&L consumers for double counting and `position_id IS NULL` assumptions. Do not infer actual open orders from old SUBMITTED mirror statuses.
- Full live broker holdings/open orders remain UNKNOWN.

## 4. Offline release candidate tests
- CI `https://github.com/kimtk94/Codex/actions/runs/38573005418`: **60 tests, OK**.
- Added `audits/2026-10-14/quality/test_trade_status_projection_regression.py`: synthetic 97-event suite (76 managed FILLED + 21 orphan SUBMITTED with cached broker FILLED). Checks projections, immutability, malformed evidence rejection, idempotent status, and LRCX exit quantity.
- This synthetic suite is **not a replay of actual raw 97 broker events**. Actual aggregate projection was checked separately via Neon SELECT-only.

## 5. Remaining release gates
1. **BLOCKED**: deployed runtime git SHA and local SQLite schema/source provenance not independently verified by the SSH runbook.
2. **BLOCKED**: current broker positions and open orders not observed via a validated read-only broker channel.
3. **BLOCKED**: all 97 row-by-row events / dashboard consumers not replayed in isolated staging against a sanitized, permissioned snapshot.
4. **BLOCKED**: entry, add-on, exit link reconstruction and exposure/P&L double-count semantics still need explicit acceptance.
5. **REQUIRED**: explicit operator approval for any production merge, server deploy, or Neon data correction.

**Conclusion:** Offline patch CI PASS, DB aggregate projection PASS, operational release **HOLD**.

Links:
- Prior 96-row dry-run: `audits/2026-10-14/TRADE_STATUS_DRYRUN_96_RESULTS.md`
- Candidate patch: `kalman-toss-gateway/engine/trade_mirror.py`
- Synthetic test suite: `audits/2026-10-14/quality/test_trade_status_projection_regression.py`
