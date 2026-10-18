# Regime Pilot #2 — Decision and corrective experiment (2026-10-18)

Run: https://github.com/kimtk94/Codex/actions/runs/39123185067

| Grid | Baseline return | Filtered return | Baseline MDD | Filtered MDD |
|---|---:|---:|---:|---:|
| 1.0% / 100 | +0.3355% | -17.0125% | -51.6868% | -29.8753% |
| 1.5% / 100 | +5.3264% | -13.4433% | -47.3003% | -30.2910% |

**Verdict:** Reject the current filter for return improvement. It reduces observed drawdown but materially lowers profit. No live deployment.

## Source-review blockers

1. The gap-reset branch in `grid_regime_ssh_worker.py` invokes `cancel(); seed(close)` and `continue` before the regime gate, potentially placing buys during a DOWN regime.
2. On UP transition, the implementation cancels and reseeds all orders; this confounds the effect of prohibiting new buys.
3. Equity is measured in the original simulator's OHLC model, not verified orderbook fills; liquidation costs and evolving exchange tick rules are not modeled.
4. Pilot only tests 2025; there is no out-of-sample acceptance evidence.

## Next isolated research checks

- Invariant: no reserved BUY order may remain after processing a DOWN/WARMUP candle, including after a data gap.
- Attribution arms: baseline / inhibit replacement buys only / cancel resting buys too / cancel-and-reseed at every UP transition. State explicitly whether sell orders remain.
- Ensure `cancel` and `seed` preserve cash/asset reservations; no overselling, repeated key mutation, or phantom position release.
- Warmup: previous completed KST day only, independent of tested year's initial state.
- 2024/2025/2026 YTD evaluation: return, MDD, fill count, fees, exposure, regime-days, both-side touched bars and gap-resets.
- Freeze parameter choices before reading out-of-sample performance and retain 10%-return target and explicit drawdown ceiling as research gates.

No changes to original backtest engine, live strategy, trading credentials, or server environment are authorized.
