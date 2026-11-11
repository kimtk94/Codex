# HCC Stage 32 — independent external 59-subject ROI volume and native MRI spacing sensitivity

**Evidence recorded:** 2026-11-01 KST. Source cohort: independent OpenSwissHCC v2 original venous HCC MRI, original expert-selected index lesion mask for each of 59 subjects.

## Reproducibility

- **Original NIfTI+source mask extraction:** [Actions #41221356861](https://github.com/kimtk94/Codex/actions/runs/41221356861), 16/16 SUCCESS, 59/59 subjects, 354 extraction rows, 0 source/geometry HOLD.
- **Original source integrity:** [Actions #41223161712](https://github.com/kimtk94/Codex/actions/runs/41223161712), SUCCESS, original seven member SHA-256 plus 59-patient and 24-condition frozen CSV crosschecks.
- **Stage 32 ROI/spacing sensitivity:** [Actions #41224431479](https://github.com/kimtk94/Codex/actions/runs/41224431479), SUCCESS; artifact **13051865378**, `hcc-stage32-external59-roi-spacing-bootstrap-4k-results`, SHA256 ZIP digest `f0d9254bc4ba50a450f4f95eae0f9221adb036655626ae76594d504a5c08f1c5`, 90-day retention.
- **Recompute from permanently saved patient values:** `python3 research/hcc/ci/mri_external59_roi_spacing_sensitivity.py --out-dir artifacts/hcc_stage32_external59`.
- **Source:** `HCC_EXTERNAL_OPENSWISSHCC_V2_59_INDEX_PATIENT_GLCM_NATIVE3MM_FROZEN_20261101.csv`. No original source NIfTI re-download or features recomputation in Stage 32.

## Scope and calculations

Patient-specific outcome: absolute percentage change in **GLCM Contrast** between original venous **native spacing/binWidth25** and **3mm isotropic/binWidth25**, holding source image and tumor index lesion fixed.

- 59 independent patient observations; do **not** count 354 feature-condition extraction rows as independent.
- Original source physical volume (mL) = original expert mask voxel count × original x/y/z spacing in mm / 1000.
- In-plane pixel area = original x spacing × original y spacing, mm².
- Anisotropy proxy = original z spacing / geometric mean(original x and y spacing).
- Two-sided 95% intervals computed with 4,000 patient-with-replacement bootstrap samples (seed 20261101, deterministic variable offsets), percentile method. Leave-one-patient-out (LOO) minimum/maximum rho as influence check.
- **Post-hoc exploratory, not prespecified hypothesis testing**, no p-values, no cutoff optimization, no cross-cohort causal comparisons.

## Actual independently reproducible results (Stage 32 CI)

| Original-source variable | Spearman rho with absolute GLCM change | 95% patient-bootstrap percentile CI | LOO rho range |
|---|---:|---:|---:|
| log10 ROI physical volume, mL | +0.094272 | −0.162150 to +0.335599 | +0.057061 to +0.138515 |
| Original mask voxel count | +0.175921 | −0.093089 to +0.403625 | +0.139746 to +0.220031 |
| Native in-plane pixel area, mm² | −0.352666 | −0.561773 to −0.103817 | −0.416426 to −0.316168 |
| Native z/in-plane anisotropy | +0.334448 | +0.088178 to +0.546285 | +0.297419 to +0.396506 |

All four associations used 4,000 finite bootstrap replicates. The main external 59-person median absolute native→3mm GLCM Contrast shift remains **64.635863%** (original primary bootstrap 95% CI 56.753732–74.435888%). These are separate estimands; do not substitute the Stage 32 correlation CIs for that primary median-shift CI.

Physical ROI volume ordered quartiles (source volume rank split, not tuned on feature shift):

| Quartile | Independent n | Original volume range, mL | Median absolute change |
|---|---:|---:|---:|
| Q1 | 14 | 0.575–1.646 | 57.81% |
| Q2 | 15 | 1.756–5.766 | 64.64% |
| Q3 | 15 | 6.752–14.451 | 65.78% |
| Q4 | 15 | 16.372–119.773 | 73.13% |

## Interpretation and next scientific gates

The original in-plane resolution and anisotropy proxies show stronger rank associations with GLCM sensitivity than physical ROI volume in this *specific original-source cohort*. Because source sampling/sequence/interpolation/binning and segmentation are not experimentally randomized or independently varied, and native acquisition covariates are interrelated, **this is not evidence of a causal resolution effect** or independent significance of either proxy. Bootstrap confidence intervals are descriptive exploratory uncertainty intervals, not corrected for selecting among covariates after seeing results.

**Gate decisions:**
- Technical descriptive external MRI preprocessing-sensitivity: **GO**.
- Independent abdominal radiologist expert review of tumor anatomy, registration and original acquisition details: **HOLD**.
- MRI–RNA same-patient, same-lesion pretreatment scan/tissue pairing: **HOLD**.
- Predeclared Hallmark MRI–RNA association panel: **0/12 tested; STOP** until clinical source-pairing gate passes.
- Diagnostic, treatment, prognosis, biology and clinical utility claims: **S0 (not established)**.

Recommended Stage 33: check image-space contour validity through independent blinded abdominal expert review, and quantify agreement only where paired second-reader masks exist (selected external index lesion n=3; never claim ICC generalizability to n=59). Preserve original 59/59 denominator and all technical HOLD logs.
