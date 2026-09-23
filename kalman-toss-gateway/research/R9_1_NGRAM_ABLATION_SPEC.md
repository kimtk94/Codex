# Kalman R9.1 — GDELT NGram Attention Ablation

**Pre-registered:** 2026-09-23  
**Mode:** RESEARCH_ONLY  
**Champion:** R5.1_BASE_HGB  
**Production/LIVE:** unchanged

## 1. Admission

R9-NG historical readiness passed before this experiment was defined:

- universe: 93
- supported aliases: 93
- symbols with historical mentions: 91
- recovered rows before bounded filter: 99,092
- bounded 2024-08-01 through 2026-09-01 rows: 64,435
- usable span: 25.002 months
- duplicate symbol/day rows: 0
- all readiness gates: PASS
- historical source result was mirrored to Neon research tables
- no production writes

No additional GDELT historical query is required for R9.1.

## 2. Experimental question

Does **symbol-specific company-name news mention intensity** add predictive information beyond the frozen R5 base feature family?

This is a single bounded ablation. No sentiment, article text, LLM label, event taxonomy, ticker search, or post-result feature search is allowed.

## 3. Frozen news features

Exactly three R9-NG features are admitted:

1. `ngram_log1p_d1`
   - `log1p(mention_count)` for the latest completed UTC day.

2. `ngram_log1p_7d`
   - `log1p(sum(mention_count))` over the latest 7 completed UTC calendar days.

3. `ngram_abnormal_z_30d`
   - latest completed day's `log1p(mention_count)` standardized against the preceding 30 completed UTC days;
   - the current day is excluded from the reference mean/std;
   - zero is used only when the historical std is effectively zero or the burn-in is insufficient.

Missing symbol/day rows in the GDELT result are calendar-completed to zero mentions before feature calculation.

No alternative lookback, weighting, half-life, transformation, alias, or feature subset may be tried after performance inspection inside R9.1.

## 4. PIT contract

For an R5 hourly bar with timestamp `timestamp`:

- `signal_as_of = timestamp + 60 minutes`
- feature day = UTC calendar day strictly before `DATE(signal_as_of)`
- same UTC day mention information is forbidden
- future UTC day information is forbidden

Thus a signal on UTC day D can use data only through D-1.

Historical news starts 2024-08-01. To provide a full 30-day pre-signal burn-in, model training rows start at 2024-09-01 UTC.

## 5. Evaluation folds

Only folds fully after R9 feature readiness are admitted:

- E5_2025H1
- E6_2025H2
- E7_2026_JAN_APR
- E8_2026_MAY_CUTOFF

The final research cutoff remains 2026-09-02 13:30 UTC.

## 6. Models

Three references are reported.

### Frozen champion
`R5C0_HGB_REFERENCE`

The frozen R5.1 ledger on the admitted R9 folds.

### Window-matched control
`R9C0_WINDOW_MATCHED_BASE`

- same HGB model template as frozen R5 research
- same R9 feature-ready training rows
- BASE_FEATURES only
- same test rows and execution simulator as challenger

This control isolates the effect of the shorter R9 historical window from the news feature effect.

### Single challenger
`R9C1_NGRAM_ATTENTION`

- same HGB model template
- same train/test rows as R9C0
- BASE_FEATURES + the three frozen R9-NG features
- no hyperparameter search introduced by R9.1

## 7. Integrity gates

All must pass before performance interpretation:

- R9 readiness manifest PASS
- frozen universe = 93
- base feature reconciliation PASS
- frozen target reconciliation PASS
- no missing news features in feature-ready training rows
- >= 80 symbols per evaluated timestamp
- exact control/challenger decision schedule match
- exact frozen-R5/challenger decision schedule match
- research_only = true
- production_changed = false
- live_action = NONE

## 8. Frozen survivor gates

R9C1 is a research survivor only if **all** are true:

- trades >= 150
- challenger log growth > R9C0 log growth
- challenger profit factor >= R9C0 profit factor
- challenger max drawdown no worse than R9C0 by more than 2 percentage points
- challenger log growth > frozen R5 log growth on the same folds
- challenger profit factor >= frozen R5 profit factor on the same folds
- positive paired folds versus R9C0 >= 3 of 4
- 95% moving-block bootstrap lower CI for paired daily log-growth difference > 0
- one-sided bootstrap p < 0.05
- effective names >= 5
- top ticker share <= 35%

Bootstrap:
- moving block = 5 calendar days
- repetitions = 2,000
- RNG seed inherited from the frozen R8 research harness

Exactly one challenger is tested, so no multi-candidate multiplicity correction is required.

## 9. Decision rule

If any survivor gate fails:

- `research_survivor=false`
- `promotion_eligible=false`
- R5.1 remains champion
- no tuning of the R9.1 news features is permitted inside this experiment

If all gates pass:

- `research_survivor=true`
- `promotion_eligible=true` means research eligibility only
- LIVE remains unchanged
- any production promotion requires a separate guarded deployment decision

## 10. Production invariant

R9.1 does not write or alter:

- `strategy_signal`
- LIVE orders
- position sizing
- exit rules
- R5.1 model artifacts
- R5-EXIT-V1
- production dashboard snapshots

The experiment writes research artifacts only.
