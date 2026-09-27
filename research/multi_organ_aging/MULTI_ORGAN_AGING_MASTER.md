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
2. Use out-of-fold baseline predictions when estimating organ age in the training cohort.
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
5. Run OOF organ-age models.
6. Estimate aging slopes.
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
