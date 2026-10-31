# HCC Radiomics × RNA-seq — Public cohort research

## Start here (required for every continuation)

- **CURRENT RESEARCH DECISION V2 (2026-10-31):** [HCC_RESEARCH_STRATEGY_V2_GATE_REDESIGN_20261031.md](HCC_RESEARCH_STRATEGY_V2_GATE_REDESIGN_20261031.md) — **P0 MRI mask/phase source-space dispute and MRI-before-treatment + same-lesion RNA** are the blocking gates; CT-A/B numerical source PASS is only nonblocking methods evidence. Clinical GO withheld, twelve MRI–RNA associations not run.

- **2026-10-31 scientific direction reset and STOP/GO gates:** [HCC_RESEARCH_DIRECTION_RESET_20261031.md](HCC_RESEARCH_DIRECTION_RESET_20261031.md) — clinical MRI–tissue pairing first; CT mask rescue second; IBSI CT A nonblocking.
- **Master verification standard and manuscript significance/claim rubric:** [HCC_VERIFICATION_AND_PUBLICATION_FRAMEWORK.md](HCC_VERIFICATION_AND_PUBLICATION_FRAMEWORK.md)
- **27 live evidence checkpoints:** [HCC_VERIFICATION_LEDGER.csv](HCC_VERIFICATION_LEDGER.csv)
- **Parallel GitHub Actions batch: clinical / purity / MRI-RNA identity / readiness:** [HCC_PARALLEL_ACTION_EVIDENCE_BATCH_20261031.md](HCC_PARALLEL_ACTION_EVIDENCE_BATCH_20261031.md)
- **Expanded 5-job evidence pipeline: official LiverHccSeg expert-reader metadata + 14-case source-drift safeguard:** [HCC_FIVE_PARALLEL_EVIDENCE_AND_DRIFT_QC_20261031.md](HCC_FIVE_PARALLEL_EVIDENCE_AND_DRIFT_QC_20261031.md)
- **Official IBSI-1 CT Configuration A independent 5/5 + PyRadiomics v3.1.0 4/4 official-reference PASS (not CT B–E/IBSI-2):** [verified CT-A report](HCC_IBSI1_CT_CONFIG_A_VERIFIED_20261031.md) · [frozen source/values JSON](HCC_IBSI1_CT_CONFIG_A_OFFICIAL_BENCHMARK_20261031.json) · [immutable regression](ci/mri_ibsi1_ct_a_frozen_result_qc.py) · [4-job PASS run](https://github.com/kimtk94/Codex/actions/runs/41186059566). HCC-18 remains PARTIAL; clinical HCC eligibility and MRI–RNA analysis remain blocked.
- **Official IBSI-1 ten-feature digital phantom 10/10 PASS + IBSI-1/2 identical CT source QC (NOT CT preprocessing):** [full verified methods and results](HCC_IBSI1_TEN_FEATURE_AND_CT_DUAL_SOURCE_VALIDATION_20261031.md) · [10-feature values CSV](HCC_IBSI1_TEN_FEATURE_PHANTOM_RESULTS_20261031.csv) · [CT source hash JSON](HCC_IBSI_CT_OFFICIAL_SOURCE_MANIFEST_20261031.json) · [verified GitHub Actions #214](https://github.com/kimtk94/Codex/actions/runs/41179519399)
- **Official IBSI-1 3D phantom independent GLCM and real PyRadiomics 5.32448 benchmark:** [IBSI1 official source report](HCC_IBSI1_OFFICIAL_PHANTOM_GLCM_BENCHMARK_20261031.md) · [verified 5-job PASS #202](https://github.com/kimtk94/Codex/actions/runs/41173010049)
- **Further 168-cell GLCM binWidth × voxel spacing assay, original ICC source reproduced:** [HCC_MRI_14_GLCM_FACTORIAL_BINWIDTH_SPACING_REPORT_20261031.md](HCC_MRI_14_GLCM_FACTORIAL_BINWIDTH_SPACING_REPORT_20261031.md) · [PASS run #185](https://github.com/kimtk94/Codex/actions/runs/41170599536)
- **Real 14×2 native-vs-3mm radiomics sensitivity and unexpected GLCM numeric shift:** [HCC_MRI_PV_14_NATIVE_VS_3MM_SENSITIVITY_REPORT_20261031.md](HCC_MRI_PV_14_NATIVE_VS_3MM_SENSITIVITY_REPORT_20261031.md) · [successful run #173](https://github.com/kimtk94/Codex/actions/runs/41161863748)
- **6-job source acquisition heterogeneity gate (PV voxel resolution, published 1.5T/contrast, native 10.8mm outlier):** [HCC_MRI_14_ACQUISITION_HETEROGENEITY_REPORT_20261031.md](HCC_MRI_14_ACQUISITION_HETEROGENEITY_REPORT_20261031.md) · [frozen original 14 PV voxel spacings](HCC_MRI_14_PV_NATIVE_SPACING_QC_20261031.csv) · [study contrast/field-strength](HCC_MRI_14_PUBLISHED_FIELDSTRENGTH_CONTRAST_20261031.csv) · [verified run #164](https://github.com/kimtk94/Codex/actions/runs/41160511643) · [latest verified full live run #158](https://github.com/kimtk94/Codex/actions/runs/41158329125) · [verified run #147](https://github.com/kimtk94/Codex/actions/runs/41156497628)
- **Two independent tissue-purity source checks (DNA ABSOLUTE vs CPE):** [HCC_MRI_14_CROSSMETHOD_PURITY_VALIDATION_20261031.md](HCC_MRI_14_CROSSMETHOD_PURITY_VALIDATION_20261031.md)
- **Actual 14-person GDC treatment, specimen day and pathology slide prescreen:** [HCC_MRI_14_CLINICAL_TREATMENT_ELIGIBILITY_AUDIT_20261031.md](HCC_MRI_14_CLINICAL_TREATMENT_ELIGIBILITY_AUDIT_20261031.md) · [14-patient clinical evidence CSV](HCC_MRI_14_GDC_CLINICAL_TREATMENT_GATE_20261031.csv)
- **Locked MRI–RNA Hallmark 12-test analysis plan (PRE-ASSOCIATION):** [HCC_MRI_RNA_PREOUTCOME_HALLMARK_SAP_V1.md](HCC_MRI_RNA_PREOUTCOME_HALLMARK_SAP_V1.md)
- **Real RNA 14-sample Hallmark score QC, source hash and redundancy findings:** [HCC_MRI_14_HALLMARK_PATHWAY_QC_REPORT_20261031.md](HCC_MRI_14_HALLMARK_PATHWAY_QC_REPORT_20261031.md) · [14×4 scores CSV](HCC_MRI_14_MSIGDB_HALLMARK_RANK_SCORE_20261031.csv)
- **Actual MRI PV 14-person imaging/reader QC:** [HCC_MRI_14_PIXEL_AND_RATER_QC_RESULTS_20261030.md](HCC_MRI_14_PIXEL_AND_RATER_QC_RESULTS_20261030.md)
- **Actual 14-person two-reader PyRadiomics ICC, 95% CI and leave-one-out:** [HCC_MRI_PV_PYRADIOMICS_ICC_14_VALIDATION_20261030.md](HCC_MRI_PV_PYRADIOMICS_ICC_14_VALIDATION_20261030.md) · [machine-readable 10-feature ICC/CI/LOO](HCC_MRI_PV_RATER_ICC_14_FEATURE_STABILITY_20261030.csv)
- **Actual MRI 14-person primary-tumor GDC RNA numeric QC:** [HCC_MRI_14_GDC_STAR_NUMERICAL_QC_RESULTS_20261030.md](HCC_MRI_14_GDC_STAR_NUMERICAL_QC_RESULTS_20261030.md)
- **Immutable source GDC UUID/MD5 file list:** [HCC_MRI_14_GDC_PRIMARY_TUMOR_RNA_FILE_MANIFEST_20261030.csv](HCC_MRI_14_GDC_PRIMARY_TUMOR_RNA_FILE_MANIFEST_20261030.csv)
- **Proposed pre-outcome patient index lesion IDs:** [HCC_MRI_14_PREOUTCOME_INDEX_LESION_SELECTION_20261030.csv](HCC_MRI_14_PREOUTCOME_INDEX_LESION_SELECTION_20261030.csv)
- **G3 MRI source-mask phase verification and manual reviewer roster:** [HCC_G3_IMAGE_REVIEW_AND_PHASE_LOCK.md](HCC_G3_IMAGE_REVIEW_AND_PHASE_LOCK.md) · [HCC_G3_PATIENT_IMAGE_REVIEW_QUEUE.csv](HCC_G3_PATIENT_IMAGE_REVIEW_QUEUE.csv)
- **Scientific hypotheses, cohort design, and methods:** [HCC_RADIOGENOMICS_PROTOCOL_20261030.md](HCC_RADIOGENOMICS_PROTOCOL_20261030.md)
- **CI script enforcing evidence and claim ceilings:** [ci/validate_research_ledger.py](ci/validate_research_ledger.py)

Important: Always read the framework **and** ledger first. PASS_METADATA/PASS_TECHNICAL applies only to what was tested. “Qualified paired cohort,” statistical significance, biomarker validity, independent replication, and clinical utility are distinct higher stages.

## Baseline verified (2026-10-30)

| Track | Verified to date | Still not established |
|---|---|---|
| TCGA-LIHC CT × tumor RNA | 75 CT patients, 73 case+RNA barcode-linked candidates | CT tumor lesion ROI; clinical eligibility; raw RNA expression QC |
| TCGA-LIHC LiverHccSeg MRI × tumor RNA | 17 MRI metadata matches; **14 HCC tumor mask NIfTIs with nonzero voxels** and tumor RNA file links | Actual MRI image–tumor mask affine/overlay, pretreatment timing, full RNA expression QC |
| CT × MRI × RNA | 2 same-patient barcodes | Same lesion and imaging timepoint; not an independent cohort |
| TACE prognostic imaging | WAW-TACE / HCC-TACE-Seg are two separate clinical benchmark datasets | No paired tumor RNA; no clinically validated new prognostic model |

**CRITICAL series distinction:** The historic patient-level CT review P1=20 is superseded. **Zero** patients have an explicitly PV-labeled CT and liver-only mask referencing that *same CT series UID*. The 20 cases had those labels/organ masks on different CT series. Moreover, liver-only segmentation **never counts as HCC tumor ROI**. Use the same-series review queue.

Latest end-to-end public-data CI evidence (all four jobs PASS):
https://github.com/kimtk94/Codex/actions/runs/41057407936

## Study roles

1. **MRI molecular feasibility pilot**: 14 mask voxel-QC-passed candidates. Only progress to pathway association after actual image–mask registration, sample/timing QC, frozen expression pipeline. n=14 does not support a high-dimensional ML biomarker claim.
2. **CT molecular expansion**: 73 metadata candidates. Require pretreatment contrast CT, lesion segmentation and tumor RNA to qualify effective n. CT tumor ROI presently unresolved.
3. **TACE clinical benchmark**: only for separately predeclared overall survival/censoring comparison using WAW-TACE and HCC-TACE-Seg. Not molecular validation.
4. **Cross-modality**: two case-ID overlaps are descriptive feasibility, not independent or same-lesion validation.

## CI and evidence

Actions → HCC Public Cohort Audit. On pull requests, GitHub Actions runs offline fixtures plus evidence ledger schema/claim guards only. Live TCIA/GDC/IDC and LiverHccSeg NIfTI remote audits run via **workflow_dispatch** (select the feature branch) or on the weekly schedule after merging to main; crossmodal job runs only after both live audits succeed. This avoids public Zenodo HTTP 429 rate limits from repeated documentation commits.

Metadata outputs include CT source-series, corrected CT series review queue, GDC primary tumor file lineage, MRI segmentation metrics × RNA barcodes, real NIfTI mask CRC/nonzero voxel QC, and triple patient overlap. This pipeline does **not** commit DICOM, RNA matrices, protected records, or raw image pixels. GitHub action artifacts expire after 30 days.

Run ledger CI manually in clone:
    python research/hcc/ci/validate_research_ledger.py
    python research/hcc/ci/validate_research_ledger.py --offline-test

## Existing Google Drive exploratory notebooks

- [Public HCC research Drive folder](https://drive.google.com/drive/folders/1YVSssXSTn8S2Bau3ji7vhs33y5jnKxnZ)
- HCC_Public_Radiomics_Model_Starter.ipynb: CNN **starter only**, not a trained/validated model.
- HCC_TCIA_External_Validation_Starter.ipynb: external validation **starter only**, no independent test result.

## Primary public sources

- [LiverHccSeg v1.1 MRI](https://doi.org/10.5281/zenodo.8179129)
- [TCIA TCGA-LIHC](https://www.cancerimagingarchive.net/collection/tcga-lihc/)
- [HCC-TACE-Seg](https://www.cancerimagingarchive.net/collection/hcc-tace-seg/)
- [WAW-TACE](https://zenodo.org/records/12741586)
- Study-quality sources and comparator DOI links are indexed in the master verification standard.


## Next execution: source-pixel PV overlay pilot

The new code `research/hcc/ci/mri_pv_pixel_overlay_audit.py` generates 3-plane PV MRI–tumor mask overlays and numerical image/ROI QC from *real* NIfTI files. It is **not** the same as header geometry and it is not expert approval.

The optional workflow `.github/workflows/hcc-mri-pv-pixel-overlay-pilot.yml` supports `source_run_id` and `max_cases` (2-case safe pilot, then 14). It reuses the archived MRI tumor-mask QC CSV from a successful live audit, rather than querying GDC again. **New GitHub workflow_dispatch files usually need to exist on the default branch before manual UI execution becomes available.** PR #228 remains unmerged; until merged, use a local authorized runner or keep the pilot pending. The referenced CI artifact expires after 30 days, so update the source run ID as needed.

Artifacts: `mri_pv_image_mask_pixel_qc.csv`, `mri_pv_image_mask_pixel_qc_summary.json` and patient-labeled three-plane PNG review images. These are **reviewer aids**, not image/ROI expert certification. Original NIfTI and RNA counts are not committed or uploaded as Actions artifacts.

The `research/hcc/ci/mri_gdc_file_manifest.py` script prepares exact TCGA-linked GDC STAR-Counts tumor RNA `file_id`/associated aliquot barcodes and expected MD5/size; multiple tumor files per patient stay unresolved rather than arbitrarily choosing an aliquot. **No RNA counts have been downloaded.**

## Latest actual data QC: MRI tumor/reader and GDC unstranded STAR counts (2026-10-30)

- Real PV MRI source pixels, mask geometry, 3-plane overlays: 14/14 technical candidate pairs pass, including the **largest tumor3 for TCGA-BC-A10Y** in [run #70](https://github.com/kimtk94/Codex/actions/runs/41068072486). Source tumor1 QC run [#62](https://github.com/kimtk94/Codex/actions/runs/41065766643) alone was not the final proposed index-lesion selection.
- Liver containment and 2-reader tumor mask Dice for 14/14: Dice median 0.9016, range 0.8136–0.9606; minimum tumor-in-liver mask fraction 99.8778%; 1/14 with multiple tumor contours (A10Y), largest tumor3. [Run #65](https://github.com/kimtk94/Codex/actions/runs/41067136933). **Dice is not PyRadiomics feature ICC.**
- Exact GDC STAR-Counts files identified for all 14 primary tumor samples; MD5 and size verified against **the actual 14 source files**; 60,660 GENCODE v36 gene IDs/sample with consistent unstranded counts and TPM. No numeric corruption or preliminary library-size outlier flags. [Run #76](https://github.com/kimtk94/Codex/actions/runs/41069103398). Only metadata and QC retained; raw expression vectors are not archived in GitHub.
- **Evidence gates:** HCC-12 = PARTIAL (reviewer/anatomic+timing pending), HCC-13 = PARTIAL (feature ICC pending), HCC-15 = PASS_TECHNICAL (GDC RNA file and gene count integrity), HCC-16 = PARTIAL (normalization/gene sets/batch/tumor purity pending), HCC-17/20 = PENDING.
- **Manuscript claim ceiling remains S0**, not a qualified 14-person paired radiogenomics biological association cohort.
- Heavy public remote access is deliberately kept off PR checks to avoid rate limits. The one-off PR live jobs that established the above evidence were removed after recording; repeat explicitly when a new dataset version or QC reason requires it.

## Actual feature-level radiomics robustness — 2026-10-30

- [Live GitHub run #87](https://github.com/kimtk94/Codex/actions/runs/41074562055): 14 PV MRI patients, 2 rater segmentations for each selected index tumor, PyRadiomics 3.1.0 Original-only, ten a priori image features; extraction 28/28 PASS; ICC(A,1) patient bootstrap 95% CIs.
- [Leave-one-out GitHub run #90](https://github.com/kimtk94/Codex/actions/runs/41075577502): 8/10 features pass original ICC≥0.90, bootstrap CI lower≥0.75 and all 14 delete-one-patient ICC≥0.75. Sphericity 0.822 (bootstrap 0.350–0.952) and Elongation 0.727 (0.289–0.919) excluded from primary reader-reliability screen. This is *measurement reliability*, not a gene–image association.
- Exact version/feature table + limitations archived [here](HCC_MRI_PV_PYRADIOMICS_ICC_14_VALIDATION_20261030.md). Critical: large volume heterogeneity can inflate ICC; 3D MRI slice anisotropy, IBSI benchmark, alternative resampling, tumor chronology, clinical expert review remain open.
- HCC-13 and HCC-18 now have real supporting evidence but stay **PARTIAL**. HCC-17 qualified paired patients and HCC-20 biological correlations remain **PENDING**; HCC-19 internal test-family plan is now **PASS_TECHNICAL** (not external preregistration). Maximum manuscript claim **S0**.
- Heavy remote GitHub PR pilot jobs removed after successful audited run; PR CI retains deterministic offline tests only. Artifacts expire in ~30 days, permanent derived feature ICC values and source run evidence are in tracked Markdown/CSV.

## Most recent 14-person MSigDB source RNA score audit — 2026-10-31

- [Live source-verified RNA run #100](https://github.com/kimtk94/Codex/actions/runs/41086269950) PASS: 14/14 GDC tumor STAR files MD5 checked; official Hallmark v2025.1.Hs GMT SHA `f22066af72e215ccb7b89d88e492c07e1eef17534c2ca7b0f9902cfecbbdd8e9` **pinned**; full membership of Hypoxia 200, Angiogenesis 36, EMT 200 and Glycolysis 200 genes mapped 100% per sample. Scores reproducible and nonzero-variance.
- RNA-only QC flags very high pathway co-variation (Angiogenesis vs EMT Spearman rho 0.982; Hypoxia vs Angiogenesis 0.930), plus differences by TCGA tissue-source site code (BC/DD/G3). No independent pathway mechanism or clinical batch adjustment claim.
- **Primary analysis family is frozen before looking at image–RNA associations:** 3 preselected reproducible PV features (Firstorder Entropy, Firstorder InterquartileRange, GLCM Contrast) × 4 Hallmarks = 12 two-sided tests with one BH-FDR family. Image–RNA association code remains gated and **has not run**.
- Gate updates: HCC-16 = **PARTIAL** (numeric pathway scoring PASS; tumor purity/batch/clinical eligibility unresolved), HCC-19 = **PASS_TECHNICAL** for internal source-controlled plan, HCC-17/20 = **PENDING**, manuscript ceiling S0. See [research gate ledger](HCC_VERIFICATION_LEDGER.csv). Heavy remote pilot PR job removed after PASS; only offline/score-table QC remains in PR checks.

## Live clinical eligibility prescreen — 2026-10-31

- [GDC clinical/treatment/samples/slides run #111](https://github.com/kimtk94/Codex/actions/runs/41089216888): **14/14** exact TCGA-LIHC case and corresponding Primary Tumor sample found. 9/14 have multiple diagnosis records disagreeing on `prior_treatment=Yes/No`; 5/14 have only No reported. **Five** have explicitly Yes treatment start day at/before GDC relative RNA tissue collection day; requires source-based review, not automatic exclusion.
- GDC slide tumor-cell and tumor-nuclei estimates were present for all 14 but **not confirmed to represent the exact sequenced aliquot** and are not genomic purity. Patient-level linked slide `percent_tumor_cells` varies 50–100%; use only as a QC review flag.
- TCIA shifted image DICOM dates and GDC diagnosis-relative days cannot be directly aligned. The TCIA collection-level baseline-pre-surgical statement **does not establish untreated status for each MRI**. All 14 remain unqualified **candidate cases** pending authoritative pre-intervention MRI chronology and expert lesion-source review.
- HCC-14 = **PARTIAL** (clinical metadata screened), HCC-17 = **PENDING** (final eligible n unassessed), HCC-20 = **PENDING** (no RNA-image tests), claim ceiling S0. One-time live GDC API PR job removed after passing; deterministic fail-closed tests retained in PR CI.


## Independent 14-sample purity proxy cross-validation — 2026-10-31

- Actual [GDC ABSOLUTE DNA purity crosswalk run #121](https://github.com/kimtk94/Codex/actions/runs/41090891246): 13/14 frozen tumor RNA cases matched the *same 16-character TCGA tumor specimen* in official PanCancer Atlas ABSOLUTE. Median copy-number purity estimate 0.74, range 0.20–1.00; one case (TCGA-DD-A4NJ) without ABSOLUTE match. **Never label same specimen as same DNA/RNA aliquot.**
- Actual [Aran 2015 CPE supplement crosswalk run #128](https://github.com/kimtk94/Codex/actions/runs/41091879111): same tumor specimen matched **14/14**, historical CPE median 0.81565, range 0.4591–0.9763. No ABSOLUTE values were reported in this older supplement for these 14 cases, so do not conflate CPE with current GDC PanCanAtlas ABSOLUTE.
- Major disagreement: TCGA-G3-A3CJ ABSOLUTE 0.20 vs CPE 0.8806; TCGA-G3-A7M7 ABSOLUTE 0.58 vs CPE 0.836. Low-purity review cases: G3-A3CJ, DD-A4NH, G3-AAV3 under ABSOLUTE 0.5; DD-A4NH, G3-AAV3 under CPE 0.5. None excluded solely on method-dependent proxies.
- [Permanent 14-sample purity analysis and confounding interpretation](HCC_MRI_14_CROSSMETHOD_PURITY_VALIDATION_20261031.md) · [ABSOLUTE source CSV](HCC_MRI_14_PANCAN_ABSOLUTE_PURITY_PROXY_20261031.csv) · [CPE source CSV](HCC_MRI_14_ARAN2015_CPE_REFERENCE_PURITY_20261031.csv).
- HCC-16 stays PARTIAL. HCC-14 treatment chronology remains PARTIAL; HCC-17 qualified paired n remains NOT ASSESSED; HCC-20 image–RNA association remains PENDING and maximum manuscript claim S0. Offline CI prohibits silent sample substitutions and arbitrary clinical eligibility flags.


## Refinement: source treatment anatomy and ABSOLUTE call quality — 2026-10-31

- [Read the original 14-case treatment/quality source adjudication](HCC_MRI_14_ORIGINAL_TREATMENT_SITE_ADJUDICATION_20261031.md). In [live GDC Actions run](https://github.com/kimtk94/Codex/actions/runs/41155810208), 130 treatment rows contain 42 explicitly administered Yes entries. **Five patients** have some affirmative treatment start on/before GDC relative tissue collection, but only **four** have these dated treatments recorded under an HCC diagnosis context. The fifth, **TCGA-BC-A5W4**, has a dated surgical record explicitly at **Cecum / Appendix** (diagnosis `Not Reported`), not evidence of a treated HCC imaging lesion; its other undated therapy records still require review.
- [Ten source treatment rows with IDs/dates/diagnoses/anatomy](HCC_MRI_10_DATED_YES_TREATMENTS_SOURCE_20261031.csv) have been versioned. [No-network source anatomy review script](ci/mri_treatment_anatomic_context_review.py) classifies P0 4/P1 5/P2 5 and retains all **14 HOLD**. The original 5-person flag was for *any* prior intervention, not proven HCC-specific intervention.
- ABSOLUTE DNA `call status=called`, `solution=new` at all 13 source-matched cases, with one missing. **A3CJ's called ABSOLUTE 0.20 versus independent historical CPE 0.8806 remains an unresolved cross-method disagreement**, not proof of measurement accuracy or RNA purity.
- HCC-14 and HCC-16 remain PARTIAL; HCC-17 eligibility PENDING; HCC-20 original 12-image/RNA hypothesis tests still NOT RUN. S0 manuscript limit unchanged.


## Verified native-versus-3mm PV MRI PyRadiomics re-extraction — 2026-10-31

- **Actual 14 cases × 2 original raters, native and 3mm isotropic:** [GitHub Actions #173](https://github.com/kimtk94/Codex/actions/runs/41161863748), full paired live source image/mask extraction in two 7-case parallel jobs, source ICC 10/10 reproduced before computing 3mm technical sensitivity. **Zero imaging-to-RNA associations**.
- Both native and 3mm reader ICC points are ≥0.90 for 8/10 original features, but GLCM Contrast undergoes **77.1% median absolute within-patient relative magnitude change** and across-patient mean-feature rank rho **0.851**, despite high two-reader ICC (~0.967 in both conditions). First-order Entropy and InterquartileRange changes are much smaller (~0.69% and ~1.08%). This distinguishes **reader repeatability** from **acquisition-grid stability**.
- Frozen results: [ten-feature native/3mm ICC, Spearman rank and relative drift](HCC_MRI_PV_14X2_NATIVE_VS_3MM_FEATURE_REPRODUCIBILITY_20261031.csv) · [14-case ROI physical-volume and primary-feature change](HCC_MRI_PV_14_NATIVE_3MM_ROI_VOLUME_AND_PRIMARY_FEATURE_CHANGE_20261031.csv) · [complete methodological result](HCC_MRI_PV_14_NATIVE_VS_3MM_SENSITIVITY_REPORT_20261031.md).
- A10Y's original 10.8mm through-plane acquisition is still a **technical acquisition flag**; its 3mm interpolation cannot recover missing acquired spatial detail. Small AAV7 rater1 ROI volume shifts **−5.14%**, also a voxelization flag. **No subjects were excluded.**
- The precommitted 3 MRI features × four Hallmarks **12-test family remains unchanged** and blocked until HCC-14/17 clinical source eligibility and selected-lesion review. GLCM Contrast is marked **high interpolation sensitivity**, not optimized/removed based on RNA results. HCC-13/18 **PARTIAL**, HCC-20 PENDING; claim ceiling S0.
- Heavy MRI extraction is preserved in the workflow behind the **explicit** `workflow_dispatch.run_heavy_resampling=true` input to avoid repeating 14×2 image downloads on ordinary PRs. GitHub manual dispatch becomes available when the workflow exists on the default branch. Routine PRs run deterministic checks against the archived small CSVs. The full paired 28-reader table is available in run #173's time-limited artifact.


## HCC 14×2 MRI-only binWidth × voxel spacing factorial, official source verified (2026-10-31)

- Real [GitHub Actions #185](https://github.com/kimtk94/Codex/actions/runs/41170599536) PASS: **14 original PV MRI index lesions × two original rater masks × native/3mm grid × binWidth 12.5/25/50 = 168 PyRadiomics extraction cells**, four GLCM/firstorder features; original binWidth25 reader ICC **8/8** native/3mm baselines reproduced. **No MRI-RNA associations or eligibility auto-upgrades**.
- GLCM Contrast native fixed binWidth halved 25→12.5: median *absolute relative numeric change* **253.3%**, doubled 25→50: **65.2%** (on 3mm grid: **270.5%**, **68.1%**). Original reader ICC stays ~0.967 across all six conditions. In-grid patient mean Contrast rank rho relative to 25 remains ~0.996 (12.5) / 0.965 native (50) / 0.925 3mm (50), so **numerical and rank stability are different**.
- [Permanent 24 factorial cell metrics](HCC_MRI_14_GLCM_BINWIDTH_VOXEL_FACTORIAL_20261031.csv) · [14-case Contrast per-patient matrix summary](HCC_MRI_14_GLCM_CONTRAST_CASE_FACTORIAL_20261031.csv) · [full methods and scientific interpretation](HCC_MRI_14_GLCM_FACTORIAL_BINWIDTH_SPACING_REPORT_20261031.md). Full 112 case×reader×feature rows remain archived in run #185's artifact (time-limited).
- Literature-only/illustrative GLCM reference check is NOT a full IBSI phantom PASS. Official IBSI `ACUI` Contrast digital phantom reference differs for 3D:avg 5.32 vs 3D:mrg 5.12; PyRadiomics fixed bin-edge and voxel grid alignment differ from IBSI. **IBSI conformance NOT ASSESSED**, HCC-13/HCC-18 PARTIAL, HCC-14/17 clinical gate unresolved, HCC-20 unexecuted and S0 claim ceiling.
- Heavy image re-extraction remains opt-in `workflow_dispatch.run_glcm_factorial=true` after workflow becomes accessible on the default branch; everyday PR CI runs [frozen data guard](ci/mri_glcm_factorial_frozen_results_qc.py) without download. Retain precommitted MRI entropy/Contrast/IQR × 4 Hallmarks = 12 exploratory tests unchanged and blocked.


## Completed IBSI-1 OFFICIAL phantom numerical validation — 2026-10-31

- **Actual [GitHub Actions run #202](https://github.com/kimtk94/Codex/actions/runs/41173010049): PASS** for official source hash, independent pure-stdlib 13-direction GLCM original NIfTI, PyRadiomics v3.1.0 `original_glcm_Contrast`, frozen HCC cohort and claim guards, and all legacy HCC clinical/source jobs.
- The original official [IBSI-1 digital phantom](https://github.com/theibsi/data_sets/tree/master/ibsi_1_digital_phantom/nifti) has 5×4×4 voxels, ROI 74, 2×2×2mm spacing. Image SHA-256 `83773ac2a288aa93cf819a98eaf301c18d35d5876182ec9c18733184e2b7a83a`; mask SHA-256 `3032d340944b577b83bc559ea7ae9a6034b84633a840eff39570ec17aa1d6281`. Original repo commit `6da96021bc91faf4c0cb7fd7fa56a4225d2064a8`.
- Independent original **3D directional averaged ACUI Contrast = 5.324479993784631**, original **3D merged = 5.117647058823529**, matching separately published rounded IBSI 5.32 vs 5.12 reference values. **PyRadiomics v3.1.0 3D averaged = 5.32447999378463** with `binWidth=1, normalize=False, resampledPixelSpacing=None, symmetric GLCM, distances=[1], weightingNorm=None`; independent and software calculation agree to floating-point precision. No patient-specific MRI or RNA analyzed in this phantom run.
- Permanent [full methods and evidence report](HCC_IBSI1_OFFICIAL_PHANTOM_GLCM_BENCHMARK_20261031.md) · [machine-readable frozen source and values](HCC_IBSI1_OFFICIAL_PHANTOM_GLCM_VALIDATION_20261031.json) · [no-network regression tests](ci/mri_ibsi1_frozen_source_result_qc.py).
- **Scope: one IBSI digital phantom GLCM feature/3D average benchmark PASS, NOT full IBSI standardization certification**. Original HCC clinical PV MRI used different `binWidth=25`, normalized images and heterogeneous native voxel sizes; original 168-cell MRI setup sensitivity findings remain. HCC-13/HCC-18 **PARTIAL**, HCC-14/17 **HOLD/PENDING**, original 12 MRI-RNA analyses HCC-20 **NOT RUN**, claim ceiling **S0**.
- Official clone/live 5-job IBSI test is preserved as opt-in `workflow_dispatch.run_ibsi_live=true` for reruns, while ordinary PR CI uses frozen checked SHA/results regression to avoid unnecessary clone/compute. Branch-only workflow dispatch availability depends on GitHub default-branch workflow registration; do not claim a deployed scheduler.
