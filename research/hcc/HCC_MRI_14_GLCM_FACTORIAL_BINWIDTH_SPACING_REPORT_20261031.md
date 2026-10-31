# HCC MRI GLCM binWidth × voxel spacing — complete 14 × 2 × 2 × 3 empirical factorial

**Date:** 2026-10-31 KST. **Result: PASS, outcome-blind image measurement sensitivity only.** This does not establish pretreatment MRI, same-lesion tissue correspondence, patient clinical eligibility or IBSI phantom certification.

## Source execution and reproducibility

- [GitHub Actions HCC Public Cohort Audit #185](https://github.com/kimtk94/Codex/actions/runs/41170599536) executed **two independent 7-case × 2-reader × 2-spacing × 3-binWidth shards** in parallel, then one strict aggregation Job: **14 patients, 28 unique rater profiles, 168 extraction cells, four original image features** per cell; **PASS**.
- Python 3.9, NumPy 1.26.4, PyRadiomics **v3.1.0**, official [LiverHccSeg Zenodo 8179129](https://zenodo.org/records/8179129) original PV images and masks; same predefined index lesions (A10Y tumor3), same two published readers. `featureextractor` parameters inherited from original 2026-10-30 report: `normalize=True`, `normalizeScale=100`, `voxelArrayShift=0`, `minimumROIDimensions=2`, `correctMask=False`, `preCrop=True`.
- **Grid condition**: (1) native original MRI voxel size unchanged, (2) isotropic 3×3×3 mm using `sitkBSpline` MRI interpolation and nearest-neighbor binary mask label resampling, same image/ROI and physical tumor label.
- **Discretization condition** `binWidth=12.5, 25.0, 50.0`, with original **25.0** as frozen reference. GLCM settings made explicit: `symmetricalGLCM=True`, `distances=[1]` in *voxel* units and `weightingNorm=None`. Thus the physical neighboring distances differ between anisotropic native and isotropic 3mm grids; **this is a joint voxel geometry and interpolation sensitivity**, not a claim of constant physical displacement.
- Four measured features: `original_glcm_Contrast`, `original_glcm_JointEntropy`, `original_firstorder_Entropy`, `original_firstorder_InterquartileRange`. No RNA, pathology, p-values, drug outcomes, patient sample filtering or modification of the prespecified 12 image–RNA test hypotheses.
- Verified against the frozen [native/3mm two-rater ICC results](HCC_MRI_PV_14X2_NATIVE_VS_3MM_FEATURE_REPRODUCIBILITY_20261031.csv): **all 4 features × both native and 3mm binWidth 25 ICC = 8/8 reference values reproduced** with strict ±0.003 tolerance; all 168 extraction cells finite and source-matched.
- Frozen derived [24-cell condition-by-feature ICC/rank/relative-change source CSV](HCC_MRI_14_GLCM_BINWIDTH_VOXEL_FACTORIAL_20261031.csv) and [14-patient GLCM Contrast per-case source QC CSV](HCC_MRI_14_GLCM_CONTRAST_CASE_FACTORIAL_20261031.csv); full **112 patient × reader × feature rows**, six measurements per row, in time-limited `hcc-glcm-factorial-14x2-summary` artifact.

## Primary methodological finding: GLCM Contrast responds strongly to binWidth

This is the median **absolute relative within-person/reader difference** from `binWidth 25` at the *same grid*, calculated on all **28 rater profiles**:

| Feature | Native bin 12.5 | Native bin 50 | 3mm bin 12.5 | 3mm bin 50 |
|---|---:|---:|---:|---:|
| **GLCM Contrast** | **+253.33% absolute relative** | **65.19% absolute relative** | **270.49%** | **68.09%** |
| GLCM JointEntropy | 39.19% | 34.22% | 39.35% | 33.21% |
| Firstorder Entropy | 35.03% | 32.61% | 35.47% | 32.63% |
| Firstorder InterquartileRange | **0.00%** | **0.00%** | **0.00%** | **0.00%** |

- The `+` above is a description of **absolute relative magnitude**; the sign of each original individual patient's actual change must be read from the full patient output. The `binWidth 50` GLCM contrast values generally decrease as coarser binning reduces gray-level differences. **Do not interpret a 253% change as patient biology**.
- Under **fixed native spacing**, across-patient rank correlations of mean reader Contrast relative to binWidth 25 were **rho 0.9956 for binWidth 12.5**, **rho 0.9648 for binWidth 50**. Under **3mm**, they were **0.9956** and **0.9253**, respectively. So numeric values change far more than patient ranking: rank-based biological testing could sometimes be less sensitive to binWidth changes than raw numeric effects, but **no MRI–RNA associations were run**.
- In contrast, **native vs 3mm at the same original binWidth 25**, Contrast absolute relative change across 28 reader values has median **77.42%**. The prior equal-weight-per-patient (two-reader mean, then 14-patient median) calculation was **77.07%**, a different descriptive aggregation—not a data contradiction. The source 3mm case-specific example `TCGA-DD-A4NJ` reader1 increases **0.910601 → 2.466661**.
- Contrast ICC(A,1) stays deceptively high across configurations:

| Condition | binWidth 12.5 | binWidth 25 | binWidth 50 |
|---|---:|---:|---:|
| Native Contrast ICC | 0.96693 | 0.96680 | 0.96702 |
| 3mm Contrast ICC | 0.96869 | 0.96782 | 0.96730 |

**High two-rater segmentation consistency therefore does not imply numerical invariance under binWidth or grid interpolation.** Fixed-binWidth changes can rescale Contrast across patients almost monotonically, so point estimates and ranking stability must be reported **separately**. Between-grid rank changes are more serious for the locked *Spearman-based* primary family.

## Patient-level QC and methodological cautions

- `TCGA-BC-A10Y` remains the original **10.8mm through-plane** PV MRI index tumor3; its two-reader median native→3mm relative Contrast shift at bin25 is **14.68%**, not the largest of the cohort. Interpolation does NOT recover missing 10.8mm acquired detail; retain patient-level native acquisition flag.
- `TCGA-DD-A4NJ` has the largest 3mm-versus-native Contrast change among the 14 at bin25: two-reader median **170.08%**. Its lack of ABSOLUTE DNA purity has no causal connection established with MRI feature changes.
- Patient-level binWidth sensitivities and original native/resampled reference Contrast for all 14 cases are in the frozen derived CSV, without RNA score linkage.
- `original_firstorder_InterquartileRange` is not a discretized gray-level histogram feature and remains invariant to binWidth in this PyRadiomics setting. `original_firstorder_Entropy` **is** discretization-sensitive: ~35% (halving) and ~33% (doubling), despite its previously low original-vs-3mm voxel-grid shift (~0.69%).
- Limitations: n=14 technical candidates, MRI source 1.5T metadata at patient level (not exact sequence), unknown exact scanner vendor, selected-lesion clinic verification missing, no external scanner/sequence replication, no noise/contrast normalization sensitivity or IBSI digital phantom measurement acceptance. Do not ComBat-harmonize sparse scanner labels or choose a binWidth by prospectively looking at MRI–RNA test p-values.

## IBSI and PyRadiomics standardization distinction

- IBSI identifier **ACUI** GLCM Contrast is based on `Σ (i−j)^2 p_ij`; the standardized **3D directional-averaged** digital phantom reference is **5.32**, while **3D directional-merged** is **5.12**—different valid aggregation choices. [Official IBSI feature standard](https://ibsi.readthedocs.io/en/master/03_Image_features.html).
- PyRadiomics default symmetrizes GLCMs and averages feature values across the 3D directions if no weighting is selected, analogous to the IBSI **3D:avg** family; we did **NOT** run the official 5×4×4 IBSI phantom here and do NOT claim 5.32 agreement.
- The PyRadiomics documented `5×5` 2D illustrative symmetric GLCM has `Σ P_ij=40`, `ΣP_ij(i−j)^2=116`, hence **contrast 2.9** for that *single illustrative direction*, verified by our pure-Python regression; this **is not** the IBSI 3D phantom reference. [PyRadiomics GLCM documentation](https://pyradiomics.readthedocs.io/en/stable/features.html).
- The PyRadiomics FAQ explicitly documents differences from IBSI in **fixed-bin-size edge origin** and **interpolation grid alignment/rounding**. Thus reproducibility across settings does not prove standardized conformance: [PyRadiomics FAQ](https://github.com/AIM-Harvard/pyradiomics/blob/master/docs/faq.rst), [IBSI Radiology standard](https://doi.org/10.1148/radiol.2020191145).
- **Future IBSI gate:** official IBSI digital 3D phantom must be fetched, checksum pinned, image+mask orientation/gray-level discretization and GLCM aggregation specified, then `Contrast IBSI 3D:avg` compared against 5.32 with documented tolerance. PyRadiomics may need custom binning/resampling to match; mark any deviation explicitly. Until then, **IBSI_PASS = NOT_ASSESSED**.

## Downstream decisions remain LOCKED

- **Measurement sensitivity complete (technical GO)**; GLCM Contrast *numerical portability* across binWidth and grid conditions remains **not established**. The high ICC must not be presented as proof of acquisition-protocol robustness.
- **HCC-13 and HCC-18 remain PARTIAL** (reader repeatability and factor sensitivity quantified, but IBSI phantom, true scanner and clinical lesion validation unresolved).
- **HCC-14 clinical pretherapy = PARTIAL/HOLD; HCC-17 paired final n = PENDING; HCC-20 primary 12 MRI–RNA tests = PENDING, NOT EXECUTED; S0 maximum claims.** No patient excluded automatically.
- Original frozen 12-test family (3 MRI features including Contrast, four Hallmark pathways) **unchanged**. If future clinical eligibility permits molecular associations, report all primary tests plus prespecified setting sensitivities; do not optimize binWidth, voxel size or feature inclusion based on outcome significance.
