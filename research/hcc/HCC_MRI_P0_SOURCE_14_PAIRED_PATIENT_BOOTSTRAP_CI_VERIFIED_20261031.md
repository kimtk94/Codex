# HCC MRI P0 — Paired-patient uncertainty for PV source phase and reader ICC

**2026-10-31 KST; actual GitHub Actions [#41207344436](https://github.com/kimtk94/Codex/actions/runs/41207344436): 2/2 PASS.** Technical image measurement and source sensitivity study only. Clinical paired eligibility **NOT ASSESSED**. Original 12 MRI–RNA associations **0/12 executed**. Claim ceiling **S0**.

## Reproduction contract

- Use only the **frozen 14 independent HCC patients** and the original [56-row source artifact #41191599451](https://github.com/kimtk94/Codex/actions/runs/41191599451), artifact **13039386584**.
- Verify the original ZIP's **four SHA-256 members** against [existing frozen immutable audit script](ci/mri_p0_frozen_source_results_qc.py) before any calculation. The source arm on identical fixed tumor ROI is **unregistered raw `pv.nii.gz`** versus **official registered `art_pv.nii.gz`** reoriented to mask physical space.
- Within each patient, average the two radiologist measures in each source arm **before** source-sensitivity summaries; do not misinterpret 28 reader masks as 28 independent cases.
- Source percentage change per patient = `(registered_pv_patient_mean - raw_pv_patient_mean) / abs(raw_pv_patient_mean) × 100`. Derive median absolute %, median signed % and source-arm Spearman **across 14 patient means**. Exact zero denominators are rejected, not imputed.
- **Simple percentile patient bootstrap**: 4,000 resamples (fixed `numpy.random.default_rng(20261031)`) of patient IDs, 14 draws with replacement each. For all 10 features, keep the same patient indices for two source arms and two readers. Estimate 95% intervals from resample percentiles 2.5/97.5. Source Spearman uses average ranks for ties. This is an uncertainty interval for a **descriptive n=14 convenience sample**, not a population transportability or molecular-association confidence interval.
- Recompute two-way random-effects, single-measurement absolute-agreement **ICC(A,1)** separately by arm, paired bootstrap ICC difference `registered minus raw` from the **same patient-index resamples**. Features with degenerate resample statistics are not silently promoted; each displayed interval has 4,000 valid draws.
- Use **10 originally extracted features**. No RNA data or transcriptome scores were downloaded or accessed; no regression, BH-FDR, permutation MRI–RNA association, treatment response, classifier performance or survival statistics were computed.

## Locked three MRI feature results

| Frozen MRI feature | Median absolute source change % [95% bootstrap CI] | Median signed source change % [95% CI] | Patient rank Spearman ρ [95% CI] | Cases ≥10% absolute change |
|---|---|---|---|---:|
| Entropy | **3.309 [0.334, 5.192]** | −0.424 [−4.852, 0.000] | 0.895 [0.664, 0.982] | 1/14 |
| Interquartile Range | **2.944 [0.950, 10.609]** | −0.728 [−9.991, 0.956] | 0.943 [0.718, 1.000] | 4/14 |
| **GLCM Contrast** | **22.080 [13.937, 30.316]** | **−22.071 [−30.316, −7.676]** | 0.895 [0.598, 0.995] | **11/14** |

Source effects for GLCM Contrast are not driven by *one* patient. Leave-one-patient-out (LOO) median absolute source shift ranges **21.836–22.324%** over the 14 possible omitted patients. For comparison: Entropy **2.681–3.938%**, IQR **2.612–3.276%**. LOO robustness does not make n=14 representative or establish which source processing operation caused each contrast change.

**Note:** source effect size is observational/descriptive, not a pre-specified source equivalence test. A bootstrap CI for a nonnegative median absolute change being positive is **not proof of statistical superiority or clinical significance**. The registered and raw PV processing paths can differ due to deformation, interpolation, header/orientation and/or original source processing; this study does not independently isolate a specific causal component.

## Paired source-arm change in two-reader ICC(A,1)

| MRI feature | Historical raw PV ICC | Official registered PV ICC | Registered minus raw ICC [95% paired patient bootstrap CI] |
|---|---:|---:|---|
| Entropy | 0.987377 | 0.989027 | **+0.001651 [−0.011886, +0.021343]** |
| IQR | 0.989092 | 0.993254 | **+0.004163 [−0.002475, +0.019485]** |
| GLCM Contrast | 0.966796 | 0.951613 | **−0.015183 [−0.033548, +0.020041]** |

All three uncertainty ranges for ICC change **include zero**, so do **not** claim a demonstrated gain or loss in reader ICC with registered PV. Excellent reader ICC can coexist with strong differences in features extracted from different image sources. ICC uncertainty is broad for some features because only 14 patients contribute independent resampling units.

All four **shape features** (VoxelVolume, SurfaceArea, Sphericity, Elongation) have median raw-versus-registered changes **exactly zero**, bootstrap CIs **[0, 0]**, source rank ρ **1.000** and paired ICC difference **0**. This matches the locked unchanged two-reader tumor masks and is the expected technical negative control, not new biological validation.

## Technical reproducibility

- Computation: [`ci/mri_p0_source_paired_patient_bootstrap_ci.py`](ci/mri_p0_source_paired_patient_bootstrap_ci.py)
- Automatic test/figure generator: [GitHub Actions #41207344436](https://github.com/kimtk94/Codex/actions/runs/41207344436)
- Artifact `hcc-mri14-source-14-patient-bootstrap-ci-and-icc-delta-figures`, ID **13044742330**, 90-day retention. Contains actual source-based 10-feature effect CIs, 10 ICC difference CIs, 140 patient×feature source-change rows, two real data-driven figure PNGs and metadata JSON.
- Repository reference snapshot: [source feature CI CSV](HCC_MRI14_SOURCE_PAIRED_BOOTSTRAP_10_FEATURE_FROZEN_20261031.csv) and [ICC delta CI CSV](HCC_MRI14_SOURCE_PAIRED_BOOTSTRAP_10_ICC_DELTA_FROZEN_20261031.csv).
- Seed and bootstrap resample counts are fixed. Exact source SHA verification and CSV patient/sample shape guards must pass before inference; automated negative fixture test PASSED. The 95% simple percentile bootstrap is a small-sample descriptive uncertainty method, not a comprehensive inferential calibration.

## Manuscript claim and strategy after this stage

**Track A methods:** technically **GO for descriptive source robustness** and two-reader reliability. Real quantitative figure panels are now available. A methods-focused HCC MRI reproducibility manuscript remains conditional on independent anatomical registration review, source/software reproducibility, external image-methods validation and literature novelty; do not market `n=14` as broad standardization. Optionally extend to registered-source (rather than historical raw-PV-only) binWidth/voxel-spacing factorial after locking interpolation strategy.

**Track B biological:** clinical **HOLD**. Qualified 14-person ART/registered-PV anatomy reviewers, exact MRI HCC pre-therapy timing and index lesion → GDC RNA tissue identity have not been established. Patient case-ID/aliquot barcode matching alone is not sufficient. Do not execute the locked 3 MRI features × 4 Hallmark scores = 12 tests.

**Decision:** Source sensitivity with bootstrap uncertainty supports studying **measurement transportability and phase processing dependence**, but current evidence does not support MRI–RNA pathway association, drug effect, survival, prognosis or patient-level clinical utility. `HCC-12/13/14 PARTIAL`; `HCC-17/20 PENDING`; `MRI_RNA_12_tests=NOT_EXECUTED`, **S0**.
