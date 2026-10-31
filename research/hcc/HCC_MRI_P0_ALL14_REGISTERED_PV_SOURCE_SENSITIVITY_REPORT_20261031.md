# HCC P0 — 14-patient native PV versus official registered PV radiomics source-space sensitivity

**Date:** 2026-10-31 KST. **Scientific status: SOURCE-SPACE METHODS PASS, MRI–RNA BIOLOGY HOLD.**

## Verified real source execution

- [Complete 9-job GitHub Actions #41191599451](https://github.com/kimtk94/Codex/actions/runs/41191599451): one frozen 14-case/negative-fixture validation, **seven successful** deterministic two-case source-shards, and one successful aggregate job.
- Official [LiverHccSeg v1.1, Zenodo 8179129](https://zenodo.org/records/8179129). Same fixed 14 TCGA case IDs and index tumor choice as before (A10Y tumor3).
- Source arms: **historical raw** `pv.nii.gz` versus **official arterial-registered portal venous** `art_pv.nii.gz` after nibabel exact voxel-axis reorientation into the mask's reference. No new B-spline interpolation, no automatic patient exclusion or imaging-response correlation.
- Exactly **14 distinct patients, 2 expert reader masks, 2 source arms = 56 PyRadiomics rows**. Same ten original features and locked settings (`normalize=True`, `normalizeScale=100`, `binWidth=25`, `correctMask=False`, `resampledPixelSpacing=None`), with declared 0.5-mm physical image/ROI geometry tolerance for source header rounding. PyRadiomics distribution **3.1.0** with Python **3.9** Linux binary wheel. The ZIP archive member's CRC and per-image/mask SHA-256 are checked and retained per feature row.
- 14 source-space orientation prior: [separate source-header audit #41188630515](https://github.com/kimtk94/Codex/actions/runs/41188630515); all registered PV source headers match the mask after axis-only reorientation to 0.5 mm, original raw PV matches directly. Source affine match does **not** prove tissue alignment.
- Raw patient feature values were *not* overwritten; this is an outcome-blind imaging methods sensitivity analysis (no RNA used).

## Verified 10-feature source stability (patient-wise average of two readers)

The source selection statistic for the **14 independent patient units** is per-patient mean of the two reader measurements. Relative change = `(registered - raw)/abs(raw) × 100`. `rho` = Spearman across the 14 patient-mean values, not a test of an RNA association.

| Original feature | Median absolute source change | Source rank rho | Patients ≥10% change | Interpretation |
|---|---:|---:|---:|---|
| First-order Entropy, **locked** | **3.309%** | 0.8945 | 1/14 | Nonzero source effect; preserve locked endpoint |
| First-order Interquartile Range, **locked** | **2.944%** | 0.9429 | 4/14 | Rank fairly preserved but individual magnitude may shift |
| GLCM Contrast, **locked** | **22.080%** | 0.8945 | **11/14** | **High source-phase sensitivity**; 9/14 are ≥20% |
| GLCM Joint Entropy | 4.608% | 0.8945 | 2/14 | Secondary MRI diagnostic |
| First-order Mean | 1.774% | 0.9648 | 3/14 | Median shift small, individual outliers |
| First-order Median | 1.224% | 0.9648 | 2/14 | Median shift small, individual outliers |
| Shape VoxelVolume / SurfaceArea / Sphericity / Elongation | **0% each** | **1.000 each** | 0/14 each | Expected negative control: unchanged masks |

GLCM Contrast median **signed** source change = **−22.071%**, maximum absolute change **43.111%**. Direction is not universal: TCGA-DD-A4NJ increases **+21.84%**. TCGA-G3-AAV7 has 0% changes in the locked three features, **not evidence of a duplicated source** without a pixel-level source check. The source images have distinct SHA-256, so voxel-level equality within an ROI remains a separate question.

## Two-reader reliability does not imply source invariance

ICC = two-reader absolute-agreement `ICC(A,1)`, with 300 patient bootstrap resamples and 95% percentile interval; same patient is the independent resampling unit. Do not treat the 28 reader measurements as 28 patients.

| Locked feature | Historical raw PV ICC (95% bootstrap interval) | Official registered PV ICC (95% bootstrap interval) |
|---|---|---|
| Entropy | 0.98738 (0.96533–0.99673) | **0.98903 (0.97781–0.99667)** |
| Interquartile Range | 0.98909 (0.96681–0.99783) | **0.99325 (0.97782–0.99817)** |
| GLCM Contrast | 0.96680 (0.90313–0.99640) | **0.95161 (0.89145–0.99783)** |

All **20/20 ICC estimates were numerically estimable**. Registered GLCM Contrast ICC remains high even though changing source images shifts the magnitude for most patients; the two properties assess different measurement stability dimensions.

Original and registered PV values are not exchangeable. Source differences may reflect the original source's non-rigid interpolation and anatomical motion correction and/or other source processing; this experiment **does not isolate which component caused a change**.

## Frozen evidence and reproducibility

- [Source-rank/ICC pipeline](ci/mri_p0_registered_pv_all14_aggregate.py)
- [Deterministic 7-shard raw/registered PV extractor](ci/mri_p0_registered_pv_all14_sharded.py)
- [Immutable 14-patient signed changes](HCC_MRI14_PV_SOURCE_14_CASE_PRIMARY_FEATURE_CHANGE_20261031.csv), rounded to 2 decimals.
- [Immutable ten-feature sensitivity metrics](HCC_MRI14_PV_SOURCE_10_FEATURE_SENSITIVITY_20261031.csv), frozen to 5/6 decimals.
- [Immutable twenty two-reader ICC reference values](HCC_MRI14_PV_SOURCE_TWO_READER_ICC_20_20261031.csv), frozen to 5 decimals.
- GitHub Actions artifact **`hcc-mri14-native-vs-registered-pv-ten-feature-comparison-and-icc`**, artifact ID **13039386584**, run **41191599451**, retaining full exact 56×31 row CSV with per-source SHA plus statistics and JSON for 30 days. Downloaded original artifact file SHA256:
  - `hcc_mri14_raw_vs_registered_pv_all_features.csv`: `89721948d9be9942c25b1be95388c8121eb2b89298443c7e0edf30fd563d0184`
  - `hcc_mri14_pv_source_feature_sensitivity.csv`: `504615f735d0acb1d301d7de0be6a779c069e3efdddb08c119bebe632cfb00a0`
  - `hcc_mri14_pv_source_two_reader_icc_a1.csv`: `86c205f0ef719012cb05104a3082209f6c1b852c453dcfa2e405414d44ddfcf0`
  - `hcc_mri14_registered_source_reproducibility_summary.json`: `a5ab10797db11b592a957f5464b50b2bb767956f316c3e557f0c4da78f904a96`
- Reference original raw 14-person ICC and LOO: [frozen reader validation](HCC_MRI_PV_PYRADIOMICS_ICC_14_VALIDATION_20261030.md); reference source is original PV, not source-authorized registered PV.

## Study-level decision and explicit claim ceiling

**P0 source-space gate:** technical **PASS** for exact axis correction/CRC/feature extraction but remains **PARTIAL for anatomical/lesion approval**. A qualified abdominal radiologist still needs to inspect actual tumor ROI vs registered PV; the source's B-spline registration is not independently validated by affine equality. The TCGA MRI and GDC RNA relationship still lacks verified pretreatment chronology and matched sequenced tumor index-lesion origin.

**Primary MRI image source for a future biological test** shall be official `art_pv` after axis-only correction (if clinically validated), **not raw `pv`**. Historical raw-PV values are retained as prespecified source-phase sensitivity context. This is a provenance/source-correction amendment **before any MRI–RNA association outcomes**, not a choice based on molecular correlations. Three MRI features × four predefined Hallmark scores remain **exactly 12 pre-locked tests**. No source-dependent p-value selection and no narrowing/widening after exposure to association statistics. See [locked source-correction SAP addendum](HCC_MRI_RNA_SOURCE_PHASE_SAP_ADDENDUM_20261031.md).

**Scientific statuses:** HCC-12/13/14 PARTIAL; HCC-17/20 PENDING; eligible paired n **NOT ASSESSED**, MRI–RNA tests **0/12 executed**, manuscript claim ceiling **S0**. A 14-person image methods study remains limited by sample size, thick-slice heterogeneity and need for independent validation.

## Next non-outcome-biased tasks

1. Screen **TCGA-G3-AAV7** for exact original-versus-registered PV voxel identity in the selected mask and liver reference (signed-axis corrected, no transcriptome data); file hash difference alone cannot establish true ROI changes.
2. Generate patient-wise source sensitivity and reader ICC panels, with **absolute** registered-vs-original change and rank rho, not a misleading significance claim.
3. Validate mask-to-tumor anatomy on `art` and registered `art_pv` via qualified review; verify MRI pretreatment and matched index-lesion RNA before deciding eligible n. Do not launch the 12 tests before those gates pass.
