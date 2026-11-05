# HCC-18 IBSI-1 CT Configuration B numerical reproduction (actual CI)

**Run:** https://github.com/kimtk94/Codex/actions/runs/41186558822  
**PR:** https://github.com/kimtk94/Codex/pull/228  
**Date:** 2026-10-31 (KST) · **Result:** PASS CT-B official reference measurements, 4/4 Jobs successful.

## Source and exact preprocessing

- Source official `theibsi/data_sets` pinned commit `6da96021bc91faf4c0cb7fd7fa56a4225d2064a8`.
- CT source NIfTI image SHA-256 `909129fdf99d5f5fd17bc568b1834d31edce8663ea6746c6020720bfc1d7bbcb`; mask SHA-256 `0e9243e473b1255c60e6460df465d0b07b65436d6e0c691fe3d17bca0594ae78`.
- **Original non-small-cell lung cancer PAT1 GTV phantom, not an HCC patient.** Raw/derived CT pixel maps excluded from shared artifacts (CC BY-NC 3.0).
- Native 204×201×60, 0.977×0.977×3.0mm to **100×99×60, 2×2×3.0mm** with SimpleITK centered-grid axial bilinear interpolation; nearest-integer intensity rounding; ROI bilinear fractional threshold >=0.5.
- Interpolated morphology mask **29,842 voxels**, [-500,400] HU resegmented intensity ROI **27,359 voxels**.
- FBN32 discretization uses **actual ROI min -500 HU and max +391 HU**, not fixed HU bounds or FBS25. Levels 1...32.
- GLCM symmetric Chebyshev distance one voxel; **2D:avg** for independent slice-direction average; **2.5D:dmrg** for independent direction-merged and PyRadiomics forced axial 2D. 2D:avg is not natively measured by that PyRadiomics call.
- PyRadiomics 3.1.0 GLCM receives **explicit externally FBN32 encoded image** with 1-HU bin width; PyRadiomics does not implement FBN32 as its native bin-width switch.

## Official IBSI CT-B values and observed results

| Feature | IBSI code | Reference | Official tolerance | Independent | PyRadiomics | Result |
|---|---|---:|---:|---:|---:|---|
| Mean | Q4LE | 11.5 | ±1.1 | 11.530100 | 11.530100 | PASS |
| Median | Y12H | 45 | ±0.3 | 45 | 45 | PASS |
| Interquartile Range | SALO | 52 | ±0.5 | 52 | 52 | PASS |
| GLCM Contrast **2D:avg** | ACUI | 11.9 | ±0.1 | 11.884356 | not natively tested | PASS independent |
| GLCM Contrast **2.5D:dmrg** | ACUI | 8.66 | ±0.09 | 8.659118505446799 | 8.659118505446793 | PASS |

**Numeric outcome:** independent **5/5 PASS**, PyRadiomics **4/4 PASS**; both measurements use same exact source/hashes and same intensity mask. Their 2.5D:dmrg Contrast difference is **5.329070518200751×10⁻¹⁵**.

Final integrator returns `PASS_CT_B_INTERPOLATION_FBN32_FEATURE_REFERENCES`. Crucially, the two calculators share one **SimpleITK** resampled pixel/ROI preparation. The result therefore supports agreement between the independent matrix math and PyRadiomics extraction *after one shared interpolator*, and reproducibility of these selected official references; **it does not independently cross-verify interpolation algorithms**.

## Scientific gate and next checkpoint

- Source hash + official measurement numerics: **PASS for the tested subset of CT B**.
- Independent resampling engine / mask partial-volume implementation comparison: **PENDING**.
- IBSI-1 CT C–E (3D interpolators) and IBSI-2 filtered images: **NOT EXECUTED**.
- HCC-18 remains **PARTIAL**. Original HCC 14-case clinical eligibility and same MRI-tumor tissue / pre-therapy date reconstruction still open.
- HCC-20 primary twelve MRI–RNA association tests **PENDING, NOT AUTHORIZED**. No biological effect, clinical significance, or entire IBSI software certification is established. Manuscript **claim ceiling S0**.

Permanent numeric data: [Frozen CT A/B values](HCC_IBSI_CT_A_B_FROZEN_REFERENCES_20261031.json). GitHub PR regression: [fail-closed offline test](ci/mri_ibsi_ct_a_b_frozen_result_qc.py). Official references: [IBSI image processing](https://ibsi.readthedocs.io/en/master/02_Image_processing.html), [IBSI data and CT configuration B](https://ibsi.readthedocs.io/en/master/05_Reference_data_sets.html), [IBSI image features](https://ibsi.readthedocs.io/en/master/03_Image_features.html).
