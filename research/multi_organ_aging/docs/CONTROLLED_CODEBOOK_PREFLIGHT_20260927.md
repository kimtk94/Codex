# Controlled KoGES Codebook Preflight — 2026-09-27

Source reviewed: **KoGES 지역사회기반코호트 반복 추적조사 통합자료 코드북 (ver5.0, 2024-12)** from the connected project Drive.

This document records **codebook-supported expectations only**. No controlled individual-level dataset is currently present in `/srv/is-analysis/data/multi_organ_aging/controlled`, so every item below must be re-verified against the actual approved extract before inference.

## Key finding

The controlled/integrated KoGES schema appears substantially richer than the current public-training subset.

### Expected longitudinally feasible systems

**1. Cardiovascular / vascular — expected READY**
- repeated seated blood-pressure measurements are present across A01–A05,
- repeated BMI and waist measures are present,
- pulse pressure can be derived from a matched SBP/DBP pair.

**2. Metabolic — expected READY**
- fasting glucose (GLU0),
- HbA1c,
- fasting insulin (INS0),
- total cholesterol (TCHL),
- HDL,
- triglyceride,
- BMI / waist,
are repeated across the reviewed A01–A05 structure.

**3. Renal — expected READY**
- BUN is repeated,
- creatinine is repeated.

This is sufficient for the current renal minimum of two age-independent features. eGFR remains excluded from clock predictors because chronological age is embedded in standard eGFR equations.

**4. Inflammatory / hematologic — expected READY**
- WBC,
- hemoglobin,
- platelet
are repeated across the reviewed A01–A05 structure.

CRP/hsCRP changes assay/representation across waves and should be treated as a harmonization sensitivity rather than a required core feature.

**5. Pulmonary — expected READY**
The codebook contains repeated spirometry across A01–A05:
- measured/best FVC,
- measured/best FEV1,
- FEV1/FVC.

For biological-age modeling, measured values should be preferred over **predicted** spirometry values because predicted pulmonary values themselves encode age/sex/height reference equations and could reintroduce target leakage.

### Hepatic — expected HOLD under current prespecification

AST and ALT are repeated, but reviewed codebook entries indicate r-GTP, albumin and total bilirubin are largely baseline-only in the integrated repeated dataset. With the current hepatic minimum of three repeated features, the hepatic clock should remain unavailable unless the actual approved extract contains an additional repeated age-independent hepatic biomarker.

Do **not** lower the hepatic minimum merely to increase organ count after seeing outcomes.

## Expected organ count

If the approved controlled extract follows the reviewed integrated codebook:

- cardiovascular: likely ready
- metabolic: likely ready
- renal: likely ready
- inflammatory/hematologic: likely ready
- pulmonary: likely ready
- hepatic: likely not ready

Therefore the working expectation is **up to five longitudinal organ systems**, pending raw-data verification.

This is materially stronger than the two-organ public prototype and is sufficient to support a genuine multi-organ aging design if sample size, missingness and follow-up remain adequate.

## Integrated wide-file support

The controlled readiness audit now recognizes KoGES integrated columns such as:

- `A01_...`
- `A02_...`
- `A03_...`
- etc.

It can audit a **single wide integrated file** instead of requiring one file per wave.

Expected command after approved data arrive:

```bash
bash scripts/run_controlled_readiness.sh
```

A GO decision still requires actual-data verification of:
- participant ID,
- repeated chronological age,
- visit timing,
- nonmissing counts,
- units,
- assay/platform shifts,
- outcome coding,
- sufficient post-landmark events.

## Important leakage guard

For pulmonary clock construction:
- use observed FVC / FEV1 measurements,
- do not use predicted FVC, predicted FEV1, or percent-predicted values as age-clock predictors.

Predicted spirometry equations include demographic/reference information and can make chronological-age prediction artificially easy.

## Files

Machine-readable expected-variable manifest:

`config/controlled_codebook_manifest.tsv`
