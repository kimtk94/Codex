# QLD 40-axis independent random 10,000-policy experiment

Date of design: 2026-10-31. **Research-only; no LIVE execution access.**

## Design

This is a second, independent experiment alongside the existing 800-combination exploration. The 800 sweep does not inform any parameter draw. Candidate generation occurs without reading returns, trades, test labels, or performance.

- Sample exactly **10,000 distinct candidate policies** by drawing each of 40 raw parameter axes independently and uniformly over that axis's predeclared discrete levels; deterministic generator seed `20261101`.
- Reject logically invalid price/risk bounds (`min_rr`, credit-floor/cap); normalize inactive branches (unused trailing-stop / split-entry values) and reject duplicate resulting effective policies.
- A fixed unchanged reference configuration is prepended as control, **not counted** as one of the 10,000 random policies.
- Apply each of 10,001 configurations to two signal models (price-only, integrated-regime) and two distinct calendar-year evaluations (2025 and 2026 through Oct 30): total **40,004 full-portfolio simulations**.
- **Every joint scenario runs an entire position ledger** with entry delay, split buys, fixed/raised stops, partial sells, fees/slippage, position sizing, monthly throttle and cooldown. No additive attribution of independent option effects.
- Historical inputs: SIP QLD/QQQ 15-minute candles, 2024–2026, Alpaca `adjustment=all`; lagged daily macro price data from private Google Drive. One SIP download per CI run; 4 local parallel simulation workers, no raw proprietary bar artifacts.
- Report outcomes for all policies including no-trade policies, rather than removing nonperformers. The initial ranking requires at least **15 completed trades in each test year** to prevent zero-trade strategies from winning.
- Report pairwise option-level coverage; even 100% pairwise coverage does **not** imply 3-way or 40-way exhaustive coverage.
- Model-fitting uses a **fixed expanding OOS classifier per year and model**. The earlier 100× train-only bootstrap experiment remains distinct: this experiment has 10,000 random execution policies, **not** 10,000 × 100 trained classifiers.

## Non-negotiable interpretation

2025 and 2026 have already been observed and used for option comparison, so selecting a winner after testing 10,000 combinations creates severe multiple-testing / data-snooping risk. The ranking is **exploratory only**. Promotion requires independent post-selection data, order-fill/liquidity assumptions, a guardrail on concentration/low-trade regimes, and no direct LIVE modifications.

GitHub Actions workflow: `.github/workflows/kalman-qld-random-10k.yml`.
Reference implementation: `random_10k.py`; fixed 40-axis simulator `joint_policy.py`; paired-year aggregator `joint_report.py`.

Result files expected:
- `random10k_manifest.json`: independently sampled candidate details, completed 40,004 rows contract, pairwise coverage.
- `joint_all_results.json`: every policy × model (yearly comparisons and parameter values).
- `joint_leaderboard_summary.json`: baseline, exploratory Pareto-ish rankings and two-factor effect screen. All reported interaction contrasts are descriptive, not causal.
