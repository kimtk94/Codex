# 2025 Four-Arm Regime Attribution — verified result and decision

Evidence: [GitHub Actions Run #5](https://github.com/kimtk94/Codex/actions/runs/39124502619), job 117666686744, artifact 12136026979. Strict OHLC 1-minute ETH, capital 1,000,000 KRW, fee 0.1%, 100 levels.

| policy | 1.0% return | 1.0% MDD | 1.5% return | 1.5% MDD |
|---|---:|---:|---:|---:|
| baseline | +0.3355% | -51.6868% | +5.3264% | -47.3003% |
| inhibit_new_buys | -16.4944% | -30.0517% | -13.4585% | -30.5843% |
| cancel_resting_buys | -17.5256% | -29.0269% | -13.8398% | -29.6195% |
| reseed_on_up | -16.8708% | -29.0268% | -13.5563% | -29.6195% |

**Decision:** all three gated policies underperform baseline on return, despite lower MDD. No LIVE change or selection.

**Integrity caveats:**
- This policy attribution remains exploratory and uses 1-minute OHLC proxies, not queue-position or exchange fill confirmations.
- `inhibit_new_buys` still handles gaps through original `cancel();seed(close)`, which can create resting buys during DOWN; existing bids also persist. It must be renamed or corrected before strong causal claims.
- Comparison has not isolated equal exposure, liquidation cost, re-entry timing, or a 2024/2026 out-of-sample protocol.
- A 60-day warmup built from completed KST daily candles precedes each decision. Verify against a fully independent, continuous period split.

**Next gate:** prioritize changes to fill accounting and gap invariants; only afterward rerun 2024–2026 walk-forward tests. A 10% minimum return target and explicit MDD gate must be assessed jointly. Do not conflate reduced MDD with profitable strategy.
