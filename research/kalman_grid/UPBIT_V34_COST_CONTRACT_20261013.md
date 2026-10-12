# Kalman Grid V3.4 — Upbit PAPER order cost contract

Date: 2026-10-13 KST. Research branch only.

## Implemented
- `upbit_grid_contract_v34.py`: explicit BUY-down / SELL-up KRW tick rounding, minimum KRW notional check, and hypothetical roundtrip net cost after fee and slippage.
- `test_upbit_grid_contract_v34.py`: four additional tests.
- Earlier V3.3 rules and its four tests reproduced independently with Python 3.
- **8/8 unit tests PASSED** in an isolated Python environment (reconstructed copies matching GitHub file content). The complete server checkout and 2026-09 full-month simulation were **not** rerun because remote-server tool quota was previously exhausted.

## Important boundary
This is **not integrated** into `Grid.update()` or the Ledger. It is a separately callable PAPER pricing/cost contract. In particular, do NOT apply rounding inside `price(k)` without passing BUY/SELL explicitly, because a sell target can have a negative grid index. The contract does not assert resting limit fills, execution probabilities or order book queue position.

Illustrative parameters:
- raw buy KRW 3,500,555 -> BUY tick KRW 3,500,000
- raw sell KRW 3,505,456 -> SELL tick KRW 3,506,000
- minimum order KRW 5,000, fee assumption 0.05% per side
- additional 0.10% slippage per side can turn this example from positive into negative modeled net P&L.

## Follow-up gates
1. Run complete clean GitHub checkout test suite and compare with server version.
2. Refactor engine to explicitly quote BUY and SELL per level; validate tick/quantity/order min and ledger invariants before each simulated placement.
3. Rerun September 2026 full-month BTC and ETH using 1-minute, OHLC sensitivity, actual tick/fee and slippage stress.
4. Compare against buy/hold and cash, report realized/unrealized P&L, annualized return (only with sufficient sample), MDD, turnover, trading days and no-fill rates.
5. Maintain **PAPER ONLY**, no LIVE changes.
