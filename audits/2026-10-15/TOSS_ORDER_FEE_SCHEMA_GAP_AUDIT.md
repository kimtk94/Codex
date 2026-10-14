# Kalman Toss fee currency schema gap — 2026-10-15 KST
**Status: DOCUMENTED_FIELD_AUDIT_PASS / FEE_CURRENCY_UNVERIFIED / PRODUCTION_RELEASE_HOLD**

## Objective
Verify the provenance of broker commission, tax, and currency for the Kalman net-return P1 audit. Avoid inventing `feeCurrency` or treating undocumented currency provenance as audited cash flow. All actions were public documentation reads, read-only GitHub source inspection, and audit-branch-only CI. **No Toss account/API request, Neon DML, broker trade, or production deployment occurred.**

## Public documentation examined
- Toss official API guide: https://developers.tossinvest.com/docs ; order detail `GET /api/v1/orders/{orderId}` and historical orders are exposed, and separately `GET /api/v1/commissions` returns a fee *schedule*.
- Publicly archived 2026-09-07 audit of official REST OpenAPI v1.2.14: https://github.com/dd3ok/tossinvest-api-skill/blob/main/references/official-api-audit-2026-09-07.md
- Its `Order` schema documents `currency` among other fields.
- Its `OrderExecution` fields are precisely `filledQuantity`, `averageFilledPrice`, `filledAmount`, `commission`, `tax`, `filledAt`, `settlementDate`. **No `feeCurrency` property is listed** in that archived schema.
- A more recent official website appears to have newer spec versions than the archived v1.2.14. As of this audit, attempts to fetch live `/openapi-docs/latest/openapi.json` and `/llms.txt` through our public document access route were unsuccessful. Do **not** assert an exhaustive current live spec or runtime response shape.

## Existing application paths inspected (GitHub main read-only)
- `kalman-toss-gateway/app/toss_client.py::order`: `GET /api/v1/orders/{orderId}`.
- `engine/position_manager.py::_order_view`: unwraps `result` object.
- `engine/position_manager.py::_broker_order_telemetry` stores: `currency=order.currency` and `filled_quantity,average_filled_price,filled_amount,commission,tax,filled_at` from `execution`; there is **no `fee_currency` stored** in the broker-order telemetry.
- `engine/trade_mirror.py` on the audit branch correctly refuses to equate absent broker `fee_currency` with order `currency`. Thus fee currency remains UNVERIFIED in both existing source and currently reviewed documented field set.
- **Release compatibility blocker**: The previous audit-branch fail-closed net-return checker explicitly requires `broker_currency` AND `fee_currency`. Since local telemetry has no `fee_currency`, it would suppress net-return values even where trade currency, commission, and tax are all reported. This is intended fail-closed, but it is **not an approved production replacement** until an independent fee-denomination source is established.

## Offline diagnostics implementation
- `audits/2026-10-14/quality/toss_order_fee_schema.py`: pure schema probe returns **non-sensitive flags only**; does not output accounts, order IDs, or fee amounts; does not assert net-PnL eligibility.
- `audits/2026-10-14/quality/test_toss_order_fee_schema.py`: validates documented field set, presence and finite nonnegative commissions/taxes, true zero versus missing, rejection of invalid/partial payloads, and static source checks to detect implicit fee currency inference.
- Final GitHub Actions run `38637862359`, completed/success: **146 tests OK**. https://github.com/kimtk94/Codex/actions/runs/38637862359
- This is mock/offline testing and source inspection, **not** an attested real Tosss order response.

## What is and is not established
| Dimension | Evidence | Decision |
|---|---|---|
| Order trade currency | Documented `Order.currency` and local telemetry parser | KNOWN FIELD; individual live values unverified |
| Filled quantity, avg price, amount | Documented `OrderExecution` properties | KNOWN FIELDS; values unverified |
| Actual commission and tax amounts | Documented `OrderExecution.commission,tax`; optional/missing observations possible | KNOWN FIELDS; each order needs attestation |
| Commission/tax denomination | No distinct `feeCurrency` in archived schema; local code does not persist one | UNVERIFIED |
| Commissions schedule | Separate `GET /api/v1/commissions` | NOT a substitute for actual historical fees/taxes |
| Five corrupted historical multi-leg positions | Prior Neon SELECT-only audits | P1 NOT REPAIRED |
| Original LIVE broker account & execution balances | Not accessed | UNKNOWN |

## Release decision and next evidence
1. Obtain **authoritative current** schema description or explicit provider statement on the currency of `OrderExecution.commission` and `tax`; never assume parent `currency` without documentation.
2. If fee currency semantics are documented, add a unit-tested, source-attributed normalization layer (with schema version and provenance). Do not silently fill missing fees or convert currencies.
3. Independently link all historical add-on broker-order IDs to managed positions and get per-order fee/tax receipts before any repair of the five P1 net returns.
4. Only after staging replay, version-pinned runtime checks and explicit user approval may any production source/Neon/Vercel change be considered.

**Current conclusion: Audit source/provenance gap identified, regression verified, Production remains HOLD.**
