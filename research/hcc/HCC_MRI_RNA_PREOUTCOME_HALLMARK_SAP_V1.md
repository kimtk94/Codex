# HCC MRI × RNA — Pre-outcome Hallmark scoring and primary test-family lock

**Frozen before any MRI–RNA associations**, 2026-10-31 KST. PR #228 branch `feat/hcc-public-ci-20261022`.

## Source and exact analysis unit

- RNA: 14 TCGA-LIHC MRI patients, 14 distinct linked primary solid tumor GDC STAR-Counts files (file UUID, sample barcode, size, MD5): [immutable RNA manifest](HCC_MRI_14_GDC_PRIMARY_TUMOR_RNA_FILE_MANIFEST_20261030.csv).
- Imaging: PV MRI, one rater1 largest-volume index HCC tumor per patient defined **without looking at RNA**; TCGA-BC-A10Y uses tumor3. [frozen index-lesion manifest](HCC_MRI_14_PREOUTCOME_INDEX_LESION_SELECTION_20261030.csv).
- Each MRI feature has same-lesion rater2 measurement. Two-reader ICC validation [stored here](HCC_MRI_PV_PYRADIOMICS_ICC_14_VALIDATION_20261030.md).
- **These 14 are *technical candidates*, not yet eligible research participants.** Expert anatomical tumor ROI review and pretreatment MRI-to-tumor tissue relation not established; do not make biological significance claims before eligibility.

## Official gene-set snapshot — selected *a priori*

MSigDB v2025.1.Hs, human Hallmark, **exact 2025.1.Hs GMT file**, source URL:
https://data.broadinstitute.org/gsea-msigdb/msigdb/release/2025.1.Hs/h.all.v2025.1.Hs.symbols.gmt

Only four prespecified pathways, all directions represent higher RNA signature activity:
1. HALLMARK_HYPOXIA (hypoxic tissue response)
2. HALLMARK_ANGIOGENESIS (vascular signaling/stromal biology)
3. HALLMARK_EPITHELIAL_MESENCHYMAL_TRANSITION (EMT and ECM)
4. HALLMARK_GLYCOLYSIS (metabolic stress/reprogramming)

Important: Hallmark angiogenesis and EMT may reflect stromal content and tumor purity rather than tumor-intrinsic processes. No prespecified immune signature or TACE prediction model in this first test.

## RNA numerical normalization and score *specification*

1. GDC STAR-Counts UUID download via API, verify **expected exact file byte size and MD5**, gene IDs and sample barcode. No normal tissues, secondary aliquots, multiple files per patient or changed GENCODE gene model silently included.
2. Use GDC `tpm_unstranded` (not `unstranded` integer counts) as the input to *single-sample ranking*. TPM is already length-/library-normalized; never call it raw counts. Parallel counts used as a QC indicator only.
3. Restrict ranking universe to `gene_type == protein_coding`, valid ENSG IDs and nonempty gene symbols, and remove non-gene STAR QC rows. Gene-symbol conflicts must be resolved *deterministically* by **maximum TPM per symbol** (a conservative ranking rule for repeated aliases); log number of collisions. This collapse rule is explicitly *not* expression summation.
4. For each sample, calculate `log2(1 + TPM)`. Rank this vector with **average ranks for expression ties**, giving each gene a percentile rank `(rank-1)/(number_of_ranked_genes-1)`. For each of the 4 sets, score = mean rank percentile for matched genes minus **0.5**. This is a **custom unweighted mean-percentile-rank activity score** motivated by rank-based single-sample scoring, *not* the exact `singscore` package algorithm or `ssGSEA`. Ranks are within the sample, not learned from other samples, and no association target is used.
5. Require every set have ≥15 mapped genes and ≥70% mapped membership in **every** patient; otherwise **fail closed**. Record 50 sets in source, exact 4 gene sets, membership count, matched gene symbols, collisions, rank-universe size, per-patient score and raw count/TPM QC summary. Freeze source GMT **SHA-256** after first official download and enforce it on all subsequent executions.
6. Output summary score table only, no per-gene expression values or full genome matrices on GitHub artifacts. Check finite scores and nonzero between-patient score spread; caution that small variation can make correlations unidentifiable.
7. Report across-patient pathway score ranges and influence of source count and detection metrics; descriptive score correlations with library size/other scores are **QC**, not the research imaging–RNA association.

## MRI features and *frozen* prospective hypothesis family

Reader-stability screen (ICC(A,1) ≥0.90 and patient-bootstrap 95% lower ≥0.75 and every leave-one-patient-out ICC ≥0.75) yielded 8 of 10 reliable measured features before looking at gene scores. To limit multiple comparisons and redundant MRI features, select three **primary imaging hypotheses**:

- `original_firstorder_Entropy`: overall MRI signal heterogeneity.
- `original_glcm_Contrast`: local texture contrast, with potential dependence on slice anisotropy.
- `original_firstorder_InterquartileRange`: robust broad signal variability, not highly optimized.

The 4 pathways × 3 selected features define **exactly 12 primary two-sided association tests**. All 12 must be reported (positive and null). `original_shape_VoxelVolume` is a **volume covariate/adjustment and sensitivity**, not a fourth independent discovery feature. `original_shape_SurfaceArea`, Mean, Median and JointEntropy remain predeclared descriptive/secondary results only, not added to the primary FDR family post hoc. Exclude Sphericity and Elongation on prespecified reader-reliability grounds.

## Statistical *precommitment* — NOT AUTHORIZED TO EXECUTE YET

- First obtain G3 qualified radiologist MRI/ROI anatomical verification and G4 GDC-tumor relative pretreatment/time provenance with written per-patient inclusion/exclusion log. **HCC-17 final eligible n must be explicitly set**; cannot default to 14.
- If the final n ≥ 10 and only if gate requirements pass: exact 12 Spearman rank associations (two-sided) and individual effect size rho. For very small n/ties prefer permutation p values predeclared 10,000 label permutations (fixed seed); BH-FDR across all 12 tests, q<0.05 as *internally controlled exploratory association*, not clinical or causal significance. Do not swap primary features or pathways based on observed scores/p values.
- Give 95% effect CI using participant-level bootstrap with full selection-agnostic resampling, report missingness and failures. The small-n p-values cannot justify an optimized predictive MRI model.
- Sensitivity: leave-one-patient-out effect rho/CI; adjust or stratify by lesion volume when identifiable (minimal covariate degrees of freedom), report image acquisition/voxel thickness and potential tumor purity/batch confounding; multiple readers as measurement sensitivity only, not independent subjects.
- Independent cohort validation is required for replication. 2 CT/MRI patient overlaps are **not** external replication. Untested hypotheses remain pending regardless of technical scoring PASS.
- S0 manuscript-claim ceiling persists until eligible patient and biological validation gates passed. Significant association does not mean drug-response prediction, survival value, or causal molecular regulation.

## Source and methodological guardrails

MSigDB Hallmark 2025.1.Hs official 50-set GMT: https://data.broadinstitute.org/gsea-msigdb/msigdb/release/2025.1.Hs/
Single-sample rank-scoring conceptual reference: https://bioconductor.org/packages/release/bioc/html/singscore.html
GDC expression pipeline: https://docs.gdc.cancer.gov/Data/Bioinformatics_Pipelines/Expression_mRNA_Pipeline/

All scripts and their inputs are maintained in `research/hcc/ci/`, and all outcomes must be committed with checksums and GitHub run URLs.
