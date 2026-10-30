# HCC MRI × RNA — Pixel/QC and tumor ROI selection evidence (2026-10-30)

**Source public dataset:** [LiverHccSeg v1.1](https://doi.org/10.5281/zenodo.8179129); case barcodes TCGA-LIHC.  
**Exact live evidence:** [14/14 PV real-pixel QC run #62](https://github.com/kimtk94/Codex/actions/runs/41065766643) and [14/14 liver/rater segmentation QC run #65](https://github.com/kimtk94/Codex/actions/runs/41067136933).

## Quality of evidence — do not confuse these analyses

1. **PV pixel QC:** Original publicly released PV NIfTI image was read and compared with a *single rater1_tumor1* NIfTI in **14/14 cases**. All have consistent 3D shape and source-to-tumor coordinate transform (max FOV corner offset 0mm), positive tumor voxels, finite tumor ROI MRI intensities, and a generated 3-plane reviewer PNG. **No imaging expert has certified the tumor contour.**
2. **Independent segmentation audit:** Full rater1 tumor set, same-label rater2 tumor mask and rater1 liver mask were read on **14/14**. All comparable coordinates; all 14 largest lesions have a rater2 matching-number contour with Dice. The criterion "largest rater1 tumor volume" is **proposed now, before looking at RNA association estimates**, not a validated lesion-selection standard; confirm lesion identity and freeze clinical criteria with a reviewer.
3. **Critical index lesion case:** TCGA-BC-A10Y has **three** rater1 tumors, and largest is tumor3 (740.18662 mL). The existing 14-case PV pixel/PNG audit used tumor1 (**6.9961 mL**) for this patient, so its PNG is **NOT the proposed index-lesion image**. Generate tumor3-specific source-PV pixel QC and visual overlay before any feature association using the proposed rule. All other 13 patients have tumor1 as the largest/published tumor mask.
4. These masks are **NOT** yet eligible radiogenomics patient counts. The correct claim ceiling remains **S0** until reviewer anatomy/clinical chronology and numeric RNA QC, with patient-level exclusions, are recorded.

## Results

- PV image + original rater1_tumor1 pixel QC **14/14 passed**, failures 0.
- Rater1/rater2 same tumor number Dice, representative maximum-volume lesion: **median 0.901575, range 0.81362–0.96057**.
- Selected lesion tumor-mask inclusion inside same-reader liver mask: **minimum 0.998778 (99.8778%)**; median 1.0.
- Representative lesion volume: **median 114.64354 mL**, range 6.00539–753.25977 mL.
- Exactly **1/14** patients has multiple rater1 tumor masks (3 lesions); exactly **1/14** changes representative lesion from tumor1 to tumor3.
- No independent clinical/reviewer confirmation that same-number rater1/rater2 tumor masks describe precisely the same individual lesion. Dice is segmentation-level overlap, **not** PyRadiomics feature ICC.

| Patient | R1 tumors | Proposed largest R1 tumor | Original tumor1 volume (mL) | Proposed ROI volume (mL) | R1/R2 same-label Dice | R1 tumor inside liver | New PV QC needed? |
|---|---:|---:|---:|---:|---:|---:|---|
| TCGA-BC-A10Y | 3 | tumor3 | 7.00 | 740.19 | 0.930 | 100.000% | YES — tumor3 |
| TCGA-BC-A3KG | 1 | tumor1 | 333.35 | 333.35 | 0.959 | 100.000% | No — tumor1 pixel QC done |
| TCGA-BC-A5W4 | 1 | tumor1 | 254.15 | 254.15 | 0.896 | 100.000% | No — tumor1 pixel QC done |
| TCGA-BC-A69I | 1 | tumor1 | 120.84 | 120.84 | 0.881 | 99.878% | No — tumor1 pixel QC done |
| TCGA-DD-A4NF | 1 | tumor1 | 15.01 | 15.01 | 0.848 | 100.000% | No — tumor1 pixel QC done |
| TCGA-DD-A4NH | 1 | tumor1 | 387.06 | 387.06 | 0.907 | 100.000% | No — tumor1 pixel QC done |
| TCGA-DD-A4NJ | 1 | tumor1 | 30.76 | 30.76 | 0.859 | 100.000% | No — tumor1 pixel QC done |
| TCGA-G3-A25T | 1 | tumor1 | 557.60 | 557.60 | 0.949 | 100.000% | No — tumor1 pixel QC done |
| TCGA-G3-A3CJ | 1 | tumor1 | 753.26 | 753.26 | 0.961 | 100.000% | No — tumor1 pixel QC done |
| TCGA-G3-A7M7 | 1 | tumor1 | 24.63 | 24.63 | 0.896 | 100.000% | No — tumor1 pixel QC done |
| TCGA-G3-AAV1 | 1 | tumor1 | 69.43 | 69.43 | 0.814 | 100.000% | No — tumor1 pixel QC done |
| TCGA-G3-AAV2 | 1 | tumor1 | 56.04 | 56.04 | 0.922 | 100.000% | No — tumor1 pixel QC done |
| TCGA-G3-AAV3 | 1 | tumor1 | 108.45 | 108.45 | 0.913 | 99.989% | No — tumor1 pixel QC done |
| TCGA-G3-AAV7 | 1 | tumor1 | 6.01 | 6.01 | 0.891 | 100.000% | No — tumor1 pixel QC done |

## Decision gates for next work

- **G3 image technical (HCC-12): PARTIAL.** PV source pixel+tumor1 masks 14/14, published mask–liver geometry 14/14, reviewer/manual tumor accuracy and temporal eligibility still pending. Repeat PV pixel overlay for A10Y tumor3.
- **G7 annotation stability (HCC-13): PARTIAL.** Two-reader mask Dice 14/14 computed. **Radiomics feature ICC and feature perturbation stability not computed**, and clinical mapping of tumor IDs unverified. Avoid treating Dice as an ICC threshold.
- **G4 chronology: PENDING.** TCIA dates are deidentified; avoid naive calendar joins.
- **G5 tumor RNA numerical QC: PENDING.** GDC file-associated Primary Tumor barcodes exist but no real expression values have been checked.
- **G6 paired eligible n: NOT ASSESSED.** 14 are source imaging and segmentation technical candidates, not final analysis patients.
- **G8 locked hypothesis family: PENDING.** Pathway scores + IBSI features require a separate frozen protocol before observing any association.
- **Highest allowable manuscript inference currently S0 (technical feasibility)**. Do not claim pathway association or clinical prognostic utility.

### Reproduction

- Scripts: `research/hcc/ci/mri_pv_pixel_overlay_audit.py`, `research/hcc/ci/mri_liver_tumor_rater_qc.py`, `research/hcc/ci/fast_zip_member_range.py`.
- Github Actions: run #62 14 PV PNGs, CSV & JSON; run #65 14 largest-lesion annotations, liver fraction, Dice & JSON. Retention 30 days; exact patient-level results archived in this Markdown.
- No protected medical data, raw RNA expression, or full MRI NIfTI files committed.
- Before publishing figures, note axes use NIfTI voxel orientation and physically scaled spacing; radiological left-right orientation should be validated by a qualified image reader.
