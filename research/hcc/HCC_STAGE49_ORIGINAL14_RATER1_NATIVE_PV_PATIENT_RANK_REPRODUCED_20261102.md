# HCC Stage49 — original native PV rater1-only patient Spearman rank (n14) source verified

**Date 2026-11-02 KST.** Actual success: [GitHub Actions #41448904879](https://github.com/kimtk94/Codex/actions/runs/41448904879), **SUCCESS**; final artifact **13143686363**, ZIP SHA-256 `4f2aa835efce0e417a62ae1e07467b6c9b0fe27c6d53175392be5c8b330c693a`.

## Original source and reproducible arithmetic

- Source original full PyRadiomics v3.1.0 **14 patients × 2 original masks × 10 original radiomic features**, all original native PV versus 3mm binWidth25, original 28-row paired feature values from [GitHub Actions #41161863748](https://github.com/kimtk94/Codex/actions/runs/41161863748), original artifact `13027382220` named `hcc-pv-3mm-native-vs-resampled-14x2` (original artifact ZIP SHA256 `7838588956db579211479c87f681a7e35bbee39f982ce6cb53e02b38fe0aab2d`).
- Exact internal original 28-row CSV member SHA-256: `053c31f44eae435dce5a31a9b8785dcd4ff6f11768dedd5e243511d5db2c1318`.
- **28/28 original source patient-rater rows**, 14/14 frozen selected tumor labels (including `TCGA-BC-A10Y` tumor #3), all **10 original native/resampled feature family means** reproduced against frozen source to rounding tolerance ±0.000002.
- GLCM Contrast original patient-rater1 measured percentage changes exactly crosschecked against `HCC_MRI_PV_14_NATIVE_3MM_ROI_VOLUME_AND_PRIMARY_FEATURE_CHANGE_20261031.csv`; one original PV image, one selected index lesion and one rater1 mask per internal patient.
- One original venous MRI and original expert primary index mask per external `OpenSwissHCC v2` patient, 59/59 unique case identities from source `HCC_EXTERNAL_OPENSWISSHCC_V2_59_INDEX_PATIENT_GLCM_NATIVE3MM_FROZEN_20261101.csv` [source Actions #41221356861](https://github.com/kimtk94/Codex/actions/runs/41221356861).
- Spearman calculated as Pearson on deterministic average-tie ranks, after fixed source processing; 4,000 paired-patient bootstrap resamples with fixed seeds and leave-one-patient-out (LOO) diagnostics. **No MRI image redownload or radiomics reextraction**.

## Key results: distinguish rater1 from reader-mean

| Paired original HCC PV GLCM Contrast pre/post 3mm | Independent patients | Spearman rho | 4,000-patient-bootstrap 95% percentile interval |
|---|---:|---:|---|
| TCGA-LIHC internal original **rater1 only** | 14 | **0.810989010989** | **0.39365499–0.98642534** |
| TCGA-LIHC internal original **rater2 only** | 14 | **0.881318681319** | Not computed for rater2 |
| TCGA-LIHC internal **two-reader mean original feature value** | 14 | **0.850549450549** | Not computed for two-reader mean |
| Independent OpenSwissHCC external original venous primary mask | 59 | **0.940794856809** | **0.88375260–0.96586585** |

- Internal rater1 LOO rho range: **0.7637363–0.8956044** (13 remaining patients in each LOO analysis).
- External n59 LOO rho range: **0.9376788–0.9508444** (58 remaining patients).
- Internal original **`TCGA-BC-A10Y`** had largest absolute pre/post rank displacement: **6 rank positions**, original thick through-plane spacing **10.8mm**. This is a sensitivity/review flag, **not a retrospective clinical exclusion**.
- Observed external-minus-internal rater1 rho difference **0.12980585** (original output computed internal-minus-external **−0.12980585**). **NO between-cohort formal significance test, equivalence test or scanner-causality inference** was conducted; internal n14 has broad bootstrap uncertainty.
- The earlier frozen **n14 0.850549** was a **two-reader-averaged original feature** rank, **not** rater1-only. Its exact numeric reproduction from the 28 source rows is independently verified, as are all ten old two-reader means.

## Scientific interpretation and original thesis claim correction

The supported observation is **large preprocessing-induced feature magnitude shifts with nonuniform patient-rank preservation**. External original n59 shows relatively high preserved rank rho~0.941 while internal source rater1 n14 only rho~0.811 (reader2 rho~0.881; reader-average rho~0.851). Thus a blanket claim of invariant patient order across all HCC MRI cohorts or rater masks is **not supported**.

Higher between-patient rank correlation in external n59 does not mean a particular scanner has superior imaging performance, that preprocessing improved clinical predictions, or that the cohorts are exchangeable. Original underlying native acquisition thickness, image contrast, segmentation masks and sample sizes differ. Intra-rater reproducibility is not a test-retest MRI scan acquisition.

**Revised candidate methods paper title:**
*"Magnitude Drift and Heterogeneous Rank Preservation After MRI Voxel Resampling in Two HCC Imaging Cohorts: A Source-Verified Radiomics Methods Analysis."*

This is a **post-results exploratory sensitivity analysis**, not a preregistered confirmatory analysis. Stage48 DOI/title/year metadata crosschecks 6/6 successful, but full-text close prior-art novelty remains pending.

## Thesis stage decision and remaining 3 categories

**Methods thesis direction CONDITIONAL GO, submission HOLD.** Stage49 independently completes the **M1/reader1-only rank source calculation** task. Other M1 requirements remain: fully document original native acquisition/mask/parameter protocol comparability, quantitative influence of slice thickness and ROI volume, prevent unfair pooling of n14/n59, and source-specific negative controls.

**M2:** independent qualified abdominal radiologist image/selected index-lesion contour review; if unavailable, explicitly restrict claims to computational sensitivity under published source masks rather than new anatomy.

**M3:** full-text Methods/Supplement direct HCC MRI reproducibility/resampling prior-art gap, beyond the current 6 DOI/title/year checks. No claim that generic preprocessing sensitivity or 3mm voxel grid is novel.

**Original MRI×RNA biological research remains HOLD/STOP**, selected index lesion→GDC RNA tumor portion unproven, timing prior to all relevant HCC treatment unproven, clinically eligible n NOT_ASSESSED, **0/12 MRI–RNA tests**, claim ceiling **S0**.

## Frozen machine-readable outputs

1. `stage49_rater1_14_native3mm_patient_rank_evidence.csv`: patient ID, frozen index lesion, original native/resampled exact GLCM Contrast feature, rank of each, absolute rank displacement, original source run and S0 gate.
2. `stage49_all10_native3mm_reader1_reader2_mean_spearman.csv`: 10 features, separate rater1/rater2/two-reader mean rank rho, independently replayed original means.
3. `stage49_original14_reader1_59_original_rank_summary.json`: exact source and artifact hashes, confidence intervals, LOO, source gates.
4. `stage49_source_reader1_nativePV_patient_rank_report.md`.

Script: `research/hcc/ci/mri14_stage49_native_rater1_spearman.py`; workflow `.github/workflows/hcc-stage49-original-native-reader1-spearman.yml`.
