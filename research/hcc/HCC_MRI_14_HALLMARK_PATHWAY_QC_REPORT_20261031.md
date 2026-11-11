# HCC MRI — 14 TCGA primary-tumor Hallmark pathway scores and RNA-only QC

**Data snapshot 2026-10-31 KST**. Primary study state: S0 (technical feasibility). Molecular association with MRI **NOT performed**.

## Primary auditable evidence

- [Actual GitHub GDC + official GMT run #100](https://github.com/kimtk94/Codex/actions/runs/41086269950): source-verified GDC STAR-Counts 14/14, official Hallmark 50-set **MSigDB human v2025.1.Hs** GMT fetched, four a priori pathways scored with **14/14 PASS**, no failed patients or nonfinite scores.
- Official source: https://data.broadinstitute.org/gsea-msigdb/msigdb/release/2025.1.Hs/h.all.v2025.1.Hs.symbols.gmt
- **Exact official GMT SHA-256**, now pinned in code: `f22066af72e215ccb7b89d88e492c07e1eef17534c2ca7b0f9902cfecbbdd8e9`.
- [Immutable sample-level four-score CSV](HCC_MRI_14_MSIGDB_HALLMARK_RANK_SCORE_20261031.csv): **14 sample rows**, gene mapping counts, expression technical QC and NOT_ASSESSED clinical eligibility. No full RNA matrix or broad full-GMT contents were committed.
- [Locked analysis-plan commit before any molecular score execution](HCC_MRI_RNA_PREOUTCOME_HALLMARK_SAP_V1.md). Fixed: **4 pathways × 3 PV imaging features = 12 primary tests**. Biology/image correlations NOT run yet.

## RNA measurement and gene-set QC

- Four gene sets and exact official membership: HALLMARK_HYPOXIA **200**, HALLMARK_ANGIOGENESIS **36**, HALLMARK_EPITHELIAL_MESENCHYMAL_TRANSITION **200**, HALLMARK_GLYCOLYSIS **200**. All mapped genes: **100%** in each of 14 samples.
- GDC STAR-Counts originals verified by exact file byte size/MD5 for 14/14. GENCODE v36: **60,660** unique ENSG gene IDs/sample; **19,962** protein-coding ENSG rows; **19,938** distinct protein-coding symbols after handling **24** duplicate gene-name rows by locked maximum TPM convention.
- Scoring is **custom sample-wise unweighted mean percentile of within-sample rank of log2(1+TPM_unstranded), minus 0.5**, NOT a claim that R `singscore`, GSVA or ssGSEA were run. The rank procedure handles tied expression values by average rank. Each case independent of other case values in scoring, with fixed official gene sets.
- Scores have positive nonzero between-patient spread, no missing gene-set genes, sample clinical eligibility NOT_ASSESSED. This is not a tumor purity, batch, gene expression differential analysis or biological significance result.

| Hallmark pathway | Score min | Median | Max |
|---|---:|---:|---:|
| Hypoxia | 0.155759 | 0.178834 | 0.216760 |
| Angiogenesis | 0.082635 | 0.176246 | 0.256695 |
| EMT | 0.076392 | 0.141471 | 0.204149 |
| Glycolysis | 0.171078 | 0.198021 | 0.240300 |

## Descriptive *RNA-only* redundancy/site QC — not MRI-RNA tests

Spearman correlations computed solely among four RNA pathway scores (n=14), **without any image features, outcome labels or inferential p-values**:

| RNA pair | Spearman rho | Interpretation |
|---|---:|---|
| Hypoxia vs Angiogenesis | 0.930 | Strong co-variation, don't claim independent biological mechanisms |
| Hypoxia vs EMT | 0.912 | Strong co-variation |
| Angiogenesis vs EMT | **0.982** | Near-redundant pathway scores in this small cohort |
| Hypoxia vs Glycolysis | 0.670 | Moderate/high |
| Angiogenesis vs Glycolysis | 0.622 | Moderate/high |
| EMT vs Glycolysis | 0.574 | Moderate |

Descriptive technical-QC checks: raw gene-count total vs Glycolysis score Spearman rho ≈ **−0.516** (does not prove technical confounding). Patient source-site code TSS (not full center/scanner identity): **BC n=4, DD n=3, G3 n=7**. Angiogenesis median score BC ≈0.1188; DD ≈0.2134; G3 ≈0.1856, indicating potentially important sample-composition, TSS/batch or biological differences. These numbers are **not** a multicenter batch correction or proof of site effect.

## Locked hypothesis and manuscript claims

- Primary MRI source PV phase, largest rater1 tumor per patient (A10Y = tumor3). Two-reader reproducibility verified for 10 features, 8 pass conservative ICC/bootstrap/LOO; only 3 nonredundant candidate primary MRI predictors chosen **before** any observed MRI-RNA association results: `original_firstorder_Entropy`, `original_glcm_Contrast`, `original_firstorder_InterquartileRange`.
- Primary family: 4 pathway rank scores × 3 image features = **12** two-sided, pre-specified patient-level Spearman tests, with a single BH-FDR family across 12. p-values, effect sizes and q-values **not yet calculated**. Tumor volume is a predeclared sensitivity/confounder, not a fourth primary feature.
- Before permitting associations: expert image ROI and index lesion review, clinical MRI/tissue chronology, final eligible n (not 14 by assumption), tissue purity/batch QC, and explicit methodological signoff. Caution: EMT and angiogenesis reflect stroma/immune mixing in bulk tumor RNA.
- High RNA score correlation does not invalidate BH reporting across the fixed 12 but **prevents treating distinct pathway p-values as independent biological validations**; report overlap and consider restrained mechanism language.
- Current state: **HCC-16 = PARTIAL** (expression and scores technically validated, tumor purity/TSS/method cross-check pending). **HCC-19 = PASS_TECHNICAL** for internally version-locked primary analysis plan, **not external registered-study preregistration**. **HCC-17 and HCC-20 = PENDING**. Manuscript ceiling **S0**, even with 14 RNA score-QC-passed *candidates*.

## Reproduce / next

- `research/hcc/ci/mri_gdc_hallmark_rank_score_qc.py`: sample-level original RNA file + official GMT SHA verification, gene mapping, custom mean rank score.
- `research/hcc/ci/mri_hallmark_rna_only_redundancy_qc.py`: score-only pairwise correlation, raw count/detected gene QC, TSS medians; no image input.
- Fix live runs to official GMT SHA and frozen GDC file hashes; only re-download source data when specifically warranted, not on each PR.
- Next hold-points: resolve G3 ROI anatomy and G4 chronology, verify tumor RNA purity and TSS/batch, test different MRI native vs resampled texture (IBSI), and only then move to original primary family (n dependent) without adding extra outcome-driven tests.
