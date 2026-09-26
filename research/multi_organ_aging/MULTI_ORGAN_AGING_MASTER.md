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
eGFR, creatinine, BUN, UACR when available.

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
