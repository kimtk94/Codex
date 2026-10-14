# Kalman P1 follow-up — fee provenance fail-closed net return gate
Recorded 2026-10-15 KST. GitHub audit branch only. No broker API requests, live trading, production deployment or Neon DML.

## Confirmed source defect
The earlier `kalman-toss-gateway/engine/trade_mirror.py::_execution_quality` converted missing or invalid commission and tax to zero with:
```python
commission = _dec(broker.get("commission")) or Decimal("0")
tax = _dec(broker.get("tax")) or Decimal("0")
```
Consequently `_round_trip_quality` could return a numeric net return even where a full position's fees were not actually reported. This is separate from the previously proven 5 multi-entry P1 net-return overstatements.

## Audit branch corrective design
- `_execution_quality` preserves explicit reported numeric 0 and retains NULL for missing, invalid, nonfinite or negative fee components. It does not calculate `cost_bps` without both commission and tax.
- Broker-provided `currency` and `fee_currency` are separately exposed in execution quality; a quote-derived trade currency alone is *not* fee-currency proof.
- `_round_trip_quality`, after verifying position leg quantities, requires explicit nonnegative finite commissions and taxes from both entry and exit quality records.
- Missing fee evidence => `quality_status=INCOMPLETE_FEE_EVIDENCE`, with `net_return`, `net_return_pct`, `round_trip_cost_bps` all NULL.
- Missing/unproven/mismatching fee and trade currencies => `quality_status=UNVERIFIED_FEE_CURRENCY`, also NULL numeric net return and cost.
- Explicit zero fee is allowed; complete matching USD/USD or KRW/KRW examples retain the existing net return arithmetic.
- This is a deliberate conservative quality gate: whether Toss historical payloads actually supply `fee_currency` is **UNVERIFIED**. A NULL result may reflect an unavailable field, not a nonzero fee. Do not assume that absence means fees were free.
- `public.v_live_trade_ledger.realized_return_pct` is independently calculated from managed position average entry/exit prices; suppressing net quality does not alter the position-price-only return.

## CI verification
- Tests: `audits/2026-10-14/quality/test_fee_provenance.py` plus updated quantity-coverage fixtures.
- Tests cover zero-vs-missing fees, nonexistent broker payload, negative/nonfinite fees, missing/incorrect fee currency, quote-only currency, pricing and guard priority.
- First CI with new tests failed a *test expectation*: completely missing broker payload appropriately fails earlier as `INCOMPLETE_LEG_COVERAGE`, not `INCOMPLETE_FEE_EVIDENCE`; test was corrected without weakening runtime checks.
- Final CI: **134 tests / OK**, GitHub Actions `38635160574` **COMPLETED / SUCCESS**:
  https://github.com/kimtk94/Codex/actions/runs/38635160574

## Current limitations and release decision
- Existing 5 anomalous multi-entry net returns are **still wrong in Production** and were **not repaired**. No new broker fee/position data was acquired.
- Existing 31 quantity-covered net values have **not** been validated against independent fee-currency statements.
- The code is **only on audit/kalman-control-20261014**. Its fee-currency input contract is not yet validated against the real Toss response schema. Staging/replay and broker-source attestation are required.
- Baseline `main`, the running server, Neon Production and Vercel Production were not modified in this step.
- Overall: `OFFLINE_FEE_GATE_PASS / HISTORICAL_FEES_UNVERIFIED / P1_PRODUCTION_RELEASE_HOLD`.

See also `audits/2026-10-14/NET_RETURN_OVERSTATEMENT_P1.md` and `audits/2026-10-14/MULTILEG_CASHFLOW_OFFLINE_GATE_20261015.md`.
