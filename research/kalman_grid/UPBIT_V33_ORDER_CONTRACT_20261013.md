# Kalman Grid V3.3 — Upbit price tick and order-cost gate

Created 2026-10-13 KST. Scope: **PAPER RESEARCH ONLY**.

Code: `upbit_krw_rules_v33.py`; tests: `test_upbit_krw_rules_v33.py`.
Official current Upbit KRW tick policy (2025-07-31 onward): https://docs.upbit.com/kr/docs/krw-market-info .
Minimum notional 5,000 KRW. For BTC and ETH at prices >=1m KRW, tick 1,000 KRW.

Implemented:
- Decimal-based price-tier tick lookup.
- Conservative LIMIT BUY price rounds down, SELL price rounds up.
- Reject invalid tick or notional <5,000 KRW; only accepts positive price and quantity.
- Approximate round-trip margin `grid spacing pct - 2*fee pct - 2*slippage pct`, **not** executable expected return.
- Four unit-test cases authored; **not yet executed against the server repository** due remote access tool quota.

Examples:
- 0.14% grid, 0.05% each-side fees -> 0.04 percentage points before spread/slippage.
- At 0.03% each-side slippage, approximate margin -0.02 pp.
- Price 3,500,555 KRW -> BUY limit 3,500,000, SELL limit 3,501,000.

DATA status: September BTC and ETH full month collected and quality audit PASS. Monthly performance **NOT VERIFIED** and no numeric return has been claimed.

Next:
1. Execute new unit tests (and prior 22 tests) in clean research checkout.
2. Wire tick snapping and min-notional validation to PAPER engine with ledger invariants; explicitly disallow production deployment.
3. Rebuild backtest for 2026-09 all minutes, export return/MDD/fees/fills/turnover and manifest.
4. Expand full months and add queue/spread/slippage sensitivity.
5. Compare against buy-hold/cash, out-of-sample before any LIVE consideration.
