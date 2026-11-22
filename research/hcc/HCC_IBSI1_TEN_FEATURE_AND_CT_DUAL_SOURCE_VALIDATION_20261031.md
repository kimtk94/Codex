# HCC MRI technical validation — IBSI-1 ten features and official IBSI-1/2 CT phantom sources

**2026-10-31 KST · verified GitHub Actions run [#214](https://github.com/kimtk94/Codex/actions/runs/41179519399) · PR #228 · no MRI–RNA association tests.**

## Parallel GitHub Actions outcome

- **IBSI-1 official original digital phantom**: PyRadiomics **v3.1.0** calculated all ten frozen HCC MRI radiomics features, **10/10 reference comparisons PASS, 0 REVIEW** under the clearly stated numerical tolerances.
- **IBSI-1 vs IBSI-2 official CT phantom**: real NIfTI images and masks in the two directories have the **same SHA-256**, identical native geometry, and valid native CT GTV mask; **source provenance PASS**.
- **Independent protocol guard**: official reference registry and CT phases differentiated, HCC sample/claims locked, **PASS**.
- **Final integration**: source hash + 10-feature reference match + CT original equality + no invalid inferential upgrade, status **PASS_SOURCE_ALL_10_IBSI_PHANTOM_MATCHED**.
- Existing HCC MRI/RNA technical/clinical provenance **six-job source gate PASS**, HCC fixed-source regression suite PASS in the same run. Some unrelated heavy image-extraction jobs remain intentionally skipped unless explicitly re-run.

## Exact ten-feature official digital phantom measurements

Original source: [IBSI-1 3D digital phantom](https://github.com/theibsi/data_sets/tree/master/ibsi_1_digital_phantom/nifti), source git commit `6da96021bc91faf4c0cb7fd7fa56a4225d2064a8`, image SHA-256 `83773ac2a288aa93cf819a98eaf301c18d35d5876182ec9c18733184e2b7a83a`, mask SHA-256 `3032d340944b577b83bc559ea7ae9a6034b84633a840eff39570ec17aa1d6281`.

Configuration: 5×4×4 voxel image, **74 voxel ROI**, 2mm isotropic, `binWidth=1`, **no intensity normalization**, **no interpolation**, symmetric GLCM, Chebyshev distance one voxel, no GLCM weighting. GLCM reference uses **3D directional average**, not 3D directional merged. This is not the same intensity-normalized, binWidth25, n=14 original PV MRI clinical extraction protocol.

| Original PyRadiomics feature | IBSI code | Official reference | Observed v3.1.0 | Result |
|---|---|---:|---:|---|
| shape VoxelVolume | YEKZ | 592 | 592 | PASS |
| shape SurfaceArea | C0JK | 388 | 388.070630 | PASS |
| shape Sphericity | QCFX | 0.843 | 0.842940 | PASS |
| shape Elongation | Q3CK | 0.816 | 0.816321 | PASS |
| firstorder Mean | Q4LE | 2.15 | 2.148649 | PASS |
| firstorder Median | Y12H | 1 | 1 | PASS |
| firstorder Entropy | TLU2 | 1.27 | 1.265612 | PASS |
| firstorder InterquartileRange | SALO | 3 | 3 | PASS |
| GLCM Contrast (3D:avg) | ACUI | 5.32 | 5.324480 | PASS |
| GLCM JointEntropy (3D:avg) | TU9B | 2.40 | 2.399711 | PASS |

References: official [IBSI Image Features](https://ibsi.readthedocs.io/en/master/03_Image_features.html). **Important: IBSI lists official numerical tolerances for morphological VoxelVolume 4, SurfaceArea 3, Sphericity 0.005, Elongation 0.005.** For digital-phantom intensity and GLCM references displayed without official tolerance, this audit explicitly sets a stricter diagnostic comparator based on published digits (0.005 or 0.015 absolute); **do not label those as published IBSI acceptance tolerances**. The complete comparison includes code, measurement, absolute error, threshold provenance, observed status in [CSV](HCC_IBSI1_TEN_FEATURE_PHANTOM_RESULTS_20261031.csv).

The official phantom is intentionally small and may not distinguish some percentile or mesh implementation details. Hence **10/10 phantom agreement does NOT certify complete IBSI compliance, normalized MRI robustness, spatial resampling compatibility or actual disease phenotype associations**. Existing 14×2 native-vs-3mm GLCM sensitivity (Contrast median ~77% absolute relative change; binWidth25→12.5 ~253%) remains a genuine limitation not erased by the official digital phantom benchmark.

## Official CT source verification — what passed and what did not

The original official `theibsi/data_sets` source commit was also pinned for `ibsi_1_ct_radiomics_phantom` and `ibsi_2_ct_radiomics_phantom`, each with NIfTI image and segmentation mask. The official README states IBSI-2 CT phantom is **identical to IBSI-1 Phase II CT phantom**.

| Item | Source QC result |
|---|---|
| Original NIfTI image dims | **204 × 201 × 60 voxels** |
| Original voxel spacing | **~0.977 × 0.977 × 3.0 mm** |
| Original GTV ROI | **125,256 voxels** |
| CT NIfTI image SHA-256, both versions | `909129fdf99d5f5fd17bc568b1834d31edce8663ea6746c6020720bfc1d7bbcb` |
| CT NIfTI mask SHA-256, both versions | `0e9243e473b1255c60e6460df465d0b07b65436d6e0c691fe3d17bca0594ae78` |
| Source image and mask shape/affine compatibility | **PASS** |
| CT license | **CC BY-NC 3.0** — raw CT image/mask not redistributed in our artifacts |
| IBSI-1 Phase II CT configs A–E preprocessed and feature values checked | **NOT EXECUTED** |
| IBSI-2 Phase II CT filtered-feature response benchmark | **NOT EXECUTED** |

**Nomenclature distinction:** IBSI-1 Phase II specifies five original CT preprocessing/feature configurations A–E (2D/3D, HU resegmentation, interpolators, bin size or fixed bin count), whereas IBSI-2 Phase II includes filtered-feature response maps and corresponding tests. **Identical CT input files do not imply equivalent or completed processing pipelines.** CT input verification is only an upstream prerequisite, not a scientific success on the CT benchmark. Source data: [IBSI reference datasets](https://theibsi.github.io/datasets/), [IBSI-1 preprocessing A–E](https://ibsi.readthedocs.io/en/latest/05_Reference_data_sets.html) and [IBSI-2](https://theibsi.github.io/ibsi2/).

## Reproduction and CI files

- [Ten-feature live PyRadiomics original phantom code](ci/mri_ibsi1_all10_feature_reference_audit.py).
- [IBSI-1/2 CT native source/header/license preflight code](ci/mri_ibsi_ct_dual_phase_source_preflight.py).
- [Cross-source clinical and method gate](ci/mri_ibsi10_ct_expanded_gate.py).
- [Permanent ten-feature quantitative table](HCC_IBSI1_TEN_FEATURE_PHANTOM_RESULTS_20261031.csv), [permanent CT SHA/geometry/license manifest](HCC_IBSI_CT_OFFICIAL_SOURCE_MANIFEST_20261031.json).
- [Deterministic no-network regression tests](ci/mri_ibsi1_ten_feature_ct_frozen_result_qc.py) for all ten official source values, verified CT source hashes and forbidden claims.
- [Actual Actions run #214](https://github.com/kimtk94/Codex/actions/runs/41179519399) preserves full 10-feature per-feature original measurement CSV, original source parameters, original CT two-instance audit JSON and final joined GO/REVIEW/HOLD report as downloadable CI artifacts (retention 30 days).

The heavy source downloads should not repeat on every ordinary PR once recorded; the frozen-result integrity regression should run on each PR. Explicit manual rerun is appropriate when package/dependency or source version changes, with reviewed source/threshold changes instead of silent baseline updates.

## Current HCC decisions

- **HCC-13 and HCC-18 PARTIAL**: technical feature source/reference values and reader ICC empirically verified; full IBSI CT configurations, exact PV series scanner metadata, between-scanner reproducibility, and clinical imaging/lesion validation still pending.
- **HCC-14 clinical treatment/scan chronology PARTIAL/HOLD**, **HCC-17 qualified paired cohort n PENDING**, **HCC-20 planned 12 MRI–RNA associations PENDING NOT RUN**. No automatic exclusions, 14 technical candidates unchanged.
- Claim ceiling remains **S0**. No MRIs were assumed to precede treatment based on DICOM shifted StudyDate or GDC diagnosis-relative offsets. Digital phantom and CT input verification are MRI method-validation progress, not biological evidence for hepatocellular carcinoma pathways.

## Recommended next distinct experiments

1. IBSI-1 CT **configuration A** (native 2D, resegmentation −500 to 400HU, FBS25HU) with verified source mask and explicitly matching IBSI reference, before B–E.
2. IBSI-1 CT **configurations B–E** only after specifying correct ROI partial-volume threshold, interpolation grid alignment, rounding, shape dimensionality and reference tolerances; distinguish unsupported PyRadiomics options from actual algorithms.
3. IBSI-2 **Phase II** filtered-feature images/response maps independently; do not treat a simple unfiltered CT pipeline as IBSI-2 filter compliance.
4. Most consequential biological gate remains **source-authoritative MRI-before-treatment and exact tumor-to-RNA tissue lesion matching**. Without it, original 12 associations remain disallowed.
