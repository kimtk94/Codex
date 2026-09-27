# MULTI_ORGAN_AGING_MASTER

Updated: 2026-09-27

## 1. Working concept

**Longitudinal multi-organ biological aging in KoGES**

Core chain:

repeated routine biomarkers
→ organ-specific predicted age
→ age acceleration
→ longitudinal aging pace
→ cross-organ discordance
→ multi-organ acceleration
→ incident organ dysfunction / multimorbidity
→ optional genetic validation

Primary organ systems:
- metabolic
- renal
- hepatic
- vascular

## 2. Why this is separate from CKD and Metabolic Resilience

This project asks whether different physiological systems age at different rates
within the same person. CKD focuses on kidney causal proteogenomics. Metabolic
Resilience focuses on stability despite metabolic burden. Multi-organ Aging uses
the same longitudinal KoGES infrastructure but has a distinct primary phenotype.

## 3. Bias-control rules

1. Freeze organ-feature definitions before testing clinical outcomes.
2. Use subject-level cross-fitting: every participant's full longitudinal trajectory must be scored by an organ clock that was not trained on that participant.
3. Correct raw age gaps for chronological-age dependence.
4. Do not choose organ definitions based on downstream outcome significance.
5. Require at least three repeated visits for primary aging-pace estimation.
6. Keep discovery and outcome testing logically separated.
7. Treat public KoGES training files as pipeline validation, not final inference.
8. Refit all models in the approved thesis dataset before reporting final estimates.

## 4. Primary organ panels

### Metabolic
BMI, waist circumference, fasting glucose, HbA1c, HDL-C, LDL-C, triglycerides.

### Renal
Creatinine, BUN, UACR and other age-independent renal biomarkers when available.

**Do not use eGFR as an organ-age predictor**, because standard eGFR equations contain chronological age. eGFR is retained as an outcome/validation phenotype.

### Hepatic
AST, ALT, GGT, albumin when available.

### Vascular
SBP, DBP, pulse pressure, mean arterial pressure.

Optional future systems:
- inflammatory
- hematologic
- pulmonary

## 5. Main phenotypes

For each organ:
- predicted organ age
- raw organ-age gap = predicted age - chronological age
- age-adjusted organ-age acceleration
- longitudinal organ-age acceleration slope
- predicted-age pace

Across organs:
- mean aging acceleration
- maximum organ acceleration
- number of accelerated organs
- within-person organ discordance
- organ-aging cluster

## 6. Outcome layer

When source variables are available:
- incident reduced kidney function / CKD proxy
- incident dysglycemia / diabetes proxy
- incident hypertension proxy
- hepatic deterioration proxy
- multi-organ deterioration count

Continuous marker change should be retained even when threshold-based outcomes are unavailable.

## 7. Genetics bridge

Optional, after phenotype freezing:
- candidate PRS → organ aging pace
- pathway-specific PRS → organ-specific acceleration
- shared genetic architecture between organ-aging phenotypes
- integration with CKD / metabolic candidate loci without redefining the aging phenotype

## 8. Immediate execution order

1. Audit follow_01–follow_07 and baseline files.
2. Confirm subject ID and visit encoding.
3. Freeze variable alias map.
4. Build harmonized panel.
5. Train organ-age models and generate subject-level cross-fitted scores across all visits.
6. Estimate aging slopes from the cross-fitted longitudinal scores.
7. Run cross-organ discordance / clustering.
8. Build incident outcomes.
9. Run outcome associations.
10. Add genetics only after phenotype QC.


## 9. Public KoGES prototype status — 2026-09-27

Public training data are used only for workflow QA.

- 1,000 participants; 4,535 longitudinal rows; five waves (baseline through F4).
- Exact examination dates are used for longitudinal time.
- KoGES numeric missing sentinels are converted to missing values before modeling.
- Public-data trainable organ clocks: cardiovascular and metabolic.
- Renal/hepatic/inflammatory/pulmonary clocks remain unavailable because the education files do not contain enough repeated features.
- Primary longitudinal design is now a landmark design:
  - exposure window: baseline through F2
  - outcome window: F3 through F4
- Full-window pace and two-organ clustering are descriptive/sensitivity analyses only.
- Continuous discordance is preferred over cluster labels.
- Final thesis inference requires the approved controlled KoGES dataset and >=3 organ systems.

### Reference-sample definition

Clock reference participants should be:
- age 40–75,
- without established HTN/T2D/CKD/CVD history,
- without baseline BP >=140/90,
- without baseline fasting glucose >=126 mg/dL or HbA1c >=6.5% when measured.

### Outcome-testing rule

The primary prospective question is whether **pre-landmark organ-aging pace predicts subsequent incident organ dysfunction**. The exposure and outcome windows must not overlap. The primary sensitivity model additionally adjusts for baseline organ-age acceleration to test whether longitudinal pace adds information beyond starting organ state.


### Cross-fitting rule

For primary within-cohort inference, the final deployment clock must **not** be used to score participants who contributed to its training. Participants are partitioned into outer subject folds. For each fold:

1. train/tune the organ clock using healthy-reference participants from the other folds,
2. estimate age-gap residualization and scaling from training participants only,
3. score every visit of the held-out participants,
4. calculate longitudinal pace from those held-out scores.

The all-data final clock is retained only for external/deployment scoring. This prevents participant-level phenotype overfit from contaminating longitudinal pace and outcome models.


### Robustness gate before interpreting prospective effects

After subject-level cross-fitting and landmark outcome construction, the following must be checked before any effect is interpreted:

1. baseline organ acceleration vs pace coupling (correlation/VIF),
2. orthogonalized pace sensitivity,
3. proportional-hazards assumption for the joint Cox model,
4. subject bootstrap stability of pace HR, delta C-index and delta AIC,
5. landmark-window sensitivity when later controlled waves are available.

Public-data associations remain proof-of-concept only, regardless of nominal p-values.


## 10. Public prototype robustness results — 2026-09-27

Subject-level cross-fitting preserved both clock performance and prospective associations.

### Cardiovascular aging pace -> incident HTN
- Cross-fitted joint Cox HR per SD: approximately 1.77.
- Orthogonalized pace HR per SD: approximately 1.66.
- Cox proportional-hazards diagnostics passed for pace, baseline organ state, age and sex.
- 500-replicate bootstrap: median HR approximately 1.80, 95% bootstrap interval approximately 1.36-2.37.
- Pace improved prediction beyond baseline organ acceleration in almost all bootstrap samples:
  - positive delta C-index in approximately 99.4%,
  - lower AIC in approximately 99.2%.

Interpretation: strong workflow-level proof of concept, still not thesis inference because the public KoGES training dataset is educational/prototype data and events are limited.

### Metabolic aging pace -> incident T2D
- Cross-fitted joint Cox HR per SD: approximately 1.81.
- Orthogonalized pace HR per SD: approximately 1.67.
- Bootstrap HR direction was stable, but prediction-improvement intervals were less stable than for HTN.
- Cox PH tests indicated violations for metabolic pace and sex.

Interpretation: supportive prospective signal, but a single time-invariant Cox HR should not be treated as the primary summary. A discrete-time / time-varying effect sensitivity analysis is required.

### Current phenotype prioritization
1. Organ-specific longitudinal pace: primary.
2. Baseline organ acceleration: comparator/covariate.
3. Multi-organ mean pace: exploratory.
4. Cross-organ discordance: exploratory; no clear public-prototype association.
5. Two-organ clusters: descriptive only.

### Remaining public-prototype robustness work
- discrete-time complementary-log-log survival analysis for interval-observed diagnoses,
- time-varying pace effect assessment where PH is violated,
- retain bootstrap and PH diagnostics as mandatory reporting items.

Final controlled-data inference still requires >=3 organ systems to justify a multi-organ thesis framing.


## 11. Public prototype discrete-time survival decision — 2026-09-27

Because incident HTN/T2D is observed at follow-up visits rather than at exact onset dates, the prospective public-prototype analysis should use a **discrete-time complementary-log-log model** as the primary event model. Cox proportional-hazards models are retained as sensitivity analyses.

### Cardiovascular pace -> incident HTN
- Constant-effect discrete-time pace HR per SD: ~1.67.
- F3 interval HR: ~1.61.
- F4 interval HR: ~1.72.
- pace×interval interaction: not supported.
- Time-varying model has worse AIC than the constant-effect model.

Decision: use the constant-effect discrete-time HR as the primary public-prototype summary.

### Metabolic pace -> incident T2D
- Constant-effect discrete-time pace HR per SD: ~2.01.
- F3 interval HR: ~1.76.
- F4 interval HR: ~2.23.
- pace×interval interaction: not supported.
- Time-varying model does not materially improve AIC despite the earlier Cox PH diagnostic.

Decision: use the constant-effect discrete-time model as the parsimonious public-prototype summary, while retaining the Cox PH violation as a sensitivity caveat because event counts are small.

### Current methodological hierarchy
1. Subject-level cross-fitted organ-age scores.
2. Pre-landmark longitudinal organ-aging pace.
3. Discrete-time cloglog prospective outcome model for visit-observed incident diagnoses.
4. Baseline organ acceleration adjustment.
5. Orthogonalized-pace sensitivity.
6. Bootstrap stability and Cox PH checks.
7. Multi-organ mean/discordance/clustering as exploratory only in the two-organ public prototype.

Landmark-window sensitivity is deferred to the controlled KoGES dataset because the five-wave public training subset provides only one defensible >=3-visit exposure window with >=2 post-landmark outcome waves.
