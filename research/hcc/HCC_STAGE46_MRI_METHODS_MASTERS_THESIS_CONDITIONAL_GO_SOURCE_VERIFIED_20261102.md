# HCC Stage46 — MSc MRI-only radiomics methods thesis decision (SOURCE-VERIFIED)

**Date:** 2026-11-02 KST. **Actual CI:** [GitHub Actions #41443483288](https://github.com/kimtk94/Codex/actions/runs/41443483288) **SUCCESS**. Artifact **13141880559**, ZIP SHA256 `b75d319c2e7d482234a8df816575e57f3bcb6e9fbe3964508da3eb9254b68b4b`. Source script: `research/hcc/ci/mri14_stage46_mri_methods_thesis_evidence.py`.

## Executive scientific decision

**CONDITIONAL GO: a standalone HCC MRI radiomics preprocessing/measurement-stability MSc methods thesis.** The original proposed **MRI×RNA radiogenomics biological association remains HOLD**, with **0/12 predeclared tests** and clinical/biological claim ceiling **S0**.

Suggested defensible working title: **"Preprocessing-Induced Magnitude Shifts and Patient-Rank Preservation of Hepatocellular Carcinoma MRI Radiomic Features: A Two-Cohort, Source-Verified Methods Study"**.

The two-corpus design can support **descriptive technical reproducibility of the analysis pipeline / sensitivity of extracted features**, not actual *test–retest scan repeatability*, diagnostic/prognostic model validation, scanner effect causality, clinical decision thresholds, or MRI–RNA tissue biology. IBSI benchmark quality is a separate mathematical implementation assurance.

## Actual evidence from independent frozen source data

| Measured evidence | Internal LiverHccSeg TCGA-LIHC | External OpenSwissHCC v2 |
|---|---|---|
| Independent subjects | 14 (TCGA IDs) | 59 (sub IDs) |
| MRI and original segmentation image source | 14/14 original PV↔DICOM 3D, 1,095 slices source linked | 59/59 original native venous image+expert mask, 354 extraction rows |
| Rater reproducibility | 14×2 masks, 10 original features, **8/10** conservative ICC(A,1) screen PASS | Only **3/59** selected index tumors have a reader-2 mask; median Dice **0.904796** |
| Native→3 mm / binWidth 25 GLCM Contrast absolute shift median | **86.594%** [95% bootstrap **76.400–97.878%**] for *registered ART/PV source arm* | **64.635863%** [95% patient bootstrap **56.753732–74.435888%**] for *original native venous source* |
| External primary patient rank ρ | Do not manufacture comparable estimate from different feature table | **0.940795** |
| Direction and magnitude of external per-patient shift | Not assessed on same raw source design | **59/59 positive** and **55/59 >20%** |
| External patient leave-one-out median absolute shift | Not applicable | **64.249–65.207%** |
| Source identity vs clinical pairing | GDC RNA case+aliquot hierarchy 14/14, *not* exact tumor source | Independent cohort; no RNA pairing attempted |

The n=59 independent-original-mask comparison shows **a substantial shift in absolute GLCM Contrast with relatively preserved cross-patient ranking**, a valid methodological nuance. It does **not** imply a diagnostic classifier works, that a specific preprocessing pipeline improves prediction, or that a feature is biologically meaningful. GLCM Contrast within the internal 14×2 mask feature table had ICC(A,1) **0.9668**, showing reader-mask stability in that cohort; reader ICC and spatial resampling stability are different estimands.

**Critical mismatch:** internal n14 used a *registered arterial↔portal venous image source arm* whereas external n59 used native independently acquired portal venous series. The two shifts must **NOT** be pooled as a common-effect meta-analysis, nor called a strict equivalent-protocol external replication. No formal between-cohort hypothesis test is supported by the current estimand construction.

Four precomputed n59 original native→3mm (binWidth25) features (4,000 independent-patient bootstrap draws):

| Feature | Median absolute change (95% CI), % | Patient Spearman ρ | Internal ICC(A,1) |
|---|---:|---:|---:|
| GLCM Contrast | **64.64** (56.75–74.44) | 0.941 | 0.9668 |
| GLCM JointEntropy | **4.73** (3.77–6.46) | 0.939 | 0.9849 |
| First-order Entropy | **2.72** (1.66–3.93) | 0.978 | 0.9874 |
| First-order InterquartileRange | **3.64** (2.67–5.37) | 0.977 | 0.9891 |

**Population accounting:** 14+59=73 distinct source subjects, but two different technical measurement questions. The 354 extracted source condition rows are *repeated measurements within 59 independent patients*, not 354 persons. The three external original reader-2 contours do not support a 59-subject ICC.

## Relationship to established scientific literature (novelty caution)

- [IBSI 1 reference standard, Radiology 2020](https://pmc.ncbi.nlm.nih.gov/articles/PMC7193906/): standardized definitions and phantom/clinical CT benchmarks for quantitative radiomics. Following IBSI is essential QC, **not methodological originality by itself**.
- [IBSI official reference guide](https://theibsi.github.io/ibsi1/): record exact preprocessing choices, image resampling interpolation, gray-level discretization, mask resampling, feature naming, PyRadiomics version and reference configuration.
- [OpenSwissHCC dataset, Scientific Data 2026](https://www.nature.com/articles/s41597-026-08506-3): recent 132-patient resource, 63 HCC cases, 140 annotated lesions, and different phase/ROI availability. Our venous HCC index-lesion source cohort is 59 independent subjects, not 132/63 all cases.
- [MRI preprocessing and feature reproducibility 2026 literature example](https://pmc.ncbi.nlm.nih.gov/articles/PMC13178426/): prior studies already evaluate resampling, intensity discretization and reproducibility. **Do not claim that the general question of radiomics preprocessing stability is novel**. The potential defensible contribution is the lesion-locked HCC venous cross-cohort measurement finding, reproducible source QC, segmentation-reader and resampling-axis distinction, and rank-vs-magnitude dual behavior. Search for closer HCC-specific prior art before final title.

## Required remaining work for a methods-based MSc thesis (3 independent categories)

**M1 — Harmonized estimand and analysis-plan lock (P0, automatable via GitHub Actions).** Fix *exact* input arm (prefer original/native PV in both cohorts, not registered PV in one), PyRadiomics 3.1.0 version, intensity normalization, mask source/reader, size-based index lesion, 3 mm interpolation and binWidth25. Recompute internal n14 using identical native-PV source and preserve its previous registered-arm result separately. Then use paired patient-level summary, rank ρ and 4,000-bootstrap intervals; do NOT pool groups by default. Predeclare primary GLCM Contrast and four-feature secondary sensitivity family before interpreting harmonized differences.

**M2 — Anatomy/segmentation validity (P0, human expert or bounded method-only limitation).** Obtain independently signed source MRI / lesion orientation and ROI review for selected cases, at least stratified or key representative cases and all clinical-anatomy claims. If unavailable, limit paper to algorithmic source-mask/feature stability under originally published segmentation; explicitly note no new expert adjudication, 3 external paired reader masks only, and do **not** present broad segmentation reliability.

**M3 — Novelty and thesis writing validation (P0, largely automatable).** Perform a close-prior-art table around HCC MRI preprocessing/voxel resampling and source-cohort generalization. Define the negative result as scientific content: the difference between numerically stable ranks and unstable magnitudes. Use patient-level bootstrap, LOO, source image voxel anisotropy, ROI volume, and negative controls. Report cohort differences descriptively with no scanner causality. Prepare a methods-first proposal with clear nonclinical claim ceiling.

### Conditions for thesis GO / HOLD / STOP

- **GO (submission candidate)** only when M1 source-protocol comparability & numerical results pass, M2 reviewer evidence or strictly delimited non-clinical QC claims documented, M3 literature novelty and narrative independently reviewed, and exact reproducible CI output locked.
- **HOLD (current):** M1 unharmonized input arms, M2 independent image anatomy approval missing, M3 prior-art novelty unadjudicated. Current experimental evidence is complete enough to choose a *candidate direction*, not to assert finished thesis.
- **STOP for MRI–RNA biological claims:** no source-authoritative MRI before all relevant HCC therapy and no exact selected index tumor-to-GDC sequenced tissue linkage. Maintain clinical patient n **NOT_ASSESSED**, 0/12 biology tests, S0.

## Next practical GitHub Action

**Stage47:** harmonized *native* PV cohort experiment: use pinned 14-case DICOM↔PV image source identity as input, reread original native PV masks, compute n14 native/binWidth25 vs 3mm/binWidth25 with the same settings as the already frozen external n59 source experiment, verify every selected lesion's patient, source hashes, geometry/ROI and paired patient denominator, then compare only descriptive estimands. Run via GitHub Actions, not local server deployment. Before a costly recomputation check whether a truly identical n14 native-PV feature table already exists in prior artifacts. Preserve existing n14 registered-arm estimates as distinct.
