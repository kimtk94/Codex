# HCC MRI — IBSI-1 official digital phantom and PyRadiomics ACUI reproducibility, 2026-10-31

## Evidence status

**Verified GitHub Actions run:** [HCC Public Cohort Audit #202, all jobs PASS](https://github.com/kimtk94/Codex/actions/runs/41173010049), original source commit `6da96021bc91faf4c0cb7fd7fa56a4225d2064a8` from the official [theibsi/data_sets](https://github.com/theibsi/data_sets/tree/master/ibsi_1_digital_phantom/nifti).

**Result: IBSI-1 GLCM Contrast (ACUI) 3D directional-average digital phantom benchmark PASS.** Not equivalent to complete IBSI feature/profile certification, same-scanner technical reproducibility, pretreatment MRI–RNA lesion pair eligibility, or external biological validation.

### Original official binary data, immutable provenance

| Field | Verified original |
|---|---|
| NIfTI image | `ibsi_1_digital_phantom/nifti/image/phantom.nii.gz` |
| NIfTI mask | `ibsi_1_digital_phantom/nifti/mask/mask.nii.gz` |
| Original image SHA-256 | `83773ac2a288aa93cf819a98eaf301c18d35d5876182ec9c18733184e2b7a83a` |
| Original mask SHA-256 | `3032d340944b577b83bc559ea7ae9a6034b84633a840eff39570ec17aa1d6281` |
| Original repository source commit | `6da96021bc91faf4c0cb7fd7fa56a4225d2064a8` |
| Image size / mask size | 126 bytes / 99 bytes (gzip NIfTI) |
| Dimensions | 5 × 4 × 4 = 80 image voxels |
| Binary ROI | 74 voxels, excluded 6 |
| Spacing | 2 × 2 × 2 mm |
| Included integer ROI intensity levels | 1, 3, 4, 6 |
| License | IBSI-1 digital phantom CC BY 4.0 as in official `README.md` |

**Do not use IBSI-2 or the deprecated DICOM phantom**, whose ROI spacing is known incorrect. The original IBSI-1 digital phantom does not require any interpolation or MR image normalization.

### Actual measured result: three independent lines of evidence

| IBSI feature / method | Official published two-digit reference | Direct stdlib mathematical result | PyRadiomics v3.1.0 |
|---|---:|---:|---:|
| ACUI GLCM Contrast, **13 3D direction-specific feature values averaged** (3D:avg) | **5.32** | **5.324479993784631** | **5.324479993784630** |
| ACUI GLCM Contrast, **13 3D direction co-occurrence matrices pooled before the feature calculation** (3D:mrg) | **5.12** | **5.117647058823529** | **NOT TESTED** (separate aggregation) |

The original mathematical 3D:avg and PyRadiomics results agree within numerical floating-point precision. The **5.32 reference is rounded**: difference of PyRadiomics `5.32447999 − 5.32 = 0.00447999` does not indicate erroneous implementation. This experiment reports a diagnostic absolute tolerance of **0.025**; it is an internal check, **not an IBSI-defined acceptance range**. The 3D:mrg value `5.12` is a different aggregation method; do **not** compare the PyRadiomics direction-averaged feature to the merged value.

**Independent computation:** Python standard library only, gzip decompress original NIfTI int16 voxels, enumerate 13 three-dimensional undirected Chebyshev-one neighbor offsets (the corresponding GLCMs are symmetric), compute each direction's sum `Σ (g_i−g_j)^2 / n_pairs`, average direction Contrast values for 3D:avg, and divide total weighted-squared-difference sum by total valid pairs for 3D:mrg. `527` valid undirected neighboring pairs in total. All 13 directional values are archived in the time-limited action artifact `hcc-ibsi1-independent-reference`.

**PyRadiomics computation:** Python 3.9, PyRadiomics 3.1.0, `binWidth=1`, `normalize=False`, `voxelArrayShift=0`, `resampledPixelSpacing=None`, `correctMask=False`, `symmetricalGLCM=True`, `distances=[1]`, `weightingNorm=None`, `additionalInfo=False`, original 3D image only and label 1 mask; observed `original_glcm_Contrast=5.32447999378463`. `original_glcm_JointEntropy=2.399711278373436` is also observed, but its dedicated IBSI reference check was **not** the predeclared acceptance target of this experiment. The value is consistent with the separate published 3D average joint entropy rounded reference 2.4.

### Actual parallel CI DAG and results

- **Original official source acquisition**: independent Github repository clone and immutable source commit/image/mask SHA-256 artifact `hcc-ibsi1-official-source` — **PASS**.
- **Independent mathematical IBSI 3D:avg and 3D:mrg**: pure Python original official NIfTI 13-direction GLCM computation, artifact `hcc-ibsi1-independent-reference` — **PASS**.
- **Real PyRadiomics 3.1.0 3D:avg contrast**: exactly the same official original image/mask, with documented settings; artifact `hcc-ibsi1-real-pyradiomics` — **PASS**.
- **Clinical and existing 14-case source protocol safety**: frozen original HCC candidate count 14, 24 GLCM condition-level source rows and no clinical or MRI–RNA test promotions — **PASS**.
- **Evidence join**: downloader of official source, independent math and PyRadiomics artifacts, checks all three original git commit and hashes, and refuses claim-level promotion; artifact `hcc-ibsi1-final-scientific-gate`, status **PASS_REFERENCE_MATH_AND_SOURCE_COHERENCE**.
- The existing **six HCC parallel data-provenance/readiness jobs and offline regression tests** also passed in [run #202](https://github.com/kimtk94/Codex/actions/runs/41173010049).

Full machine-readable source and computed results are committed in [HCC_IBSI1_OFFICIAL_PHANTOM_GLCM_VALIDATION_20261031.json](HCC_IBSI1_OFFICIAL_PHANTOM_GLCM_VALIDATION_20261031.json), protected by [no-network CI regression script](ci/mri_ibsi1_frozen_source_result_qc.py). The independent 13-direction detailed CSV and original full action manifests can be downloaded from the GitHub Action's 30-day artifact window.

### What is scientifically justified and what remains unverified

**PASS** for a *specific* imaging-software-method calibration claim: PyRadiomics v3.1.0 default unweighted, symmetric 3D directional-averaged GLCM Contrast reproduces the IBSI-1 digital phantom reference 5.32 under specified binWidth1, no interpolation/no normalization.

**HOLD/PARTIAL**, not PASS, for broad IBSI imaging feature standardization: clinical MRI pilot settings used `binWidth=25`, `normalize=True`, heterogeneous original native voxel spacings and 3mm interpolation, not the phantom's no-preprocessing configuration. The prior 14-patient factorial found Contrast median absolute relative changes **253.3%** (native bin 25→12.5), **65.2%** (native 25→50), **~77%** (native→3mm at bin25), despite strong two-reader ICC. The phantom PASS **does not erase these measured image-parameter sensitivity problems** or prove scanner/batch reproducibility.

**Clinical eligibility remains unresolved:** HCC-13 image repeatability and HCC-18 technique QC **PARTIAL**, HCC-14 pretherapy same-lesion chronology **PARTIAL/HOLD**, HCC-17 qualified paired n **PENDING**, HCC-20 original 3 image features × 4 Hallmark **12 biological MRI–RNA tests NOT RUN**. Maximum current manuscript claim level **S0**. No patients promoted/excluded from eligibility, no imaging-to-RNA correlation, p-value, q-value or disease inference computed.

## Official scientific sources

- [IBSI-1 reference digital phantom and original image/mask](https://github.com/theibsi/data_sets/tree/master/ibsi_1_digital_phantom/nifti), licensed CC BY 4.0.
- [IBSI image features ACUI Contrast, table: 3D averaged 5.32 vs 3D merged 5.12](https://ibsi.readthedocs.io/en/master/03_Image_features.html).
- Zwanenburg et al. (2020), *Radiology* 295:328–338, DOI [10.1148/radiol.2020191145](https://doi.org/10.1148/radiol.2020191145).
- [IBSI Phase 1 reference phantom design](https://ibsi.readthedocs.io/en/latest/05_Reference_data_sets.html).
- [PyRadiomics feature documentation](https://pyradiomics.readthedocs.io/en/stable/features.html).

**Future technical work**: second IBSI CT benchmark with predefined preprocessing/discretization settings and same PyRadiomics feature, plus phantom checks of additional 9 measured features; do not represent a single Contrast PASS as all features certified. Clinical gate next needs source-authoritative pretreatment scan and MRI-to-tissue anatomical identity.
