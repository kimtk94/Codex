# Multi-regime cross-tab audit (167 crash-rebound entry events)

Read-only, exploratory; do not deploy. Source: locally recomputed from upbit_liquidity_regime_entry_audit.csv. Price data for 190 ever-still-listed cohorts; 167 matched crash/rebound entries.

Size boundaries fixed from 2023–25 training only (trailing completed 1-hour KRW turnover):
L1 <= 3.469 bn KRW, L2 <= 19.912 bn, L3 <=39.699 bn, L4 >39.699 bn.
The variable crash_to_entry is **elapsed time from observed crash to simulated entry**, NOT elapsed time from listing to first crash. Never use it as a crash-timing variable.

2023–25 training:
- L1 entered 4–24h after crash (n=17): 29.4% 4h re-crash, -1.72% avg net
- L1 entered 1–4h after crash (n=9): 77.8% re-crash, -1.80% avg net
- L4 entered 1–4h after crash (n=26): 88.5% re-crash, -0.75% avg net

2026 exploratory test (already inspected in model development, NOT fresh holdout):
- L1 entered 4–24h post-crash (n=16): 43.8% re-crash, -1.01% avg net
- L1 entered 1–4h post-crash (n=16): 37.5% re-crash, -1.29% avg net
- L2 entered 1–4h post-crash (n=23): 78.3% re-crash, +0.70% avg net
- High-L3/4 has only n=3 combined; do not claim regime robustness.

Interpretation: All training cross-group mean returns are negative. A 2026 positive-slice mean after selection is insufficient evidence for a profitable policy. Re-crash probability, realized P&L and executable order size are separate outputs.

Volume change (last completed 1h vs first 1h of listing) is strongly concentrated in cooling <=25% of opening turnover (81 training, 49 test), making most cross cells underpowered. No live policy changes.

Next: rebuild features on every observed 15m bar, calculate first-crash timing from listing separately, add historic BTC regime, quote spread/order book validation, walk-forward with purged overlapping cohorts, new unseen forward-time holdout, and portfolio-level capital allocation / MDD.
