# HCC-18 IBSI-1 CT Configuration A: verified benchmark and scope
**Date:** 2026-10-31 KST  
**Evidence:** [GitHub Actions run 41186059566](https://github.com/kimtk94/Codex/actions/runs/41186059566) · [PR #228](https://github.com/kimtk94/Codex/pull/228) · [frozen JSON](HCC_IBSI1_CT_CONFIG_A_OFFICIAL_BENCHMARK_20261031.json)

## Verified result

All four workflow jobs passed: independent raw CT calculator, pinned PyRadiomics 3.1.0 extraction, offline regression and independent/PyRadiomics scientific integration. The final source-locked verdict was `PASS_CT_A_FIVE_INDEPENDENT_FOUR_PYRADIOMICS`. This validates **IBSI-1 Phase II CT Configuration A only**.

| Feature (IBSI code) | IBSI-A reference | IBSI-published tolerance | Independent observed | PyRadiomics observed |
|---|---:|---:|---:|---:|
| Mean (Q4LE) | 13.4 | ±1.1 | 13.4084261231 | 13.4084261231 |
| Median (Y12H) | 46.0 | ±0.3 | 46.0000000000 | 46.0000000000 |
| Interquartile range (SALO) | 56.0 | ±0.5 | 56.0000000000 | 56.0000000000 |
| GLCM Contrast 2D:avg (ACUI) | 7.85 | ±0.26 | 7.8514065128 | NOT COMPUTED |
| GLCM Contrast 2.5D:dmrg (ACUI) | 5.96 | ±0.27 | 5.9609899391 | 5.9609899391 |

Two GLCM aggregation conventions are deliberately **not interchangeable**. The independent calculation covers both; PyRadiomics with `force2D=True`, `force2Ddimension=0`, `weightingNorm=None` reproduces 2.5D direction-merged and is **not** passed off as 2D averaged. The cross-implementation absolute difference in 2.5D Contrast was **5.3290705182 × 10⁻¹⁵** (comparison tolerance 1e-5 is a **local diagnostic threshold**, not IBSI-published).

## Original input and controls
- Official repository: `theibsi/data_sets` git commit `6da96021bc91faf4c0cb7fd7fa56a4225d2064a8`.
- Image SHA-256: `909129fdf99d5f5fd17bc568b1834d31edce8663ea6746c6020720bfc1d7bbcb`.
- Mask SHA-256: `0e9243e473b1255c60e6460df465d0b07b65436d6e0c691fe3d17bca0594ae78`.
- Original CT NIfTI: 204×201×60; GTV mask: 125,256 voxels.
- Configuration A: no resampling; nearest-integer HU; ROI resegmentation −500 to 400 HU inclusive; texture bin width 25 HU; 4 in-plane distance-1 directions; symmetric GLCM. Resulting intensity ROI: **114,596 voxels** (observed intensity minimum −500 HU and maximum 377 HU).
- Original official CT source license: **CC BY-NC 3.0**. No CT image or mask bytes stored in the Git repo or CI artifacts; only derived numerical evidence.
- Source provenance, ROI count, identical PyRadiomics intensity-ROI count and version-pinned settings are checked by CI.

## Scientific claim guard
- IBSI-1 **Digital Phantom 10/10 PASS** was separately documented in [prior report](HCC_IBSI1_TEN_FEATURE_AND_CT_DUAL_SOURCE_VALIDATION_20261031.md) from run 41179519399.
- IBSI-1 **CT Configuration A PASS** is the additional result from run 41186059566; CT **B–E remain NOT EXECUTED**, and **IBSI-2 CT filtered-feature response maps remain NOT EXECUTED**. Identical IBSI-1/2 CT original file hashes do not establish any IBSI-2 filtering compliance.
- HCC-18 status remains **PARTIAL**, HCC-13 and clinical timing/lesion linkage still partial, HCC-20 MRI–RNA associations remain **PENDING NOT EXECUTED**, clinical claim ceiling **S0**, fourteen MRI candidates are not the qualified patient denominator.
- IBSI CT patient PAT1 is a reference CT phantom (not an HCC patient); it is not included in any clinical cohort.

## Next checkpoints (separate from this completed result)
1. Freeze source-validated CT-A numeric snapshot and run strict offline regression on every PR change, including mutation tests that reject erroneous 'full IBSI compliance' or HCC-20 promotion.
2. Define IBSI-1 CT **B–E** resampling, mask partial-volume threshold, fixed-bin-number vs fixed-bin-size, 2D/3D spatial aggregation and published reference tolerances **before** selecting PyRadiomics APIs. Mark unsupported or non-equivalent implementations as **REVIEW**, not PASS.
3. Run IBSI-2 filtered-feature response-map benchmark separately; do not conflate with CT B–E.
4. Return to the decisive biological research gate: source-verifiable **MRI-before-therapy chronology, same MRI tumor lesion–RNA tissue match and expert image review**. The 12 frozen associations must not run until eligibility is established.

## Links
- [Official IBSI image features](https://ibsi.readthedocs.io/en/master/03_Image_features.html)
- [Official IBSI reference data sets](https://ibsi.readthedocs.io/en/master/05_Reference_data_sets.html)
- [Independent/PyRadiomics CI workflow](../../.github/workflows/hcc-ibsi-ct-config-a.yml)
- [Source-aware CT-A code](ci/mri_ibsi1_ct_config_a_benchmark.py)
