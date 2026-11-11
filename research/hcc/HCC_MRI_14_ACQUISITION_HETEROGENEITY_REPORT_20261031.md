# HCC MRI — real-data native PV resolution and published acquisition metadata QC

**Evidence date:** 2026-10-31. Frozen technical n=14 (NOT clinical eligible n). [Live independent CI run #164](https://github.com/kimtk94/Codex/actions/runs/41160511643) succeeded with **six operational Jobs**: five independently executed clinical, molecular purity, MRI/RNA source, original reader study, and native scanner/acquisition metadata audits; final combined patient gate passed. No biological MRI–RNA correlations calculated.

## Original source datasets and scope

1. **Actual native PV NIfTI voxel geometry**, 14 patients × two original tumor segmentation raters, derived from the PyRadiomics v3.1.0 original image feature extraction [live original run #87](https://github.com/kimtk94/Codex/actions/runs/41074562055). Rater1 and rater2 image spacings match within every patient. Original cases selected without RNA and fixed in [index lesion registry](HCC_MRI_14_PREOUTCOME_INDEX_LESION_SELECTION_20261030.csv). Preserved new [native-spacing CSV](HCC_MRI_14_PV_NATIVE_SPACING_QC_20261031.csv).
2. **Original study's acquisition details**, LiverHccSeg v1.1 [official Zenodo record 8179129](https://zenodo.org/records/8179129) `LiverHccSeg_MetaData.xlsx`, checksum MD5 `37806f09955aa198ab8e50e0e2929da7`, file length 12,911 bytes. Source patient/row checks **14/14**. Published [14-case study-level field-strength and contrast metadata CSV](HCC_MRI_14_PUBLISHED_FIELDSTRENGTH_CONTRAST_20261031.csv); complete derived CI artifact `hcc-batch-acquisition` (30-day retention), no original DICOM `StudyDate` or shifted dates exported.
3. **Published source reader annotation** in independent `segm_metrics.xlsx` from same Zenodo: MD5 `e3bf1618f0c0fc65b2c9d18a90a36717`, HCC segmentation metrics matched all 14. See [source reader evidence report](HCC_FIVE_PARALLEL_EVIDENCE_AND_DRIFT_QC_20261031.md).

## Actual native PV NIfTI spatial resolution

| Metric | Observed |
|---|---|
| Rater profiles with matching PV image voxel size | **28/28 (14 cases × 2 raters)** |
| PV through-plane voxel spacing (slice separation) | **2.4–10.8 mm** |
| Median PV through-plane spacing | **2.625 mm** |
| Through-plane / average in-plane spacing ratio | **1.77784–14.55133** |
| Patient exceeding prespecified QC threshold (z ≥5 mm **or** z/in-plane ratio ≥4) | **TCGA-BC-A10Y: 10.8 mm, ratio 14.55** |
| Other 13 patients' through-plane spacing | **2.4–3.5 mm** |
| Original patient-level PV phase | 14/14 technical profiles PV |

The 10.8 mm case is **A10Y with index lesion tumor3**, not a segmentation error or clinically adjudicated exclusion. Shape `SurfaceArea`, `Sphericity`, `Elongation` and GLCM texture may be strongly affected by anisotropic voxels, masks, discretization and resampling choices; even `Entropy`/IQR must be checked for potential slice, contrast and intensity normalization differences. Reader-to-reader ICC alone cannot validate across acquisitions. Thresholds here are *technical review flags*, not outcome-derived inclusion/exclusion thresholds.

## Published 14-patient field strength and contrast labels

**Field strength:** all **14** published subject-level metadata records show **1.5T**. One patient (**A10Y**) appears in three workbook rows; the other 13 have one row each. `StudyDate` is intentionally never transferred into derived files.

**Contrast label in published metadata** (not necessarily exact selected PV series):
- `Extracellular`: **7** patient IDs, corresponding to workbook labels Omniscan/Magnevist/Gadovist.
- `Hepatobiliary-specific`: **4** patient IDs, corresponding to workbook Multihance/MultiHance labels.
- `not avaliable` (literal source spelling): **3** patient IDs.

The published spreadsheet has **Magnetic Field Strength** and `Contrast Agent Manufacturer`, but the latter describes **contrast product manufacturer, not scanner vendor**. **Scanner manufacturer/model, coil, exact T1 sequence parameters and patient-level exact selected PV series linked to the metadata are NOT available in the verified workbook.** Do not infer that all exact PV series had the same scanner/vendor simply because subject-level field strength is uniformly 1.5T.

## Radiomics implications and predeclared method sensitivity

- **Present**: original MRI PV native voxel sizes and ten PyRadiomics features × two readers, reader agreement as ICC(A,1) on original spacing, 14 LOO patient checks.
- **Not yet validated**: isotropic 2 or 3 mm resampling sensitivity, alternative intensity normalization/binWidth, IBSI phantom/reference image concordance, DICOM manufacturer/sequence/field-strength *for the selected PV series*, harmonization across agents.
- In any methodological followup, retain original extraction and evaluate an **identical-patient, identical-index-lesion** re-extraction with a prechosen standard voxel size, same rater masks transformed by nearest-neighbor and images by appropriate interpolator. Record mask voxel count and volume changes, reference extraction settings, and numeric feature differences. Do not call image interpolation recovery of spatial detail lost by 10.8 mm sections.
- **Do not run ComBat** on 14 cases with unknown precise scanner/batch variables, sparse agent groups and one extreme thick-slice image. Any scanner-linked/contrast-type feature comparisons would be exploratory QC with small n, no inferential claims.
- **Do not remove A10Y simply to improve an imaging–RNA correlation.** Predefine a sensitivity with/without acquisition-flagged cases and report both if a clinically eligible sample is later established. The original 12 association family and eligibility n≥10 requirement remain unchanged, and no association is authorized until expert ROI/clinical source review.

## Six-job CI diagram and fail-closed status

`clinical`, `purity`, `frozen source`, `official expert publication`, and `native-acquisition` jobs execute independently (small published workbook downloads or frozen CSV source). `readiness` has `needs` on all five and downloads all five job artifacts, checks patient set, same-source selected tumor number, native PV geometry positivity and lack of claimed series-level scanner or clinical eligibility, then emits a **single 14-patient joined CSV + GO/HOLD/STOP JSON**.

- [GitHub Actions run #164, all 6 jobs + offline regression PASS](https://github.com/kimtk94/Codex/actions/runs/41160511643).
- Code: [acquisition metadata and native voxel QC](ci/mri_native_acquisition_heterogeneity_qc.py), [multi-evidence join](ci/mri_parallel_batch_gate.py), [unauthorized case-level drift check](ci/mri_parallel_snapshot_diff.py).
- Five input artifacts and `hcc-batch-joint-readiness` output preserve the patient-level evidence, plus GitHub Step Summary. No raw NIfTI archives downloaded in this step.
- GDC clinical pretherapy and tumor tissue lesion bridge still **NOT VERIFIED**. HCC-13/18 remain PARTIAL due to untested spatial resampling/scanner and reference standard; HCC-12/14 PARTIAL (source MRI expert annotation exists but no exact source lesion/therapy adjudication); HCC-17/20 PENDING. Maximum manuscript claim ceiling **S0**.
