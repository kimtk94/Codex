# MULTI-ORGAN AGING MASTER

## Working title
Longitudinal Multi-Organ Aging Discordance in a Korean Population

## Core hypothesis
Within-person heterogeneity in organ-system aging trajectories carries information not captured by chronological age or a single systemic aging score.

## Primary phenotype family
For organ o and participant i:
- organ age gap: BAG_io(t) = predicted organ age - expected predicted age among same-aged reference participants
- organ aging velocity: slope of BAG_io over follow-up years
- discordance: dispersion of standardized organ-specific BAG or velocity within participant

Primary quantitative endpoints:
- renal velocity
- metabolic velocity
- hepatic velocity
- vascular velocity
- cross-organ velocity SD
- cross-organ velocity range
- renal-minus-metabolic velocity
- renal-minus-hepatic velocity
- vascular-minus-metabolic velocity

Prespecified descriptive classes:
- generalized accelerated
- generalized resilient
- discordant
- renal-first aging
- metabolic-first aging
- hepatic-first aging
- vascular-first aging

The quantitative traits are primary; classes are secondary summaries.

## Stage gates
### Stage 0 Feasibility
Require:
- stable subject ID
- chronological age
- sex if available
- at least 2 waves for trajectory work
- at least 2 usable biomarkers per organ domain for a minimally interpretable clock

### Stage 1 Harmonization
Create one row per participant-wave and retain raw units, missingness, wave index, age, and follow-up time.

### Stage 2 Organ age models
Primary model: ridge regression.
Sensitivity: elastic net / gradient boosting may be added later.
Use participant-level folds.
Fit age-bias correction on training/reference predictions only.

### Stage 3 Longitudinal aging
Estimate participant-specific slopes using repeated age-gap observations.
Require >=2 valid waves; flag >=3 waves as high-confidence trajectories.

### Stage 4 Discordance
Standardize organ velocities on a frozen reference distribution.
Compute cross-organ dispersion and pairwise differences.

### Stage 5 Outcomes
When linkage is valid:
- incident multimorbidity
- CVD
- mortality
- disease-domain-specific outcomes
Primary models: Cox proportional hazards with age, sex, baseline risk factors and organ-aging traits.

### Stage 6 Genetics
Optional extensions:
- BMI, T2D, BP, CAD, eGFR PRS
- GWAS of continuous organ-aging phenotypes if sample size/genotype access supports it
- external pQTL/MR only as a later mechanistic layer

## Separation from other MASTER DEGREE projects
CKD remains kidney-focused proteogenomic prioritization.
Metabolic Resilience remains protein-genetics + longitudinal metabolic stability.
Multi-Organ Aging focuses on longitudinal organ-specific age gaps and cross-organ discordance.
