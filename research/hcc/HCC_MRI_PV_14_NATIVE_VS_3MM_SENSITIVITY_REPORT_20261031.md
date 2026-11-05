# HCC MRI PV: 14 × 2 reader original vs 3mm isotropic PyRadiomics sensitivity — verified

**2026-10-31 KST**, technical-only imaging QC; **no MRI–RNA association**, no clinical patient enrollment or exclusion. Live [GitHub Actions #173](https://github.com/kimtk94/Codex/actions/runs/41161863748) was successful: two independent 7-case shards and one strict 14-case/28-reader aggregation job; legacy HCC tests and clinical/source join also PASS.

## Frozen experimental configuration

- Source: the same original LiverHccSeg v1.1 14 index HCC lesions, all portal venous (PV); one image and the same tumor number for each of two expert-generated rater masks. A10Y indexes **tumor3**.
- **Native reference**: unchanged earlier PyRadiomics v3.1.0 image normalization, scale 100, binWidth=25, ten original features, **no interpolation**; same original image/mask ZIP members re-downloaded from official Zenodo using bounded ZIP member requests.
- **Sensitivity condition**: target voxel spacing **3×3×3mm**, PyRadiomics 3.1.0 B-spline image interpolation (`sitkBSpline`), nearest-neighbor mask resampling, `padDistance=5`, same normalization/discretization and the same physical source ROI.
- Source package/environment pinned to Python 3.9, numpy 1.26.4, PyRadiomics 3.1.0. The package API returns `v3.1.0` in `radiomics.__version__`, correctly normalized for the version check after an initial false-negative pilot.
- PyRadiomics reference [customization / resampledPixelSpacing](https://pyradiomics.readthedocs.io/en/latest/customization.html) clarifies that image and ROI masks use different interpolators, with nearest-neighbor preserving discrete mask labels.
- This is an **outcome-blind reproducibility/QC comparison**, not IBSI phantom accuracy validation, not a scientifically independent second MRI acquisition, and does NOT restore original 10.8mm z-resolution by interpolation.

## Audit outputs and provenance

- Real run [#173, PASS](https://github.com/kimtk94/Codex/actions/runs/41161863748): **7/7 + 7/7 exact patients**, **14×2=28 reader rows**, 10 original+10 resampled PyRadiomics features per rater; all 10 native ICC(A,1) numerically reproduced within 0.003 of frozen [original baseline](HCC_MRI_PV_RATER_ICC_14_FEATURE_STABILITY_20261030.csv).
- Frozen 10-feature independent source results: [native vs 3mm ICC, rank preservation and relative drift CSV](HCC_MRI_PV_14X2_NATIVE_VS_3MM_FEATURE_REPRODUCIBILITY_20261031.csv).
- Frozen 14-person lesion and three primary features sensitivity: [native/resampled tumor ROI volume and feature changes](HCC_MRI_PV_14_NATIVE_3MM_ROI_VOLUME_AND_PRIMARY_FEATURE_CHANGE_20261031.csv).
- Complete all-28 reader original and resampled feature table (280 paired feature values), 10-feature summary, 14-person change summary and JSON: `hcc-pv-3mm-native-vs-resampled-14x2` GitHub Actions artifact from run #173. GitHub artifact retention is finite, so the two small derived stable CSV tables above are committed permanently, while exact 28-reader data are downloadable from the run artifact.
- Executable source [`mri_pv_3mm_resampling_sensitivity.py`](ci/mri_pv_3mm_resampling_sensitivity.py) and [`mri_pv_3mm_resampling_aggregate.py`](ci/mri_pv_3mm_resampling_aggregate.py); no gene expression scores or clinical outcomes are imported into either script.

## Main result: reader ICC != voxel resampling stability

| Feature | Native ICC(A,1) | 3mm ICC(A,1) | Across-patient native–3mm mean-feature rank Spearman | Median absolute relative within-patient change across both readers |
|---|---:|---:|---:|---:|
| firstorder Entropy **(frozen primary)** | 0.987377 | 0.985965 | **0.9868** | **0.689%** |
| firstorder InterquartileRange **(frozen primary)** | 0.989092 | 0.992281 | **1.0000** | **1.079%** |
| GLCM Contrast **(frozen primary)** | 0.966796 | 0.967815 | **0.8505** | **77.067%** |
| shape VoxelVolume | 0.996282 | 0.996233 | 1.0000 | 0.782% |
| shape SurfaceArea | 0.995259 | 0.995470 | 1.0000 | 3.409% |
| shape Sphericity | 0.821735 | 0.860373 | 0.8022 | 4.057% |
| shape Elongation | 0.727457 | 0.805647 | 0.9912 | 0.431% |
| firstorder Mean | 0.999486 | 0.999458 | 1.0000 | 0.228% |
| firstorder Median | 0.999099 | 0.998947 | 1.0000 | 0.248% |
| GLCM JointEntropy | 0.984886 | 0.987232 | 0.9604 | 5.736% |

**Interpretation:** all ten original ICC values reproduced, and **8/10 resampled feature ICC point estimates remain ≥0.90**. But GLCM Contrast shows a **77.1% median absolute relative change**, a *major quantitative dependency* on voxel grid and its effects on neighborhood/distance discretization. High intra-image two-reader ICC does **not** mean the feature is numerically invariant across native and resampled representations. Feature scaling shifts can matter even when ranks are fairly preserved: Contrast `rho=0.8505`, whereas Entropy and IQR retain `rho≈0.987` and `1.000` respectively. Relative error is undefined/unstable near zero denominators; source contrasts in these cases are nonzero and both source and resampled values are retained.

### Predefined primary GLCM image-feature caution

- `TCGA-DD-A4NJ` rater1 GLCM Contrast **0.9106 → 2.4667** (+170.9% absolute relative).
- `TCGA-DD-A4NH` **0.4784 → 1.1906** (+148.9%).
- `TCGA-G3-A3CJ` **1.1752 → 2.3263** (+97.9%).
- These are **pre-molecular technical results**, not associations with the patient purity markers or RNA Hallmark scores. Do **not** rank or select biological patients by these feature-change magnitudes.
- The locked MRI feature family in [SAP](HCC_MRI_RNA_PREOUTCOME_HALLMARK_SAP_V1.md) remains Entropy, Contrast and IQR × 4 RNA pathways (12 planned). Contrast receives an **explicit sensitivity warning**; the research cannot call it acquisition invariant. Do not silently replace it post hoc; if a prospective protocol amendment is needed, disclose old/new version and justify it before MRI–RNA tests.

### Special original anisotropy / tumor volume cases

- **TCGA-BC-A10Y** original PV through-plane spacing **10.8mm**, in-plane ~0.742mm, z/in-plane ratio **14.55** and index tumor3. After 3mm resampling, rater1 lesion grid volume **740.187→742.878mL (+0.364%)**, Entropy changed ~0.913%, Contrast ~17.70%, IQR ~1.16% for rater1. **Smaller GLCM change than some patients with thin slices does NOT resolve loss of original through-plane detail.** Do not drop A10Y based on feature association.
- **TCGA-G3-AAV7** small ~6mL lesion: rater1 native→3mm grid volume **6.005→5.697mL (−5.135%)** versus rater2 **5.990→6.021mL (+0.525%)**. Underlines that a small ROI can be more sensitive to discrete mask regridding than a very large tumor.
- All masks retain the same patient and tumor index; regridding did not create new diagnostic evidence or correct the limited 14-person sample size.

## Research decision / follow-up gates

**Technical 3mm within-image sensitivity GO**; however **cross-acquisition GLCM stability = REVIEW / not established**; IBSI phantom and precise source PV DICOM manufacturer/sequence still **PENDING**. Keep HCC-13 and HCC-18 **PARTIAL**. HCC-14 pretreatment source and HCC-17 qualified paired n **HOLD/PENDING**; HCC-20 primary 12 MRI–RNA association tests **STOP until clinical gates pass**. Manuscript significance claim ceiling **S0**.

Recommended next **technical** tests without gene expression:
1. Recalculate GLCM Contrast at another predeclared spacing/discretization and **state precisely** resampling and intensity normalization settings, preserving both originals and all negative findings. Avoid choosing the result giving the strongest eventual biological relationship.
2. Verify feature definitions against IBSI phantom/reference when possible; PyRadiomics GLCM discretization and orientation averaging require explicit method reporting.
3. Obtain exact source PV DICOM series manufacturer/sequence, original response to extracellular vs hepatobiliary agents and image acquisition metadata where available; never claim same scanner solely from study-level 1.5T.
4. Perform genuine scan-to-therapy and same-lesion MRI↔RNA clinical source adjudication; no radiomics-only QC substitutes for that.

No biological MRI–RNA correlation `rho`, p-value, q-value, or selected clinical sample flow was generated.
