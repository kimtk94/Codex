# HCC MRI PV — 14-patient two-reader PyRadiomics absolute-agreement ICC and LOO evidence

**Verified at 2026-10-30 KST**. Public LiverHccSeg v1.1 TCGA-LIHC MR images, no RNA biological association.
- [Live 14-case 2-reader PyRadiomics extraction and bootstrap ICC run](https://github.com/kimtk94/Codex/actions/runs/41074562055): **PASS**, 14 patients × 2 masks = 28 feature profiles, 10 original-image features.
- [Independent patient leave-one-out ICC stability run](https://github.com/kimtk94/Codex/actions/runs/41075577502): **PASS**, all 14 exclusions per feature using the immutable numeric-feature artifact.
- Versioned machine evidence: [10-feature ICC+CI+LOO CSV](HCC_MRI_PV_RATER_ICC_14_FEATURE_STABILITY_20261030.csv).

## Scientific methods

- PyRadiomics **3.1.0**, Python **3.9** (native binary wheel), NIfTI image source `pv.nii.gz`. The same MRI volume is reused for both rater1 and rater2 HCC tumor masks, same lesion index (rater1-max-volume choice). For **TCGA-BC-A10Y**, index lesion **tumor3** rather than tumor1; index lesion was selected before any molecular correlation.
- Only imageType **Original**. Raw shape/first-order/GLCM features (no LoG/wavelets). `normalize=True`, `normalizeScale=100`, `binWidth=25`, `voxelArrayShift=0`, `resampledPixelSpacing=None` (native anisotropic spacing retained), `correctMask=False` (geometry mismatches fail rather than silently resample masks), `minimumROIDimensions=2`, `preCrop=True`.
- Reliability = **ICC(A,1), two-way random effects, single measurement, absolute agreement**, across distinct patients and exactly two raters. Point estimates plus **500 patient-bootstrap 95% percentile intervals**, seed 20261030. Supplementary leave-one-patient-out point ICC tested for each of 14 subjects.
- Exploratory *measurement-reliability* screen, defined independently of RNA: ICC(A,1) point ≥0.90, bootstrap 95% lower ≥0.75, and minimum leave-one-out ICC ≥0.75. These are conservative candidate filters **not statistical significance or proof of biomarker performance**. Original lower-tier classification ICC ≥0.75 alone is reported but not enough to pass the screen.
- Critical limitations: n=14, large between-patient tumor size spread may inflate absolute ICC; bootstrap intervals are exploratory; thick MRI slices (2.4–10.8 mm previous mask metadata) can distort 3D texture; PyRadiomics IBSI binning/resampling definitions differ in important cases (https://github.com/AIM-Harvard/pyradiomics/blob/master/docs/faq.rst); no phantom benchmark, inter-scanner transfer or multiple-feature clinical relevance demonstrated.

## Verified results

| Original feature | ICC(A,1) | 95% bootstrap interval | LOO ICC range | Reader stability screen |
|---|---:|---:|---:|---|
| First-order Mean | 0.99949 | 0.99842–0.99980 | 0.99923–0.99961 | PASS |
| First-order Median | 0.99910 | 0.99731–0.99977 | 0.99868–0.99958 | PASS |
| First-order Entropy | 0.98738 | 0.96014–0.99589 | 0.98488–0.99136 | PASS |
| First-order Interquartile Range | 0.98909 | 0.95752–0.99833 | 0.98551–0.99295 | PASS |
| GLCM Contrast | 0.96680 | 0.91154–0.99567 | 0.95476–0.99006 | PASS |
| GLCM Joint Entropy | 0.98489 | 0.96363–0.99661 | 0.98220–0.99058 | PASS |
| Shape Surface Area | 0.99526 | 0.98894–0.99809 | 0.99453–0.99638 | PASS |
| Shape Voxel Volume | 0.99628 | 0.99251–0.99890 | 0.99537–0.99775 | PASS |
| Shape Sphericity | 0.82174 | 0.34958–0.95241 | 0.68170–0.89041 | **EXCLUDE from primary reliability-screen features** |
| Shape Elongation | 0.72746 | 0.28927–0.91937 | 0.63995–0.81767 | **EXCLUDE from primary reliability-screen features** |

Eight of ten tested original-image features pass the reader-robustness screening. The weak **Sphericity** interval and **Elongation** point ICC are not acceptable for the initial primary biological hypothesis family. No modality-wide claim that every PyRadiomics feature is reproducible is supported.

## Hypothesis selection / what this does NOT establish

- Measurement stability is a **necessary** condition, never sufficient for meaningful biological correlation. `VoxelVolume` and `SurfaceArea` are strongly influenced by tumor size; use tumor volume as a predeclared adjustment/sensitivity variable, **not** a free independent biomarker discovery result.
- For a low-dimensional MRI–pathway exploratory pilot, candidate nonredundant first-order/texture features could be **Entropy**, **GLCM Contrast**, **InterquartileRange** (subject to additional MRI image-intensity/scanner/phase QC). `JointEntropy` is plausible but may overlap with Entropy; `Mean` and `Median` are likewise highly related. **No expression-vs-feature results were inspected for this selection.**
- No treatment timing or expert tumor anatomical/lesion validation yet. G3 remains PARTIAL, eligible n remains NOT ASSESSED.
- G7 segmentation mask and feature-reader stability is technically advanced; G8 pathway hypothesis family/gene-set version and expression score derivation remain PENDING. **Manuscript claim ceiling stays S0**.
- Independent multicenter MRI/CT harmonization and external patient replication not established. Dice is not the same as ICC, and ICC is not the same as pathway prediction performance.

## Follow-up gates

1. Read the current [HCC master verification framework](HCC_VERIFICATION_AND_PUBLICATION_FRAMEWORK.md) and [27-gate ledger](HCC_VERIFICATION_LEDGER.csv); persist latest run source commit and cohort table.
2. Obtain qualified ROI visual approval on 14 selected PV tumor masks, plus MRI-before-treatment/tissue time relationship using source-appropriate deidentification-aware records. Do not promote paired n prematurely.
3. Execute IBSI phantom reference QC and a predeclared physical resampling/voxel thickness sensitivity, with at least one separate rater feature ICC table; retain both native and resampled versions.
4. Fix exact pathway gene-set release, gene filters and a priori score method, then validate RNA score distributions, no inferred causality.
5. Lock primary MRI feature–pathway test family and family-wise BH-FDR before reading association results. Consider volume/covariate confounding and leave-one-out associations.
6. For strong publication claims, acquire an independent nonoverlapping paired-image/tumor-RNA cohort and external replication.

## Reproducible scripts / artifacts

- `research/hcc/ci/mri_pv_pyradiomics_rater_icc.py` — two-rater actual PyRadiomics, ICC + patient bootstrap.
- `research/hcc/ci/mri_icc_patient_leave_one_out.py` — ICC patient deletion and pre-outcome reliability screen.
- GitHub run #87: `hcc-mri-pv-feature-icc-fourteen-case-study` artifact: per-patient rater features, 10 feature ICC and provenance/config JSON.
- GitHub run #90: `hcc-mri-pv-feature-icc-fourteen-loo` artifact: 10 feature LOO ranges and immutable decisions.
- No raw MR voxel matrices or raw RNA expression vectors are committed or uploaded as artifact.
