# Multi-organ Aging — Public Prototype Checkpoint

Date: 2026-09-27  
Canonical code path: `research/multi_organ_aging`  
Branch: `research/multi-organ-aging-20260927`

> **Scope guardrail:** all results below come from KoGES public training/prototype data and are workflow-validation results, not final thesis inference.

## 1. Frozen methodological structure

1. Harmonize repeated KoGES biomarkers using exact examination dates.
2. Remove KoGES numeric missing-value sentinels and apply broad physiologic QC.
3. Train organ-age clocks in a strict disease-free baseline reference.
4. Score the full longitudinal trajectory using **subject-level outer cross-fitting**.
5. Estimate pre-landmark organ-specific aging pace.
6. Keep exposure and outcome windows non-overlapping.
7. Model visit-observed incident disease with **discrete-time complementary-log-log survival models**.
8. Retain Cox models, orthogonalized pace, bootstrap, PH diagnostics and discordance analyses as sensitivity/exploratory layers.

## 2. Public prototype data

- Participants: 1,000
- Longitudinal rows: 4,535
- Waves: baseline + F1–F4
- Exact examination dates available for all retained rows.
- Landmark pace exposure window: baseline through F2.
- Incident outcome window: F3–F4.
- Participants with landmark pace: 938.

## 3. Trainable public-data organ clocks

### Cardiovascular
Features:
- SBP
- DBP
- heart rate
- pulse pressure
- BMI
- waist circumference

Subject-level cross-fitted performance:
- strict reference N = 566
- OOF MAE ≈ 6.58 years
- OOF R² ≈ 0.20

### Metabolic
Features:
- fasting glucose
- HbA1c
- insulin
- total cholesterol
- HDL
- triglycerides
- TyG
- BMI
- waist circumference

Subject-level cross-fitted performance:
- strict reference N = 566
- OOF MAE ≈ 6.83 years
- OOF R² ≈ 0.12

### Not currently trainable in the public subset
- renal
- hepatic
- inflammatory/hematologic
- pulmonary

The public subset therefore validates the method but does **not** by itself justify a final multi-organ thesis claim.

## 4. Prospective proof-of-concept

### Cardiovascular aging pace -> incident HTN
Model-eligible:
- N = 666
- events = 38

Robustness:
- joint Cox HR per SD ≈ 1.77
- orthogonalized pace HR per SD ≈ 1.66
- 500-bootstrap median HR ≈ 1.80
- bootstrap HR 95% interval ≈ 1.36–2.37
- positive ΔC-index in ≈ 99.4% of bootstrap samples
- lower AIC with pace in ≈ 99.2%
- PH diagnostics passed

Discrete-time primary prototype:
- constant-effect cloglog HR per SD ≈ 1.67
- F3 interval HR ≈ 1.61
- F4 interval HR ≈ 1.72
- pace×interval interaction not supported
- constant-effect model preferred by AIC

Interpretation: strong workflow-level proof of concept.

### Metabolic aging pace -> incident T2D
Model-eligible:
- N = 842
- events = 22

Robustness:
- joint Cox HR per SD ≈ 1.81
- orthogonalized pace HR per SD ≈ 1.67
- 500-bootstrap median HR ≈ 1.80
- bootstrap HR 95% interval ≈ 1.24–2.55
- prediction-improvement bootstrap distributions less stable than HTN
- Cox PH diagnostics flagged metabolic pace and sex

Discrete-time primary prototype:
- constant-effect cloglog HR per SD ≈ 2.01
- F3 interval HR ≈ 1.76
- F4 interval HR ≈ 2.23
- pace×interval interaction not supported
- time-varying model did not materially improve AIC

Interpretation: supportive prospective proof of concept; event count remains small.

## 5. Phenotype priority

1. **Organ-specific longitudinal aging pace** — primary phenotype.
2. Baseline organ acceleration — comparator/covariate.
3. Multi-organ mean pace — exploratory.
4. Cross-organ discordance — exploratory.
5. Two-organ clustering — descriptive only in the public prototype.

## 6. Controlled-data go/no-go criteria

Before final thesis inference, the controlled KoGES dataset should demonstrate:

- at least 3 organ systems with enough repeated age-independent biomarkers,
- at least 3 repeated visits for primary pace estimation,
- exact or harmonizable examination timing,
- adequate incident outcome counts after the landmark,
- stable cross-fitted clock performance,
- no outcome/exposure window overlap.

Preferred target: 4 organ systems (vascular/cardiovascular, metabolic, renal, hepatic).

## 7. Next action

Run the controlled-data readiness audit before fitting any controlled-data clock or outcome model.

Primary command:

```bash
bash scripts/run_controlled_readiness.sh
```

Do not commit individual-level controlled KoGES data or row-level outputs containing direct identifiers.
