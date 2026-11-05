# HCC P0 — Official registered PV, 14-patient binWidth × voxel-spacing factorial

**Updated 2026-11-01 KST.** The clinical/radiogenomics claim ceiling remains **S0**. No gene-expression or 12 prelocked MRI–RNA hypothesis was accessed or tested.

## Official source and verified completion

[GitHub Actions #41208617950](https://github.com/kimtk94/Codex/actions/runs/41208617950): **9/9 SUCCESS**. The actual source is [LiverHccSeg v1.1](https://zenodo.org/records/8179129) `art_pv.nii.gz` (official registered portal-venous MRI), exact signed-axis correction into the frozen source tumor mask physical space. All fourteen predetermined patients, two expert masks each; case A10Y retains `tumor3`. No research participant was added/removed.

- **14 independent patients, 2 reader masks, 2 voxel-grid conditions** (`native`, `3mm` isotropic), **3 binWidth conditions** (`12.5`, `25`, `50`) = **168** case-reader-grid-binWidth extractions, each containing four features: GLCM Contrast, GLCM JointEntropy, first-order Entropy, and first-order IQR.
- **24** feature-condition results; **112** paired case-reader-feature values (14×2×4) in `native / binWidth25` reproduced from frozen original registered PV 56-row artifact [#41191599451](https://github.com/kimtk94/Codex/actions/runs/41191599451). The original source and expert-mask SHA-256 values were checked across all conditions.
- PyRadiomics distribution 3.1.0, `binWidth` as listed, `normalize=True`, `normalizeScale=100`, `symmetricalGLCM=True`, neighbor distances `[1]`; 3mm image interpolation `sitkBSpline`, mask nearest-neighbor. Native grid is not newly resampled. No patient-level tissue eligibility or expert anatomy review passed.
- Original 168-row artifact `hcc-mri14-official-registered-pv-2x3-factorial-168-rows-and-24-condition-metrics` (ID **13046135524**, 90-day retention). Members are pinned SHA-256:
  - `hcc_registered_pv_14x2_2x3_glcm_extraction_rows.csv`: `66286993a268a177ed663d8d328a5f9b5048d3630e897132b6c503bb44a94911`
  - `hcc_registered_pv_24_feature_condition_metrics.csv`: `ac65f81c2be42021a3a77f7752145f329b2e9fd694a7a7850d58e8c3a0387784`
  - `hcc_registered_pv_112_patient_reader_feature_profiles.csv`: `44d6a22d4e80f9135a3f0cd267d24eafc639b4aa5d2b1dbde5913533a356d98f`
  - `hcc_registered_pv_2x3_factorial_summary.json`: `638d4f91c530da2e30ffdadcc56f28bd8b459f7a3528fe55077ac1cc7e755a82`.

## Primary six-condition GLCM Contrast comparisons

All changes below are **patient-level mean of the two reader measurements per condition** versus **registered PV at native spacing, binWidth25**, with `(condition-base)/abs(base)×100` computed per patient, then median absolute percentage change across the fourteen patients. A lower binWidth naturally increases GLCM Contrast because texture gray-level quantization changes; large percentages do not by themselves represent better signal quality.

| Registered-PV condition | Median absolute difference % | 95% percentile CI (n=14 patient bootstrap, B=4,000) | Spearman rank ρ | ICC(A,1) | Patients with ≥10% abs change |
|---|---:|---|---:|---:|---:|
| Native / 12.5 | 244.7085 | **226.23–262.15** | **1.000** | 0.95171 | 14/14 |
| Native / **25 (frozen reference)** | 0.0000 | [0, 0] | 1.000 | **0.95161** | 0/14 |
| Native / 50 | 64.5187 | **59.01–66.31** | 0.97363 | 0.95091 | 14/14 |
| 3mm / 12.5 | 600.0997 | **531.73–666.24** | 0.85055 | 0.97061 | 14/14 |
| 3mm / **25** | **86.5938** | **76.40–97.88** | **0.85055** | 0.96878 | **13/14** |
| 3mm / 50 | 40.4293 | **32.14–44.87** | 0.79780 | 0.96729 | 13/14 |

The CI above comes from a **separate reconstruction of all 24 feature-conditions using 4,000 patient-cluster resamples**, seed 20261101, and does not provide a clinical or multi-site population guarantee. The original 168-row source and existing 24 summary point estimates were numerically crosschecked. Frozen output [all 24 reconstructed rows](HCC_MRI14_REGPV_FACTORIAL_24_CONDITION_PATIENT_BOOTSTRAP_FROZEN_20261101.csv), [code](ci/mri_p0_registered_pv_factorial_patient_bootstrap.py), [CI](https://github.com/kimtk94/Codex/actions/workflows/hcc-mri14-registered-pv-factorial-bootstrap.yml).

The largest 3mm/binWidth25 registered-PV GLCM Contrast patient effect is **TCGA-DD-A4NJ +251.4%**; the smallest is **TCGA-BC-A10Y −0.33%**. Thirteen of fourteen exceed absolute 10%, **but the response is not universal**, and cases remain in the analysis rather than selectively excluded. Native/bw12.5 changed the values for all fourteen but retained the full patient ranking ρ=1.0. The 3mm/bw25 comparison changed rank ρ to 0.851; source-space artifacts can therefore affect cross-patient relative comparisons even with high ICC.

### Four-feature contrast to avoid overclaiming

- GLCM JointEntropy, native12.5: median absolute difference **40.83%**; native50 **35.27%**; 3mm/bw25 **7.09%**.
- First-order Entropy, native12.5: **35.72%**; native50 **33.60%**; 3mm/bw25 only **0.30%**.
- First-order IQR: **0%** for all three native-grid bin widths (continuous percentile statistic is not changed by PyRadiomics binning); **0.621%** for 3mm at any width.
- For GLCM Contrast, native12.5 versus native25 changes the quantization scheme, while 3mm/bw25 versus native25 changes the voxel grid. The 3mm/12.5 effect combines both and is **not an additive sum or separable causal interaction**.
- ICCs measure *reader agreement within a condition*, not source or parameter invariance. Higher 3mm ICC does not prove more biologically correct texture or predictive utility.

## Scientific GO/HOLD boundaries

**Track A (image methods):** Technical **GO for source-specific measurement sensitivity** based on actual matched cases and two expert ROI masks. The 14-case convenience cohort is small, scanner-acquisition heterogeneity and manual anatomical registration review remain unresolved. No external radiomics reproducibility cohort has been evaluated in this work. For publication, report patient counts, technical parameters, negative controls, registration source lineage, clinical limitations, and an independent source validation before broadly generalizing.

**Track B (MRI–RNA):** **HOLD**. `HCC-12/13/14 PARTIAL`, `HCC-17/20 PENDING`, qualified paired patient n **NOT_ASSESSED**, original 12 tests **NOT_EXECUTED**. No feature/setting may be selected by RNA p-value. The original three MRI features, four Hallmark targets and multiple-testing plan remain frozen. The image-methods results provide **no evidence of a therapeutic, prognostic or molecular association**.

Next methodological question: whether scanner vendor field strength, image voxel anisotropy, contrast agent and per-case resolution explain the heterogeneous 3mm response. This requires original series metadata and a carefully fixed descriptive model, not biological hypothesis fishing. Reassess cohort/external validation before a manuscript claims generality.
