# QLD 40-axis structured 10k: filter-budget and allocation-matched study

This follow-up preserves the **40 effective parameters** used in the prior fully random 10,000-configuration experiment. The first random experiment is archived at `QLD_40Axis_Independent_Random10000_20261031.zip` and its outcomes remain unchanged. The additional study was designed after observing excessive filtering in the first experiment, so **the research program has already adapted to historical results**; this is neither a blind confirmatory experiment nor a new independently untouched OOS period.

## Predeclared candidate generation for this run

- Create **10,000 distinct configurations plus one untouched baseline** with deterministic generator seed `20261102`.
- Divide equally among five predeclared strata: **0, 1, 2, 3, or 4 active restrictive signal-filter groups**. There are **2,000 configs per stratum**.
- Each of the 40 parameter axes can vary across the overall study. Twenty execution-management axes vary jointly in every stratum; 20 signal-gating axes are active only if selected for the stratum. Within the chosen gate budget, gate-group identities and levels are randomly sampled without using individual historical trade labels or returns. Invalid risk-reward constraints and equivalent normalized configurations are rejected.
- For the classifier probability cutoff, 0.45 or 0.50 is considered a permissive base; 0.55/0.60/0.65 is an active restrictive gate. The original classifier probabilities are trained with 2024 for 2025 and expanding 2024-25 for 2026 (label purge).
- The full combination is traded via the **same path-dependent, no-overlap cash ledger**, never by summing one-option results.
- Every configuration × two models × two years is simulated **twice**: with the policy's original investment/risk-budget settings, and as a cash-allocation counterfactual with `size=0.50` and `risk_budget=0`, while retaining every other option. Therefore expected portfolio runs are **10,001 × 2 × 2 × 2 = 80,008**. There is no rescaling of backtest returns by a numeric constant.
- **Matching a 50% nominal cash allocation is *not* matching stop-loss risk** across policies with different stop widths. Report that limitation explicitly. It nonetheless prevents a 25% size strategy from being called superior to a 100% strategy solely because it lost less capital.
- Every policy and both counterfactual results must survive complete 2025/2026 year/model ledger checks. Final report includes trade-count buckets and native / matched-50% per-year returns, daily-mark MDD, and market filter gate-budget coverage. Strategies with fewer than 15 completed trades in either year are excluded from the **exploratory leaderboard** but remain in the full dataset.

## Caveats

Selecting and testing 10,000 policies on 2025-2026 and adapting the experimental design based on the first experiment creates severe multiple-comparison/data-snooping risk. The highest-ranked policy is never a LIVE signal until evaluated on an **independent future period**, with point-in-time market data, realistic fills including bar-level ambiguity and slippage, and adequate trade count. Even within a fixed 50% cash allocation, percentage risk-at-stop, turnover, realized exposure and intrabar MDD vary.

The prior **100 model training repetitions** are a separate training-instability experiment; this run holds the OOS probability model fixed for each year and measures policy sensitivity instead.

No production code or execution permissions are modified. CI workflow: `.github/workflows/kalman-qld-structured-10k.yml`; implementation: `research/kalman_integrated_regime/structured_10k.py`; report: `structured_report.py`.
