# HCC IBSI-1 CT Phase II Configuration A: independent + PyRadiomics cross-verification

**2026-10-31 KST, source run:** https://github.com/kimtk94/Codex/actions/runs/41186059566  
**Repository PR:** https://github.com/kimtk94/Codex/pull/228  
**Source:** `theibsi/data_sets` commit `6da96021bc91faf4c0cb7fd7fa56a4225d2064a8`

## Final verification result

- GitHub Actions: **4/4 jobs successful**, final scientific join: **PASS_CT_A_FIVE_INDEPENDENT_FOUR_PYRADIOMICS**.
- Independent 2D/2.5D GLCM math on official NIfTI: **5/5 IBSI feature references PASS**.
- PyRadiomics v3.1.0 on same source, binWidth25 with `force2D`: **4/4 corresponding IBSI references PASS**.
- No interpolation or normalization; NIfTI intensity rounding nearest integer; resegmentation [-500,400] HU; symmetric Chebyshev-distance-one GLCM.
- Distinct aggregation methods never confused: **2D:avg** tested by independent implementation; **2.5D:dmrg** tested by both. Standard 2D:avg is not natively reproduced by this PyRadiomics `force2D` call.
- Morphological ROI **125,256** voxels; intensity ROI after resegmentation **114,596** voxels.

| IBSI reference | Aggregation | Reference | Tolerance (official) | Independent | PyRadiomics |
|---|---|---:|---:|---:|---:|
| Mean (Q4LE) | whole intensity ROI | 13.4 | 1.1 | 13.408426 | 13.408426 |
| Median (Y12H) | whole intensity ROI | 46 | 0.3 | 46.000000 | 46.000000 |
| IQR (SALO) | whole intensity ROI | 56 | 0.5 | 56.000000 | 56.000000 |
| GLCM Contrast (ACUI) | 2D:avg | 7.85 | 0.26 | 7.851407 | NOT TESTED |
| GLCM Contrast (ACUI) | 2.5D:dmrg | 5.96 | 0.27 | 5.960989939109945 | 5.960989939109950 |

Independent vs PyRadiomics 2.5D:dmrg Contrast absolute difference: **5.329070518200751e-15**. The local cross-implementation diagnostic threshold of 1e-5 is **not** an IBSI-published tolerance; per-feature reference tolerances above are from IBSI.

Reference sources:
- https://ibsi.readthedocs.io/en/master/05_Reference_data_sets.html
- https://ibsi.readthedocs.io/en/master/03_Image_features.html

**Source checksum (unchanged):**
- CT image SHA256: `909129fdf99d5f5fd17bc568b1834d31edce8663ea6746c6020720bfc1d7bbcb`
- CT mask SHA256: `0e9243e473b1255c60e6460df465d0b07b65436d6e0c691fe3d17bca0594ae78`

**Scientific ceiling:** These are *lung-cancer CT phantom* standardization measurements, **not HCC patient imaging**. This validates only five reported CT-A reference/aggregation measurements, not the entire configuration A IBSI feature set, CT B–E, IBSI-2 filtered images, scanner harmonization, or pretreatment HCC case eligibility. The status remains **HCC-18 PARTIAL**, **HCC-20 PENDING**, **claim ceiling S0**. Do not run the twelve prespecified MRI–RNA associations based on phantom success alone. CC BY-NC 3.0: raw CT images and masks were not redistributed.

## Next frozen checkpoint

IBSI-1 **Configuration B**: 2D bilinear image/mask resampling to 2×2mm (z spacing unchanged), centered grid with ceiling dimensions, round intensities to nearest integer, ROI fractional-mask cutoff >=0.5, HU range [-500,400], *FBN32 (not FBS25)* and separate 2D:avg/2.5D:dmrg GLCM computations. Record 100×99×60 geometry and diagnostic mask counts. If interpolation implementation or FBN convention differs, mark **REVIEW**, never adjust reference values to obtain PASS.

B official references currently planned: Mean 11.5±1.1; Median 45±0.3; IQR 52±0.5; Contrast 2D:avg 11.9±0.1; Contrast 2.5D:dmrg 8.66±0.09.

The exact eligibility bottleneck is still independent MRI-before-treatment and exact tumor–RNA tissue matching (HCC-14, HCC-17); no automatic biological finding is authorized.
