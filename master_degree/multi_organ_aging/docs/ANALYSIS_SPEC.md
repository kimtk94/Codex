# Multi-Organ Aging Analysis Specification

## 1. Primary estimand
The primary estimands are longitudinal organ-specific biological-age-gap velocities and within-person cross-organ discordance.

The project must not be reduced to cross-sectional chronological-age prediction accuracy.

## 2. Organ domains
Primary domains:
- renal
- metabolic
- hepatic
- vascular

A domain enters primary analysis only after variable identity, units, wave consistency, and missingness are audited.

## 3. Variable-map freeze
Stage 0 may use broad pattern matching for discovery only.
Before Stage 2:
1. review STAGE0_VARIABLE_CANDIDATES.tsv,
2. confirm source variable definitions and units,
3. freeze one canonical mapping per wave/domain feature,
4. document transformations,
5. do not revise mappings based on downstream associations.

## 4. Reference population
Primary organ-age models use a prespecified healthy-reference subset where possible.
Sensitivity analyses:
- all-participant training,
- sex-stratified models if sample size is adequate,
- nonlinear model benchmark.

## 5. Leakage control
All cross-validation must be split by participant, never by person-wave row.
No outcome data, future disease status, or downstream aging phenotype may be used to define the organ clock.

## 6. Age-bias correction
For each organ, estimate the expected predicted age conditional on chronological age using out-of-fold reference predictions.
The corrected biological age gap is:

BAG = predicted organ age - E(predicted organ age | chronological age)

This residualized BAG is used for trajectory estimation.

## 7. Longitudinal phenotype
For each participant and organ:
- baseline BAG,
- last BAG,
- BAG delta,
- OLS BAG slope per follow-up year,
- number of waves,
- follow-up span.

Primary velocity requires at least 2 observations.
High-confidence sensitivity analysis requires at least 3 observations and meaningful follow-up time.

## 8. Cross-organ discordance
Primary continuous metrics:
- mean standardized organ velocity,
- SD of standardized organ velocities,
- range of standardized organ velocities,
- pairwise organ velocity differences.

Descriptive classes are secondary and must not replace continuous analysis.

## 9. Outcome models
Outcome testing starts only after phenotype definitions are frozen.
Potential endpoints:
- incident multimorbidity,
- CVD,
- mortality,
- domain-specific disease.

Primary time-to-event model: Cox PH.
Report N, event count, HR per 1-SD phenotype, 95% CI, P and BH-FDR.

## 10. Genetics
Primary feasible genetics layer:
- external or internally computed PRS for kidney, T2D/metabolic, BP/CAD and obesity-related traits,
- association with continuous organ-aging velocities and discordance.

If individual-level genotype sample size and QC support it, export continuous phenotypes for PLINK2 GWAS as a later extension.

## 11. Sensitivity analyses
- >=3-wave participants,
- alternative healthy-reference definition,
- ridge vs elastic-net vs nonlinear model,
- sex-stratified analysis,
- exclusion of baseline disease,
- winsorized biomarkers,
- complete-case vs imputed model inputs,
- minimum follow-up threshold.

## 12. Interpretation
The organ-age output is a model-derived relative phenotype.
Do not claim literal tissue age or causal effects from observational organ-aging associations.
