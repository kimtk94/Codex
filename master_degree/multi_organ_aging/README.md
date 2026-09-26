# Longitudinal Multi-Organ Aging Discordance

This repository branch implements the coding scaffold for a KoGES-centered longitudinal multi-organ aging project.

## Primary question
Do renal, metabolic, hepatic, and vascular systems age at different rates within the same person, and does cross-organ aging discordance predict later multimorbidity, cardiovascular outcomes, or mortality beyond chronological age and conventional risk factors?

## Design
1. Stage 0: audit repeated KoGES waves and resolve candidate variables.
2. Stage 1: build a harmonized person-wave longitudinal panel.
3. Stage 2: train organ-specific age models using healthy-reference data and leakage-safe cross-validation.
4. Stage 3: estimate longitudinal organ age-gap trajectories and participant-specific aging velocities.
5. Stage 4: quantify cross-organ discordance and prespecified phenotype classes.
6. Stage 5: test prospective clinical outcomes.
7. Stage 6: test PRS/genetic associations with aging velocity and discordance.
8. Stage 7: build a compact reproducible report.

## Default organ domains
- renal: creatinine/eGFR/BUN/UACR where available
- metabolic: glucose/HbA1c/TG/HDL/LDL/BMI/waist
- hepatic: AST/ALT/GGT/bilirubin/albumin where available
- vascular: SBP/DBP/pulse pressure/heart rate where available

## Server paths
- project: /srv/is-analysis/IS_Analysis_V3
- input: /srv/is-analysis/data/multi_organ_aging
- results: /srv/is-analysis/results/multi_organ_aging
- KoGES public training default: /srv/is-analysis/data/metabolic_resilience/stage0_koges/public_training

## Google Drive
Remote convention:
gdrive:MASTER_DEGREE/MULTI_ORGAN_AGING

Use scripts/sync_gdrive.sh to mirror code/results without deleting remote files.

## Important analysis constraints
- Freeze variable mapping and phenotype definitions before outcome testing.
- Split/cross-validate by participant ID, never by person-wave row.
- Correct age-gap age bias using only training/reference information.
- Keep CKD and Metabolic Resilience results separate from this project.
- Treat mortality/CVD/multimorbidity as optional until valid linked outcomes are available.
