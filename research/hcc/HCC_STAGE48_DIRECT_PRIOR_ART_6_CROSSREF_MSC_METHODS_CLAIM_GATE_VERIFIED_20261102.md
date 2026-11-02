# HCC Stage 48 — direct prior-art novelty risk and MSc manuscript claim ceiling

**Date:** 2026-11-02 KST. **Reproducible actual CI:** [GitHub Actions #41446456712](https://github.com/kimtk94/Codex/actions/runs/41446456712) **SUCCESS**. Artifact `13141473910`, ZIP SHA-256 `eaf7cdb875b5cb175381098a82f29b69cc0d133ca108e3a6b51224858596703e`.

## Scientific direction: methods CONDITIONAL GO; finished thesis HOLD

The previously proposed TCGA-LIHC HCC MRI–RNA original lesion-level biological analysis remains HOLD: precise MRI-selected HCC index lesion→GDC RNA aliquot and scan-before-any-HCC-therapy source chronology **NOT_ASSESSED**, no qualified clinical denominator, 0/12 biological tests, biological/clinical claims ceiling **S0**.

The MRI-only methods direction has source-verified **14 TCGA-LIHC native PV reader1 patient measurements** and **59 independent OpenSwissHCC venous MRI measurements**. Each is original MRI native→3mm isotropic/GLCM Contrast binWidth25; n14 median absolute shift **74.8808%** (exploratory 4000-patient-bootstrap 95% CI **68.0073–88.6917%**), n59 **64.635863%** (prior source-frozen CI **56.753732–74.435888%**); the n59 native-to-3mm paired rank Spearman **0.940795**. An exactly matched **n14 reader1-only** rank Spearman has **not yet been independently derived**, even though an earlier two-reader-averaged n14 rank (0.8505) exists; these are not interchangeable.

No scanner/protocol equivalence, intervention, patient-matched test–retest MRI, prognostic/diagnostic external validation or causal resampling effect exists. These are two *independent source cohorts*, **not a pooled estimate or a proper matched external validation of a predictive model**.

## Six direct published comparators — bibliographic DOI, title and year 6/6 LIVE Crossref PASS

The Stage48 CI downloaded Stage47 original 73-patient patient-level artifact, checked separate denominators and per-patient claim ceiling, and verified each study DOI, title string and publication year from live Crossref. **This is not a full-text systematic literature search**; the scientific scope columns are human-curated from primary abstracts/publisher pages, not validated by Crossref metadata.

| Article, journal/year | Population / methods already done | Critical overlap / constraint |
|---|---|---|
| [Carbonell et al. *European Radiology* 2022, DOI 10.1007/s00330-021-08282-1](https://pubmed.ncbi.nlm.nih.gov/34564745/) | 55 liver MRI patients incl. 16 untreated HCC; true repeat scanning, inter-platform and inter-rater reproducibility | **Already establishes HCC MRI radiomics reproducibility**. Our study cannot claim first ever or true test–retest |
| [Koçak et al. *Diagnostic and Interventional Radiology* 2024, DOI 10.4274/dir.2023.232543](https://pubmed.ncbi.nlm.nih.gov/38073244/) | 50 glioma MRI patients with multiple source readers, two sequences; discretization bin-width and voxel-spacing resampling changed to assess ICC | **Already establishes preprocessing-driven feature robustness as a research question**. Our contribution would be HCC-specific lesion-locked rank-vs-magnitude descriptive behavior, not a new principle |
| [Cao et al. *Journal of Magnetic Resonance Imaging* 2023, DOI 10.1002/jmri.28725](https://onlinelibrary.wiley.com/doi/10.1002/jmri.28725) | HCC MRI recurrence nomogram using B-spline 3×3×3 mm voxel resampling | **3 mm preprocessing itself is not novel**. Prognostic outcome model distinct from our measurement endpoint |
| [Zwanenburg et al. *Radiology* 2020, DOI 10.1148/radiol.2020191145](https://pmc.ncbi.nlm.nih.gov/articles/PMC7193906/) | IBSI feature computation, standardization and reference phantoms | IBSI check is required QC and not original contribution |
| [Santinha et al. *European Radiology* 2025, DOI 10.1007/s00330-024-11093-9](https://link.springer.com/article/10.1007/s00330-024-11093-9) | ESR radiomics study practice recommendations | Reporting of binning, resampling and uncertainty is mandated best practice, not novelty |
| [OpenSwissHCC, *Scientific Data* 2026, DOI 10.1038/s41597-026-08506-3](https://www.nature.com/articles/s41597-026-08506-3) | Public 132-subject annotated liver MRI collection, 63 HCC; our frozen index venous 59 HCC subset | Use of a newly released dataset is not automatically original; HCC-specific preprocessing finding must be distinguished from dataset paper |

## Explicit frozen claim decisions

**Prohibited** (9 source-inconsistent / non-original assertions from the Stage48 matrix) include: "first HCC MRI radiomics reproducibility study"; "3mm voxel resampling invented"; "preprocessing impact not previously studied"; "exact externally replicated scanner effect"; "prospectively preregistered"; "validated clinical prediction/prognosis"; "MRI index lesion confirmed to be aliquot source and untreated"; "genuine test–retest MRI"; and "new independent expert anatomical review for all 59 lesions."

**Source-supported limited descriptive claims**: (a) patient-level original native PV MRI voxel-grid perturbation changed GLCM Contrast magnitude in separate n14 and n59 HCC-labeled cohorts; (b) external n59 GLCM Contrast ranks retained Spearman rho 0.940795 under paired within-image perturbation. None is proof of clinical utility or causality.

**HOLD**: finished/thesis submission ready. **CONDITIONAL GO**: methods topic as a *candidate*.

## Research question / methods SAP v0.2 (POST-RESULTS LOCK, NOT preregistration)

Working research question: "In two source-verified, independently acquired HCC venous MRI cohorts, how does isotropic 3mm voxel resampling alter original gray-level feature magnitudes and preserve within-cohort patient order, conditional on original segmentation and acquisition geometry?"

Primary current descriptive endpoint: one source-selected primary HCC lesion / patient, original native portal-venous T1 MRI with provided mask, fixed binWidth25 GLCM Contrast, B-spline image and NN ROI resampling, compare native vs 3mm; patient-level median absolute relative change. Report its bootstrap percentile CI and leave-one-patient-out robustness, **not** a prespecified confirmatory hypothesis test.

Separate secondary endpoints: Spearman patient-rank native vs 3mm using **the exact same rater1-only** internal and primary-mask external data; four locked feature-family sensitivity summaries (Contrast, JointEntropy, first-order Entropy and IQR); native voxel spacing and ROI physical volume descriptive associations with rank instability, without p-hacking or causal language. Avoid inflated n from 28 reader observations or 354 preprocessing rows; patient is unit.

This SAP is written after inspecting Stage46/47 results and thus **not** a prospective registered analysis plan. Future changes must be explicitly versioned; new independent data would be needed for genuinely prospective confirmation.

## Three remaining categories, and strict completion criteria

1. **Direct methodology/statistical comparability**: internally reconstruct native-PV **reader1-only** original 14-case paired-feature rank from successful original 14×2 extraction artifact `hcc-pv-3mm-native-vs-resampled-14x2` (Actions #41161863748, artifact `13027382220`); verify original 14 patient IDs / mask identity; no new MRI download. Retain original n59 rank 0.940795 from Stage46. Clarify original scanner/registration mask source, source intensity normalization and loss of through-plane MRI resolution. Do not conduct a pooled inferential effect test without a new design.
2. **Independent expert anatomical review**: qualified abdominal MRI reviewer signs off original image phase, tumor index identity and mask anatomy. Without review, limit to computational feature drift on the published masks, explicitly noting uncertainty of anatomical correctness. Only 3/59 external index lesions have published second-reader masks; this is not new reader adjudication.
3. **Full-text novelty assessment**: verify full methods/appendices for Carbonell 2022 HCC precision, Cao 2023 HCC 3mm, Koçak 2024 MRI resampling and newer HCC-specific preprocessing/feature rank papers. Log exactly what comparable numeric results, ranks, scanner handling and mask robustness they reported. Novelty may remain limited; do not claim method invention.

**GO**: supported technical description and limited exploratory results. **HOLD**: thesis submission/narrative originality pending these 3 gates. **STOP**: qualified MRI–RNA biological tests and clinical utility claims without source-authoritative clinical pairing.

## Source and evidence paths

Script `research/hcc/ci/mri14_stage48_prior_art_methods_gate.py`, workflow `.github/workflows/hcc-stage48-prior-art-methods-gate.yml`. Source archive frozen in successful GitHub Actions [Stage47 #41444439116](https://github.com/kimtk94/Codex/actions/runs/41444439116), 73 original per-patient source rows. Stage48 archived outputs: `stage48_direct_prior_art_source_comparison.csv` (six comparators), `stage48_thesis_claim_permission_and_rejection.csv` (12 claims, 9 prohibited), `stage48_thesis_novelty_clinical_S0_gate.json`, `stage48_live_literature_metadata_check.json`, and `stage48_master_thesis_literature_gap_and_protocol_gate.md`.
