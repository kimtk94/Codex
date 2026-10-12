# Kalman Grid V3.8 — verified server cost-stress results (2026-10-13)

Source: user-provided 2026-10-13 console output from `upbit_v38_cost_stress.py`, not independently fetched from the server. Research-only.

## Execution and checks
- Tests: 15/15 PASS (V3.3–V3.5 and V3.8 targeted suite).
- 48 of 48 scenarios completed on Upbit 2026-09 one-minute BTC and ETH data.
- Base simulated each-side fee 0.05%; adverse fee-equivalent **extra cost per side** 0, 0.02, 0.05, 0.10 percentage points. This is NOT fill-price slippage, market depth, or actual exchange execution.
- Input BTC 43,197 records; ETH 43,165 records. Close-triggered hypothetical fills. No live action.

## September static grid cumulative returns (%)
| Instrument | gap | +0 cost | +0.02% | +0.05% | +0.10% |
|---|---:|---:|---:|---:|---:|
| BTC | 0.14% | +0.3525 | +0.0038 | -0.3964 | -1.0636 |
| BTC | 0.50% | +1.0685 | +0.9615 | +0.8011 | +0.4000 |
| BTC | 1.00% | +3.3005 | +3.1531 | +2.9320 | +2.5635 |
| ETH | 0.14% | +2.9370 | +1.0762 | -1.0863 | -3.8219 |
| ETH | 0.50% | +6.0371 | +5.4622 | +4.6000 | +3.0839 |
| ETH | 1.00% | +5.1947 | +4.9669 | +4.6251 | +4.0556 |

## Additional high-priority comparisons
- ETH Static 0.50%, +0.10% extra per-side: return +3.0839%, MDD 4.0843%, 84 hypothetical fills, charged expense proxy 1,263.28 KRW.
- ETH Static 1.00%, +0.10%: +4.0556%, MDD 3.0714%, 34 fills, cost 512.59 KRW. Better return and lower MDD in this one-month extreme-cost stress.
- BTC Static 1.00%, +0.10%: +2.5635%, MDD 4.1852%, 22 fills, cost 331.65 KRW.
- ETH Static 0.14%, +0.10%: -3.8219%, MDD 6.4451%, 164 fills. 0.14%-gap fragile.
- Rolling700 ETH 0.50%, extra per-side +0.10%: +2.7199%, MDD 4.5014%, 93 fills; worse than static 0.50%.
- Rolling700 ETH 1.00%, extra per-side +0.10%: +3.2780%, MDD 2.7965%, 33 fills; low MDD but lower return than static 1.00%.
- Test runner changes effective ledger fee for each scenario; changing fee can change funded order count, fill paths and hence MDD/fill totals. **Not a controlled fixed-execution counterfactual.**
- Single month, parameters looked at in-sample; no annualized claim / no 10% annual objective validated.

## Next gates
1. Require fixed-trade-path cost attribution vs rerun-fully-adaptive fee response; decompose funding/rounding impacts.
2. Build real limit-order fill uncertainty and explicit favorable/unfavorable OHLC order with queue, spread, minimum KRW tick assumptions; integrate expense model without calling it price slippage.
3. Additional complete non-overlapping months, walk-forward, cash/hold benchmark, max-drawdown and exposure reporting.
4. Keep LIVE execution/config unchanged.
