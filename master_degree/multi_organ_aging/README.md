# Longitudinal Multi-Organ Aging Discordance

KoGES-centered longitudinal analysis of organ-specific biological-age-gap trajectories and cross-organ aging discordance.

## Primary question
Do renal, metabolic, hepatic, and vascular systems age at different rates within the same person, and does cross-organ aging discordance predict future disease burden beyond chronological age and conventional risk factors?

## Pipeline
- Stage 0: variable/file feasibility audit.
- Stage 1: harmonized person-wave panel.
- Stage 1B: organ-by-wave coverage and participant eligibility.
- Stage 2: primary Ridge organ-age models with participant-level cross-validation and age-bias correction.
- Stage 2B: optional Ridge / Elastic Net / HistGradientBoosting sensitivity benchmark.
- Stage 3: participant-level longitudinal BAG velocity.
- Stage 4: cross-organ discordance metrics and secondary phenotype classes.
- Stage 4B: phenotype distribution, correlation and extreme-value QC.
- Stage 5: prospective Cox models when validated outcome linkage is available.
- Stage 6: PRS association.
- Stage 6B: PLINK2 phenotype/covariate export for later GWAS.
- Stage 7: compact status report.

## Organ domains
- renal: creatinine, eGFR, BUN, UACR when available
- metabolic: glucose, HbA1c, TG, HDL, LDL, BMI, waist
- hepatic: AST, ALT, GGT, bilirubin, albumin
- vascular: SBP, DBP, pulse pressure, heart rate

## Reproducibility rules
Stage 0 pattern matching is discovery-only. Variable definitions and units must be reviewed and frozen before final modeling.
Cross-validation is always participant-level.
Outcome information must never enter organ-age training.
Continuous discordance traits are primary; phenotype classes are descriptive.

## Server
Project root: /srv/is-analysis/IS_Analysis_V3
Results: /srv/is-analysis/results/multi_organ_aging

Bootstrap:
bash master_degree/multi_organ_aging/scripts/bootstrap_server.sh

Run primary pipeline:
bash master_degree/multi_organ_aging/scripts/run_pipeline.sh

Run model sensitivity:
RUN_SENSITIVITY=1 bash master_degree/multi_organ_aging/scripts/run_pipeline.sh

## Google Drive
Remote root:
gdrive:MASTER_DEGREE/MULTI_ORGAN_AGING

Sync:
bash master_degree/multi_organ_aging/scripts/sync_gdrive.sh

The Drive sync uses rclone copy, not sync/delete.
