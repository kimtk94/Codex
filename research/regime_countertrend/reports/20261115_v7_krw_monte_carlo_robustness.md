# CFM-V7 KRW Monte Carlo: stationary blocks, shared market/FX shocks and pinned vintage

**As of 2026-11-15. Research-only / NO LIVE changes.**

## Verified implementation and source

- First dynamic-source [GitHub Actions #43708796790](https://github.com/kimtk94/Codex/actions/runs/43708796790): **145/145 tests PASS**, Monte Carlo result artifact **#14159488405**, 4,258,073-byte ZIP.
- Drive archive: [Kalman V7 Monte Carlo results](https://drive.google.com/file/d/1cCoksVVi6d0_lWydynAJrb97Ntr8wOh_/view?usp=drivesdk), `model_tests` folder.
- Data version: **2026-11-15 re-fetched** 2022-01-05 through 2026-11-04 synthetic daily cash balance paths; adjusted-price provider revision relative to 2026-11-11 base was previously identified. This is NOT an untouched research window.
- 4 strategies (V4, V5 × USD retained vs convert on sale), 5 ETF benchmarks (QQQ, SPY, IWM, SMH, GLD) and USD-only/KRW-only cash = **11 jointly simulated equity paths**.
- Currency: KRW. USD/KRW is KRW per USD. USD cash retention and per-sale reconversion are different FX exposures, not just different FX transaction fees.
- Historical 10bp-per-side FX conversion policy curves are resampled; 0bp and 25bp fee alternatives are **deterministic historical scenarios**, not 0/25bp Monte Carlo estimates.

## Method

**Synchronous stationary bootstrap**, not iid trade shuffle:

1. Historical 1213 EOD marks produce 1212 calendar-aligned daily return vectors.
2. Select the *same* resampled trading-day indices for each strategy, passive ETF, and the currency-only benchmark, preserving same-day correlations.
3. Randomly restart a sequential block with probability `1 / L` where mean block length `L = 5, 20, or 60` trading days, preserving multiday stress to the extent represented in the source.
4. Simulate **2000 paths × 3 mean block lengths × 2 horizons** (252 trading days and 1212 trading days) = **12,000 jointly resampled 11-asset paths**; deterministic RNG seed **20261115**.
5. Apply initial synthetic fee/cash conversion only **once** per path, not on each resampled block. Estimate terminal profit/loss, 5% lower-tail terminal return, risk of EOD MDD below -20% or -35%, and paired relative outcome against QQQ/SPY/USD cash.

This is a bootstrap **of already-generated synthetic strategy daily PnL**. It does not regenerate signals, trades, high/low barrier paths, or the endogenous capital scheduling. This limits what conclusions can be drawn about unseen market states.

## One-year 252 sessions, 20-session mean blocks

| Portfolio | P(negative terminal KRW) | P(EOD MDD <= -20%) | P(underperform KRW QQQ) | Median terminal KRW | 5th percentile terminal KRW |
|---|---:|---:|---:|---:|---:|
| V4 ETF market, retain USD | **37.4%** | **4.75%** | **70.8%** | **+3.94%** | **-14.15%** |
| V5 KRW regime, retain USD | **38.3%** | **5.00%** | **70.65%** | **+3.95%** | **-14.39%** |
| V4 ETF market, convert after every sale | **62.9%** | **3.20%** | **84.0%** | **-2.78%** | **-16.09%** |
| V5 KRW regime, convert after every sale | **64.55%** | **3.90%** | **83.4%** | **-3.14%** | **-16.49%** |

*These figures are proportions within the historical bootstrap distribution, not calibrated real-market probabilities. QQQ passive leverage/cash exposure is different; relative returns are not risk-adjusted.*

### Block length stress (retain USD)

| Horizon | Mean block | V4 P(loss) | V5 P(loss) | V4 P(MDD<=-20%) | V5 P(MDD<=-20%) |
|---|---:|---:|---:|---:|---:|
| 252 sessions | 5 | 35.0% | 35.3% | 4.30% | 4.85% |
| 252 sessions | 20 | 37.4% | 38.3% | 4.75% | 5.00% |
| 252 sessions | 60 | 33.95% | 34.75% | 6.55% | 5.95% |
| 1212 sessions | 5 | 14.25% | 15.65% | 40.25% | 42.45% |
| 1212 sessions | 20 | 14.65% | 16.05% | 42.55% | 44.15% |
| 1212 sessions | 60 | 14.45% | 14.85% | 46.15% | 46.60% |

**Why 1y losses and ~5y MDD are different:** A strategy can finish a multi-year synthetic period above its initial capital while experiencing large interim mark-to-market losses. The numbers are not annualized rates.

## Exchange cost and settlement sensitivity

Observed V6 cash policy on same 2026-11-15 vintage, **full 2022–2026 historical account**, not simulated Monte Carlo distributions:

| Portfolio | 0bp FX per side | 10bp FX per side | 25bp FX per side |
|---|---:|---:|---:|
| V4, USD retained | +31.11% | +30.98% | +30.78% |
| V4, convert on each sale | +10.11% | -7.80% | -29.37% |
| V5, USD retained | +30.42% | +30.29% | +30.09% |
| V5, convert on each sale | +9.68% | -9.51% | -32.21% |

Real-life brokerage FX discount, actual conversion frequency and bank settlement evidence are **NOT verified**. A per-sale full-notional currency conversion is a *scenario*, not necessarily the user's real account behavior.

## Historical source-vintage and reproducibility gate

- `krw_monte_carlo_v7.py`: risk generator, exact daily curve alignment, FX policy integrity, initial cost once, common block indices.
- `test_krw_monte_carlo_v7.py`: 6 direct tests; unit/leakage suite **145/145 PASS** as of the first run.
- `monte_carlo_pinned_vintage_v7.json`: **SHA256 of all 10 inputs**, GitHub run/artifact ID and expected exact RNG outputs.
- New `kalman-krw-monte-carlo-v7.yml`: replay from archived fixed historical artifact, never Yahoo re-fetch. This new isolated workflow's run requires separate verification; a file being committed is NOT sufficient evidence of execution.
- In addition, `regime-countertrend-research.yml` has a pinned-source replay step with the same checksum/expected-distribution gate; this is independent of a new workflow's first-run registration.

No historical P&L variant may be silently substituted for another. If a price or USD/KRW vintage changes, report **HOLD_REVISED_RETROSPECTIVE_DATA**, even when all numerical tests pass.

## Verdict

`MONTE_CARLO_IMPLEMENTATION_PASS` on the completed 145-test workflow; **`MODEL_ALPHA_HOLD`**, **`FUTURE_OOS_HOLD`**, **`REAL_BROKER_FX_CASH_HOLD`**, **`LIVE_NO_CHANGE`**.

Monte Carlo is suitable as a **risk screen and sensitivity tool** before promotion, not a replacement for never-seen data, actual intraday fills, FX cash ledger, regime-aware external validation, or comparison to a risk-matched benchmark. No orders are placed, no REAL broker/Neon writes, no LIVE strategy is changed.
