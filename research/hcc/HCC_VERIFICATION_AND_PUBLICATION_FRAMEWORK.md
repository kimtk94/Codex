# HCC Radiomics x RNA-seq — Verification & Manuscript Claim Framework

Version: 1.0 | Baseline: 2026-10-30 (KST) | Owner: research/hcc | Canonical companion: HCC_VERIFICATION_LEDGER.csv

> OPERATING RULE: A green GitHub Actions job is evidence that its asserted checks ran, **not** that clinical eligibility, a biological hypothesis, or an external prediction claim was established. Never promote a metadata match into an eligible paired patient without image, ROI, timing and RNA QC.

## 0. How to use this file in every future research session

1. Read this document and HCC_VERIFICATION_LEDGER.csv **before** starting any new radiomics/RNA analysis; read HCC_RADIOGENOMICS_PROTOCOL_20261030.md for scientific scope.
2. Obtain the most recent GitHub Actions run SHA, date, conclusion, individual job statuses, produced artifacts, and source dataset version/checksum. GitHub PR #228 is a *feature branch*, not merged main.
3. Update ledger status only if the gate-specific evidence has been newly reviewed. Save output path, run ID, commit SHA, and patient-level denominator/exclusions. GitHub artifact retention is 30 days: persist non-sensitive summaries/manifests durably before expiration.
4. If an upstream gate fails, do not run downstream inferential steps as if valid; report the failure and re-evaluate the maximum permissible claim level.
5. Freeze the hypothesis family, features, imaging phase, expression normalization, eligibility criteria, statistical plan and sensitivity analyses **before inspecting radiomics–RNA association estimates**. Record the frozen Git commit.
6. At the end of each task, report: VERIFIED, UNVERIFIED, FAILED/BLOCKED, NEXT ACTION, manuscript-claim ceiling, provenance (link/commit/run), and whether new results change the decision.

Status vocabulary: PASS_METADATA (identity/file lineage only); PASS_TECHNICAL (tested file or code properties); PARTIAL (only some required dimensions checked); PENDING (not checked); BLOCKED (required evidence missing or failure); NOT_APPLICABLE (must justify in ledger). These are *evidence statuses* and do not imply statistical significance.

### Scope and analysis units

- A. MRI molecular feasibility pilot: TCGA-LIHC LiverHccSeg v1.1 HCC tumor MRI segmentation × GDC tumor RNA-seq. n=14 *tumor mask NIfTI technical candidates*, final eligible n = NOT ASSESSED. Pilot association only, not predictive ML.
- B. CT molecular expansion: TCIA TCGA-LIHC CT × GDC tumor RNA. n=73 *barcode-linked metadata candidates*, **no source-CT-linked tumor-lesion ROI verified** in the audited IDC collection. Final eligible n = NOT ASSESSED.
- C. CT + MRI + RNA: n=2 same-patient barcode crosswalk (TCGA-DD-A4NF, TCGA-DD-A4NJ), not proven same lesion, scan phase, or study timepoint. Not independent validation.
- D. TACE survival benchmark: WAW-TACE and HCC-TACE-Seg are **clinically related but not RNA-paired cohorts**. Use only for separately specified clinical model benchmarking; never describe as molecular replication.
- Analysis unit = **patient**, not number of scans, series, lesions, segmentation raters, raw reads or RNA files. For multiple lesions, predefine index lesion and aggregation or use patient-cluster methods.

## 1. Verified baseline and the known traps

| Check | Verified observation on 2026-10-30 | Actual evidence | Important limitation |
|---|---|---|---|
| TCIA CT inventory | 75 distinct TCGA-LIHC CT patients; 777 CT series | HCC Public Cohort Audit 41057407936 | TCIA published mixed-modality cohort size ≠ CT subjects |
| CT × GDC case ID | 73 of 75 CT patients have linked tumor STAR-Counts file metadata | Run 41057407936, tcga_rna_overlap_candidates.csv | Not 73 qualified CT tumor ROIs |
| GDC file lineage | 73/73 file-linked TCGA sample barcode type 01 | tcga_gdc_rna_file_lineage.csv | Tumor purity, RNA QC, temporal eligibility unknown |
| CT phase | 25 explicit portal venous labels, 13 generic venous labels, 35 neither | tcga_ct_phase_patient_prescreen.csv | DICOM SeriesDescription ≠ radiologist phase confirmation |
| CT SEG | 95 liver-organ SEG series map onto CT source UIDs, 36 patients | IDC source-UID and code meaning query | Organ segmentation is NOT tumor ROI |
| Pathology SEG exclusion | 142 IDC TIL annotations are pathology, **not CT tumor lesions** | tcga_idc_segmentation_metadata.csv | Earlier substring “tumor” false positive was fixed |
| CT series vs patient | **Zero** patients have *the same exact CT series* with both explicit PV label and linked liver-only SEG; 20 have both somewhere within the same patient | tcga_hcc_same_series_review_queue.csv | Historical P1=20 queue was patient-level and is superseded |
| MRI metadata | 17 LiverHccSeg patient barcodes matched to GDC primary tumor RNA metadata | verified Zenodo XLSX and GDC | 17 are not tumor-segmented cases |
| MRI tumor segmentation | 14 distinct patients in HCC metrics with a real non-AppleDouble tumor NIfTI ZIP member | verified Zenodo XLSX + bounded ZIP directory | ZIP file presence only |
| MRI voxel smoke test | One NIfTI tumor mask per 14 patients passed CRC, header, geometry and nonempty voxels | 41056977638; 41057407936; MRI voxel QC CSV | No original MRI voxel comparison or visual ROI quality check |
| Cross-modality | 2 patients share CT + tumor-mask MRI + tumor-RNA barcode | 41057407936 crossmodal job | No temporal or lesion equivalence |
| Inferential science | No version-locked tumor MRI+RNA gene-expression feature matrix; no radiomics pathway regression, FDR or external molecular replication | As of current pipeline | **No statistical or clinical significance claim yet** |

Source run: https://github.com/kimtk94/Codex/actions/runs/41057407936
Tracked PR: https://github.com/kimtk94/Codex/pull/228

## 2. Workflow Go/No-Go gates: ordered, independently auditable

For every gate write (a) patient denominator and exclusions, (b) test/evidence, (c) status, (d) whether downstream inference is allowed, (e) output filename. A manually reviewed gate needs reviewer/date and case-level decision.

| Gate | Required verification point | Proposed pass criterion / failure response | Permitted claim after gate |
|---|---|---|---|
| G0 source/provenance | Public license/allowed reuse, dataset version, DOI, checksum, reproducible download | All inputs have source, version and checksums; corrupted input stops workflow | Data source reproducibility |
| G1 patient identity | TCGA patient barcode ↔ imaging ↔ RNA file, no duplication or normal-only files | Exact normalized case-level overlap; no one-to-many inflation; audit all exclusions | Metadata linkage only |
| G2 biospecimen lineage | STAR-Counts file-associated aliquot barcode code 01, not merely some tumor sample anywhere on the case | File-specific sample link and stable RNA file ID; resolve ambiguous/multiple aliquots | File-level tumor RNA provenance |
| G3 image+lesion | Original MRI/CT exists, correct modality, phase, organ, axial geometry, usable lesion ROI | NIfTI/DICOM image and lesion mask aligned in shape, affine/origin/orientation/spacing or documented transform; expert overlay review; non-empty lesion mask; indexed lesion and reader | Technical image/ROI feasibility |
| G4 timing/eligibility | Imaging pretreatment status; tumor resection/biopsy relation, clinical context, multiple scans | Treatment history verified; source-aware handling of TCIA deidentified dates (NEVER direct calendar join); ambiguous cases flagged/excluded per frozen criteria | Clinical eligibility |
| G5 RNA numeric QC | Download counts, expression data type and gene namespace, sample ID, QC, stable gene mapping | No missing/unexpected samples; raw counts vs normalized units documented; sample-level outlier and library-size checks; zero/low count filter and treatment recorded | Molecular measurement feasibility |
| G6 final analysis sample | One linked patient → chosen phase/lesion/mask and tumor RNA file, plus relevant covariates | Frozen inclusion flow; one row per patient; n and missingness/exclusions explicit; multiple lesions clustered or indexed by predefined rule | **Eligible paired n** (not necessarily biologically significant) |
| G7 radiomics reliability | IBSI-compliant definitions, PyRadiomics/extractor version, fixed resampling/bin width, motion/voxel QC, feature stability | Compare feature values with IBSI reference, lock YAML, show inter-reader or perturbation ICC; propose ICC ≥0.75 as *study rule* for exploratory robustness and ≥0.90 for strong stability; report sensitivity to different values | Reproducible measured feature set |
| G8 pathway design | Choose a small fixed set (hypoxia, angiogenesis, EMT/ECM, metabolic) with exact MSigDB version and score method | Freeze gene sets, genes matched, sample normalization, pathway algorithm, family of feature–pathway tests in Git before associations | Prespecified hypothesis family |
| G9 primary association | Patient-level association with estimated effects, CI, uncertainty, BH FDR and covariate sensitivity | Predefine confirmatory family and primary statistic; for exploratory work q<0.05 within that defined family is “FDR-controlled exploratory signal”, not causal/validated; n=14 requires especially cautious uncertainty | Hypothesis-generating molecular association |
| G10 robustness | Leave-one-patient-out influence, rater perturbation, geometry/phase sensitivity, volume and clinical confounding | Direction and effect not driven by single outlier/rater/mask or a known scanner/volume batch; use bootstrap CI and report both pass/fail | Technically robust exploratory result |
| G11 biological replication | A **non-overlapping** patient cohort with MRI/CT lesion ROI and tumor RNA measuring same pathway, locked association direction and analysis | Same endpoint and assay semantics, genuinely distinct patients; effect and uncertainty replicated. Cross-modal checks are complementary and NOT identical-feature replication | Replicated biological association |
| G12 clinical value (only if proposed) | Predictive endpoint, clinically meaningful baseline, discrimination+calibration+utility, independent test | External testing of a frozen model, without selection/refit on test data; report Δperformance CI relative to clinical model; outcome suitability and censoring handled | Potential clinical utility; **not deployment** |

Conditional fallback:
- G3 CT fails because only liver-organ mask available → CT molecular inference is BLOCKED, but MRI G3 may proceed.
- G3 MRI image-mask geometry fails → no MRI radiomics results until transform/registration evidence; do not “fix” silently.
- G4 cannot prove treatment ordering → restrict to cross-sectional radiogenomics and label timing unknown; do not call “pretreatment”.
- G5 RNA availability/QC fails → continue image-only technical benchmarking; no transcriptomic claim.
- G6 eligible paired n remains small (such as 14) → retain feasibility and effect-size/CI exploratory analysis; **no high-dimensional signature optimization or deep learning predictive claims**.
- G9 q fails or CI is wide → report null/inconclusive estimates, power limits and QC, not a positive association.
- G10 fails → unstable feature/association and no biomarker claim even if q<0.05.
- G11 absent → no “independently validated” biological biomarker claim.
- G12 fails (negative incremental model) → publish/report limited transferability and negative utility honestly; no clinical deployment claim.

## 3. Prespecified analysis discipline (proposal, not yet locked)

These are *candidate* rules to approve **before examining associations**; they are not thresholds prescribed by the comparison papers:

- Primary analysis: within MRI only, one patient per row. Consider 3–5 interpretable, segmentation-robust imaging features and 4–5 biological hypotheses; record the exact number of hypothesis tests. Radiomics feature selection based on observed RNA associations must not occur outside nested training or post-hoc candidate labeling.
- Choose Hallmark gene sets using versioned MSigDB: HALLMARK_HYPOXIA, HALLMARK_ANGIOGENESIS, HALLMARK_EPITHELIAL_MESENCHYMAL_TRANSITION, plus one or two prespecified metabolic programs (e.g. GLYCOLYSIS or FATTY_ACID_METABOLISM, depending on scientific hypothesis). Record release and overlap with expressed genes.
- Normalize RNA counts using a method appropriate to the measured GDC workflow; do not conflate raw STAR-count columns, TPM and log-normalized values. Fix gene ID conversion and pathway score method (GSVA/ssGSEA or other) before testing.
- Descriptives: missingness, tumor volume, slice thickness, acquisition field strength/phase, site, scanner and expression distributions; plot each candidate association and influential patients without cherry-picking.
- Primary effect: Spearman rho or standardized regression β with 95% CI; select one prespecified primary inferential method. If n=14, avoid multivariable models with many nuisance covariates; show a separate volume-adjusted sensitivity when estimable and honestly flag unidentifiable scanner/phase effects.
- Error control: Benjamini–Hochberg across the **complete prespecified primary feature × pathway family**; q < 0.05 = within-study FDR-controlled exploratory signal; 0.05 ≤ q < 0.10 may be labeled *suggestive only*, not statistically significant. Unadjusted p<0.05 alone never qualifies. Report exact effect, uncertainty, test count and missing patients.
- Robustness: report leave-one-out effect direction and range, patient-bootstrap percentile CI if appropriate, mask-reader sensitivity, tumor-size adjustment and any substantial acquisition sensitivity. Avoid blanket significance labels from post-hoc resampling with n=14.
- Clinical models only if justified by number of events and useful predictors. Model comparisons require clinical-only baseline and frozen external performance. For survival use time-to-event methods with censoring (C-index, calibration, and if appropriate time-dependent AUC), not MAE/R² on censored OS time.
- Stop leakage: split by patient and preserve index lesion per patient, nested/within-training feature selection, batch scaling, imputation and tuning; freeze held-out/external cases and only evaluate once. MRI and CT from the same person are *not* independent replication.
- No causal language from observational bulk RNA–radiomics correlations. Even q<0.05 does not imply therapeutic efficacy, immune therapy response, pathway regulation, or clinical utility.

## 4. Key published comparators: what exactly should be checked

### P1. Journal of Translational Medicine (2026), DOI 10.1186/s12967-025-07627-4
Title: Radiogenomics predicts immune microenvironment heterogeneity and response to combination immunotherapy in hepatocellular carcinoma.
Source: https://link.springer.com/article/10.1186/s12967-025-07627-4

- Literature facts: 994 patients in multi-omics integration; 11 scRNA samples; **41 TCIA contrast CT cases with RNA** used for imaging development; six independent institutional cohorts totaling **754** were used for downstream clinical validation. A two-gene immune-related signature KPNA2/SMG5 and four-feature SVM biomarker were reported.
- Results: an internal TCIA AUC of **0.992** (95% CI 0.972–1.000); 500-bootstrap mean AUC **0.899** (SD 0.086; bootstrap 95% CI 0.729–1.000). Reported response AUCs **0.720–0.829** in specified external retrospective therapy cohorts, with HR 1.415–1.890 in reported prognosis comparisons. These numbers pertain to *different endpoints and datasets* and may not be compared directly with pathway correlations in our study.
- Mandatory checkpoints we borrow: image segmentation provenance, patient-level RNA matching, feature robustness, biological rationale, independent downstream cohorts, calibrated uncertainty and clinically meaningful comparison. **Do not copy only its best AUC** as an expected performance threshold.
- Novelty guard: A generic 2-gene immune score or “CT predicts immune signature” is already published. Our candidate contribution is a pre-specified pathway hypothesis, transparent MRI vs CT feasibility/negative evidence and genuine robustness; without independent evidence label as exploratory.

### P2. Abdominal Radiology (13 Oct 2026), DOI 10.1007/s00261-026-05830-5
Title: Limited incremental value and cross-cohort transferability of CT radiomics for survival prediction after TACE in hepatocellular carcinoma.
Source: https://pubmed.ncbi.nlm.nih.gov/42867540/
- 221/233 WAW-TACE and 98/105 HCC-TACE-Seg technically eligible with pretreatment arterial/portal-venous CT; within-cohort clinical C-index **0.646** (WAW) vs clinical+radiomics **0.639**; HCC cohort **0.496** vs **0.495**. Incremental improvement was not supported.
- Frozen WAW-trained radiomics Top-K 5/10/15, externally tested without refitting, yielded C-index **0.463**, **0.535**, **0.528** (with reported 95% CIs). The full combined clinical+radiomics model was **not** externally validated.
- Mandatory checkpoints: distinguish repeated internal CV from externally **frozen** testing; compare added radiomics to clinical baseline, not just AUC/C-index >0.5; quantify stage/case-mix (e.g. BCLC), cohort acquisition/segmentation and outcome differences, missingness, and ΔC-index CI.
- Interpretation: a negative result is useful if error sources and limited generalizability are clearly reported. These TACE sets cannot constitute external tumor-RNA validation.

### P3. LiverHccSeg v1.1, Zenodo DOI 10.5281/zenodo.8179129
Source: https://zenodo.org/records/8179129
- Multiphasic TCGA-LIHC MRI with radiologist-supervised liver and HCC tumor segmentation, phase labels pre/art/pv/del and inter-rater comparisons.
- Our independent evidence: 17 MRI case IDs have tumor-RNA file barcode matches; 14 are on tumor segmentation metrics; **14/14** have ZIP true tumor NIfTI files with nonzero voxels when one mask is read per person.
- Next checkpoints: MRI source–mask **affine/shape/physical overlay**, rater agreement and tumor volume sensitivity, sequence comparability, acquisition spacing, treatment ordering. Prior reader agreement statistics **cannot replace** our own feature robustness evaluation.
- n=14 is *not* a validated predictive model dataset.

### Methods and reporting standards
- IBSI standardized definitions and radiomics software reference values: https://doi.org/10.1148/radiol.2020191145
- CLEAR (2023) radiomics reporting: https://doi.org/10.1186/s13244-023-01415-8 — source, segmentation readers, image resampling/discretization, reproducibility, leakage and patient flow.
- MSigDB hallmark collection: https://doi.org/10.1016/j.cels.2015.12.004
- TRIPOD+AI (2024), only if developing/reporting a clinical prediction model: https://doi.org/10.1136/bmj-2023-078378
- PROBAST+AI (2025), risk-of-bias appraisal if prediction model: https://doi.org/10.1136/bmj-2024-082505
- CLAIM (2024), only if AI medical imaging task is proposed: https://doi.org/10.1148/ryai.240300
These are complementary **reporting/bias/reference standards**, not universal statistical success thresholds.

## 5. Research significance & permissible manuscript claims by outcome

| Evidence grade | Requirements achieved | Permitted paper conclusion | Not permitted |
|---|---|---|---|
| S0 provenance and feasibility | G0–G2 and metadata/CRC checks only | Public cohort linkage and technical feasibility; a reproducible dataset inventory | 73 CT “molecular radiomics cases”, association, biomarker |
| S1 verified usable imaging | G3–G6, with imaging/ROI/clinical timing and expression QC | A qualified paired cohort; radiomics and RNA measurement feasibility; patient flow and failure analysis | Biological biomarker based on data availability alone |
| S2 reproducible descriptive discovery | G7–G8; effect/CI descriptions, potentially inconclusive tests | Hypothesis-forming radiogenomics relationships and sensitivity bounds | Confirmatory/causal or clinically validated claims |
| S3 internally robust exploratory signal | Prespecified family G9 (BH q<0.05) **and** satisfactory G10; effect and CI reported | FDR-controlled and segmentation/volume-robust **exploratory** association for that cohort | External replication, clinical prediction, causal mechanism |
| S4 independent biological replication | S3 + G11 nonoverlapping paired MRI/CT+tumor RNA evidence with aligned question | Replicated pathway-level radiogenomic association, restricted to validated populations/modalities | Universal CT↔MRI feature portability or therapeutic benefit |
| S5 clinical evaluation | S4 + G12 with clinical outcomes, comparator, calibration/utility and frozen independent testing | Clinical predictive *potential* in specified setting, with precise limitations | Deployment/clinical decision change without prospective impact evidence |

An exploratory p-value below 0.05 with no correction, failed ROI, post-hoc chosen feature, or absent reproducibility does **not** upgrade S2→S3. Conversely q≥0.05 with tight CI around negligible effect may support a carefully bounded negative conclusion, while wide CI is inconclusive and should not be framed as evidence of no association.

### Decision matrix for publication pathway
- **A: MRI G3–G8 passes, association robust (S3), independent cohort missing** → publish as methodological feasibility / exploratory pathway radiogenomics with n=14, explicit low power. Do not assert strong biological novelty or deploy predictive claims.
- **B: MRI image-mask quality passes but association remains null/inconclusive** → valuable reproducibility/QC feasibility or a *negative* pathway result if confidence bounds meaningfully constrain effect sizes; otherwise report underpowered pilot.
- **C: MRI mask alignment or sample identity fails** → repair or restrict technical report; no MRI-RNA inference.
- **D: CT 73 candidates can get expert-verified tumor masks and pretreatment scans** → expands actual paired n, possible same-modality CT study; recalculate eligibility *from scratch*, not 73 by default.
- **E: CT expansion yields independent, nonoverlapping reproducibility with same molecular question** → upgrade biological evidence if phase/method differences controlled; do not call cross-modal feature values equivalent.
- **F: WAW/HCC-TACE external OS model weak or no clinical incremental value** → report rigorous negative transferability evidence, not a clinically useful new model.

### Paper-grade output table & figures (required eventually)
- F1 cohort flow: original → CT/MRI → case RNA → tumor aliquot → CT/MRI + true tumor lesion mask → pretreatment → expression QC → final paired n, with per-reason counts.
- F2 imaging/ROI overlay QC panel: phase, geometry, tumor and liver contours clearly separated; blinded rater checks.
- F3 feature stability: per-reader ICC, spacing/volume sensitivity and feature distribution, no pseudo-replication.
- F4 pathway hypotheses: frozen gene-set membership and expression QC distributions; molecular score variation.
- F5 effect size and **95% CI** forest/scatter per prespecified pathway, BH q table, leave-one-out/sensitivity direction.
- F6 replication/transport: independent cohort or transparent “not available”; clinical-only baseline and frozen Δperformance if model developed.
- T1 clinical/acquisition/molecular characteristics and missingness; T2 cohort QC and exclusions; T3 full hypothesis family with negative/null estimates; Supplement: code, configs, exact feature dictionary, PR/commit SHA, sample eligibility map and provenance.

## 6. Immediate next steps, in this order

1. **MRI source-mask registration** (14 cases): inspect original image NIfTI per selected tumor mask, assert congruent affine/shape/orientation, and visually review overlay; flag multi-rater disagreement. A non-empty mask alone is insufficient.
2. Verify source archive licensing and acquisition-to-treatment provenance, and freeze actual 14-case or smaller denominator with explicit exclusion reasons.
3. Download *only* necessary TCGA tumor STAR-counts files to a controlled execution environment (Drive/Colab or permitted GitHub Action), validate raw/normalized column interpretation, mapping and RNA QC. Do not commit genomic matrices/raw images to Git.
4. Freeze imaging preprocessing, PyRadiomics/IBSI config, initial clinical covariates, primary biological pathways and primary multiple-testing family in a protocol commit.
5. Execute descriptive feature extraction and association sensitivity, report effect sizes, CI and **all** tested hypotheses whether significant or not.
6. Reassess if a larger independent CT tumor-ROI sample can be qualified; avoid repurposing TACE-only cohorts as tumor-RNA external replication.
7. Update this document + HCC_VERIFICATION_LEDGER.csv and CI test evidence after every gate. Do not convert previous status “PENDING” to “PASS” from another study’s publication.

## 7. Audit pointers

- Branch: feat/hcc-public-ci-20261022; PR #228: https://github.com/kimtk94/Codex/pull/228
- Final four-job CT+MRI+RNA crosswalk run (2026-10-30): https://github.com/kimtk94/Codex/actions/runs/41057407936
- Last MRI 14-mask nonempty voxel run: https://github.com/kimtk94/Codex/actions/runs/41056977638
- Source scripts: research/hcc/ci/{tcia_cohort_audit,tcga_rna_overlap_audit,gdc_tumor_lineage_audit,idc_segmentation_prescreen,ct_phase_prescreen,build_same_series_review,liverhccseg_mri_rna_audit,zenodo_nifti_zip_inventory,mri_mask_voxel_audit,crossmodal_case_audit}.py
- Saved artifact ZIPs are reproducible for a GitHub run but GitHub retention is 30 days; regenerate or archive summaries before expiry.
- Research numbers/grades apply to this observed snapshot; future GitHub run updates may revise counts. No statistical hypotheses have been tested as of this baseline.

## Verified MRI source phase / segmentation header update — 2026-10-30
- Live source-mask geometry run: https://github.com/kimtk94/Codex/actions/runs/41061027979
- 14 cases × five phase headers = 70 phase comparisons. PV 14/14 matching, ART 14/14, ART_PV 0/14 matching; PRE 13/14 and DEL 13/14. PRE/DEL exceptions both TCGA-BC-A10Y.
- Coordinates/shape of the original NIfTI phase compared with rater1 tumor1 mask; this is not a visual overlay nor clinical eligibility. Original MRI pixel arrays were not read during header audit. The implementation was subsequently upgraded to check **maximum field-of-view corner displacement in millimetres** at a 0.5 mm threshold; verify the latest CI run separately.
- Do not use art_pv.nii.gz with untransformed tumor masks in inference. Proposed PV primary and ART sensitivity analysis must be frozen before any RNA association; original MRI voxel and expert tumor overlay review remains pending.
- HCC-12 ledger changed from PENDING to PARTIAL with S0 claim ceiling unchanged. See [G3 image reviewer checklist](HCC_G3_IMAGE_REVIEW_AND_PHASE_LOCK.md) and [14-patient review roster](HCC_G3_PATIENT_IMAGE_REVIEW_QUEUE.csv).

## Infrastructure guard: remote public-data rate limits (2026-10-30)
- Initial full MRI header audit succeeded: 70 source phases scanned, with PV and ART mask affine matches for all 14 tumor-mask candidates. After many consecutive PR commits, Zenodo returned **HTTP 429 Too Many Requests** during a subsequent remote rerun. That was an API quota issue, not imaging QC failure.
- GitHub PR-triggered workflow now runs **offline tests and evidence-ledger guards only**. Live TCIA/GDC/IDC and Zenodo metadata/ZIP audits are reserved for deliberate workflow_dispatch runs or the weekly post-merge schedule on main. Crossmodal job depends on both live metadata jobs.
- Do not interpret a green *offline-only PR run* as revalidation of public API data. Cite the specific prior successful full-data run and retain sample-level evidence, version/checksum.
- The MRI image-mask geometric difference metric was strengthened to maximum physical FOV-corner displacement (mm), rather than mixed-unit affine matrix-element differences. Synthetic geometry regression tests use sufficiently large image FOV; the original 5-phase full-data audit and its documented limitations remain separately cited.

## Live source RNA-seq and representative tumor ROI QCs (2026-10-30)

This supersedes previous "RNA counts not downloaded" baseline statements **for technical integrity only**. All current findings must be read alongside their original dated baseline snapshot.

- **MRI selected index lesion:** 14/14 PV source-image and selected largest rater1 tumor mask pixel QC passed. The original 14-person run used rater1_tumor1 in all patients; **TCGA-BC-A10Y had three tumors and its tumor3 at ~740.19 mL was the largest, versus tumor1 at ~7.00 mL**. Separate original PV/tumor3 QC [run #70](https://github.com/kimtk94/Codex/actions/runs/41068072486) passed. The largest-lesion selection was proposed before any MRI-RNA association analyses, but after reviewing descriptive mask QC. It is **not** independent clinical lesion truth.
- **Rater evidence:** 14/14 corresponding rater1/rater2 largest-lesion mask pairs can be compared: Dice median 0.9016 (range 0.8136–0.9606); rater1 tumor-in-liver mask minimum fraction 0.998778. [Run #65](https://github.com/kimtk94/Codex/actions/runs/41067136933). Reader label identity, feature ICC, resampling and lesion selection sensitivity not yet verified.
- **RNA source files:** 14/14 exact file-specific primary tumor STAR-Counts UUID + aliquot barcode and MD5. Original GDC TSV contents **downloaded and checked** (not committed): **60,660 gene IDs in all**, GENCODE v36, valid unstranded raw integer counts and finite nonnegative TPM, TPM sum ≈1 million, library-size count median 49,185,211, no within-study 0.5×–2× median outlier flags. [Run #76](https://github.com/kimtk94/Codex/actions/runs/41069103398). Count-integrity gate HCC-15 PASS_TECHNICAL; RNA normalization, GSVA/ssGSEA method, purity/batch and pathway score HCC-16 PARTIAL.
- **Important ordering:** Descriptive QC and acquisition harmonization → clinical/expert image review → treatment/tissue chronology → frozen features and hypothesis family → pathway-score QC → exploratory biological effect/CI/FDR. No biological associations have been tested. Manuscript **S0** remains the maximum permitted level.
- Per-patient and file provenance in [MRI pixel/reader summary](HCC_MRI_14_PIXEL_AND_RATER_QC_RESULTS_20261030.md), [RNA numerical summary](HCC_MRI_14_GDC_STAR_NUMERICAL_QC_RESULTS_20261030.md), and [RNA source UUID+MD5 manifest](HCC_MRI_14_GDC_PRIMARY_TUMOR_RNA_FILE_MANIFEST_20261030.csv).

## Two-reader feature robustness update — 2026-10-30 (G7/HCC-13 and HCC-18)

- 14 patients × 2 independent tumor mask readers (28 segmentations) extracted with **PyRadiomics 3.1.0** on the same original PV MRI per patient. One index lesion per patient; TCGA-BC-A10Y uses selected tumor3 (largest rater1), not tumor1.
- Ten pre-RNA-outcome original-image features (shape 4, firstorder 4, GLCM 2), fixed `binWidth=25, normalize=True, normalizeScale=100, voxelArrayShift=0, resampledPixelSpacing=None, correctMask=False`. No LoG/wavelet, no silent mask correction; native anisotropic spacing retained.
- Two-way random absolute agreement **ICC(A,1)** with 500 patient-bootstrap 95% percentile CIs: 8/10 features have ICC≥0.90, Sphericity=0.82174 (bootstrap CI 0.34958–0.95241), Elongation=0.72746 (CI 0.28927–0.91937).
- Pre-outcome reader stability screen requires **ICC≥0.90, CI lower≥0.75, minimum leave-one-patient-out ICC≥0.75**. Eight features passed: Firstorder Mean/Median/Entropy/InterquartileRange; GLCM Contrast/JointEntropy; Shape SurfaceArea/VoxelVolume. Sphericity and Elongation fail the full screen.
- High reader agreement does **not** imply MRI scanner harmonization, reproducible patient biology, strong association, robust clinical prediction, tumor boundary correctness, or IBSI phantom agreement. Large between-patient tumor volume heterogeneity can inflate ICC; beware size confounding and related shape features. IBSI bin/resampling behavior differs from some PyRadiomics defaults.
- Upstream technical image/ROI and GDC numerical counts QC are PASS for the 14 technical candidates. **Clinical eligibility n remains NOT ASSESSED**; HCC-12, HCC-13, HCC-16, HCC-18 remain PARTIAL; HCC-17/19/20 remain PENDING. Manuscript claim remains **S0**.
- Evidence: [PyRadiomics and bootstrapped ICC GitHub run](https://github.com/kimtk94/Codex/actions/runs/41074562055), [leave-one-out ICC GitHub run](https://github.com/kimtk94/Codex/actions/runs/41075577502), [per-feature ICC/CIs and leave-one-out CSV](HCC_MRI_PV_RATER_ICC_14_FEATURE_STABILITY_20261030.csv), [full detailed interpretation](HCC_MRI_PV_PYRADIOMICS_ICC_14_VALIDATION_20261030.md).
- **Next**: expert review and timing eligibility; IBSI reference phantom, native vs resampled (and scanner/MRI phase) stability; version-locked biological hypothesis family and pathway-score distributions **before** evaluating any MRI–RNA association.

## RNA pathway-score and 12-test pre-outcome plan gate update — 2026-10-31

- Original 14 GDC Primary Tumor STAR-Counts files re-downloaded with GDC UUID+MD5 validation; a rank-percentile Hallmark score was successfully calculated for each of 14 patients and four pathways (Hypoxia, Angiogenesis, EMT and Glycolysis), **14/14 PASS**. Official human MSigDB v2025.1.Hs 50-set Hallmark GMT SHA-256 pinned as `f22066af72e215ccb7b89d88e492c07e1eef17534c2ca7b0f9902cfecbbdd8e9`. Membership matched 100% across all four sets, coding symbol ranking universe n=19938 with 24 duplicate gene-name rows resolved by max TPM. Source [GitHub #100](https://github.com/kimtk94/Codex/actions/runs/41086269950).
- This is a custom *sample-wise average within-sample logTPM percentile rank minus 0.5*, **NOT** running the singscore/GSVA/ssGSEA reference implementations. The method and precise 12 hypotheses were frozen in version control before any RNA-score computation. Source [locked SAP](HCC_MRI_RNA_PREOUTCOME_HALLMARK_SAP_V1.md).
- RNA-only descriptive QC: Angiogenesis vs EMT rho 0.982, Hypoxia vs Angiogenesis rho 0.930. TCGA TSS centers BC(4), DD(3), G3(7) have differing pathway medians. No inference/p-values, no MRI-feature associations; these indicate high pathway redundancy and likely clinic/sample composition confounding to investigate, not distinct replicated biological signals.
- Gate status: **HCC-16 PARTIAL** (scores valid but sample purity/site/batch and clinical chronology unresolved); **HCC-19 PASS_TECHNICAL** for *internal version-controlled 12-test design only*, NOT external study preregistration. G3 anatomical reviewer, G4 pretreatment/tissue chronology and G6 qualified paired n still unavailable; **HCC-20 PENDING** and manuscript ceiling **S0**.
- Review [14-patient RNA Hallmark score QC and pathway redundancy report](HCC_MRI_14_HALLMARK_PATHWAY_QC_REPORT_20261031.md), [small scores CSV](HCC_MRI_14_MSIGDB_HALLMARK_RANK_SCORE_20261031.csv), and [ledger](HCC_VERIFICATION_LEDGER.csv) before ever computing an MRI–RNA p-value.

## Clinical eligibility source gate — GDC 14-person treatment/tissue review (2026-10-31)

- Live, public GDC `/cases` source audit [run #111](https://github.com/kimtk94/Codex/actions/runs/41089216888) verified **14/14** case records and exact Primary Tumor sample barcodes used in previously verified RNA STAR files. Diagnosis treatment field `prior_treatment`: 5 people have only `No` and **9 have `Yes|No` across diagnoses**, requiring record-level adjudication.
- Explicitly administered `diagnoses.treatments.treatment_or_therapy == Yes` entries appear in all 14 cases, but many are *post-tissue* or have missing start dates. A separate GDC-relative-days audit flags **five cases** where an affirmative therapy start is on/before the recorded RNA tissue collection day: **TCGA-BC-A10Y, TCGA-BC-A5W4, TCGA-DD-A4NH, TCGA-G3-A25T, TCGA-G3-AAV1**. This is a high-priority **review flag** only, not a verified pre-MRI treatment or mandatory exclusion.
- The original TCIA TCGA-LIHC collection identifies baseline studies as pre-surgical, but its DICOM dates were shifted differently from TCGA diagnosis-relative treatment/tissue dates. **No patient MRI-to-RNA tissue interval has been safely reconstructed, even when days_to_collection is present.** Sources: [TCIA identifiers and shifted dates](https://wiki.cancerimagingarchive.net/pages/viewpage.action?navigatingVersions=true&pageId=44499397) and [GDC cases API supported clinical fields](https://docs.gdc.cancer.gov/API/Users_Guide/Appendix_A_Available_Fields/).
- Linked sample/portion slides have tumor cell and tumor nuclei percentages for **14/14** (min observed tumor cells 50%, min tumor nuclei 70%), but such slides may not be the exact sequenced aliquot and cannot replace independent genomic ABSOLUTE purity estimation.
- **G3/HCC-12** still PARTIAL due to no clinical image reviewer, **G4/HCC-14** now PARTIAL (real GDC clinical data but no safe MRI chronology), **G6/HCC-17** remains PENDING, qualified paired patient n **NOT ASSESSED**, **HCC-20** remains PENDING. Claim ceiling stays S0. All 14 unresolved are **HOLD**, not "14 ineligible" and not "14 eligible".
- IMPORTANT decision scenario: The preregistered 12-test low-dimensional exploratory analysis requires *final eligible n ≥ 10*. If all five high-priority cases were independently adjudicated ineligible, maximum possible eligible n would be **9**, automatically a **STOP** for 12 primary tests. Do not preemptively exclude any case; first resolve source evidence. If fewer than 10 pass, pivot to a descriptive proof-of-feasibility/reproducibility report or a newly acquired larger paired source cohort, not outcome-driven feature-family changes.
- [Detailed source interpretation, patient-level review classes and GO/HOLD/STOP](HCC_MRI_14_CLINICAL_TREATMENT_ELIGIBILITY_AUDIT_20261031.md) · [14-case source CSV](HCC_MRI_14_GDC_CLINICAL_TREATMENT_GATE_20261031.csv) · [reproducible fail-closed manual review queue](ci/mri_clinical_gate_review_queue.py).


## Genomic purity reference cross-method verification — 2026-10-31

Two independent, public, file-hash-locked sample-level TCGA purity references now support the 14-case technical candidate cohort, but **do not constitute purity measured on the same sequenced RNA aliquot**.

- PanCanAtlas NCI ABSOLUTE (DNA somatic CN) from official GDC UUID 4f277128-f793-4354-a13d-30cc7fe9f6b5, SHA256 f430a975433d82e0098d7405619d4f12a0c765fcd97e7d63cc9b1de7f2d763cd: **13/14** have same 16-character tumor specimen as GDC STAR RNA; median 0.74. TCGA-DD-A4NJ missing, NOT zero.
- Aran et al. 2015 Supplementary Data 1 CPE (historical consensus of disparate sources), official publisher file 553082 bytes SHA256 fce1ba13ff3a6432b7e4f260eb516e407c967d615ca87bc8dffa7765baf97529, [real-data run #128](https://github.com/kimtk94/Codex/actions/runs/41091879111): **14/14** same tumor specimen IDs, median 0.81565. Historical `ABSOLUTE` field missing for these 14; so it is not interchangeable with current NCI ABSOLUTE source.
- Very different sample purity proxies: A3CJ 0.20 ABSOLUTE DNA vs 0.8806 CPE, A7M7 0.58 vs 0.836. Below 0.50 (descriptive QC review threshold only): ABSOLUTE 3/13, CPE 2/14. Do **not** drop or impute subjects using these post-source-discovery thresholds, do not maximize hypothetical imaging association signals by choosing a preferred purity method.
- Aran 2015 reference uses older TCGA assays/normalizations, not the new GDC GENCODE STAR count aliquot. Same 16-character sample barcode does **not** prove same nucleic-acid analyte/aliquot or image-lesion identity. Histopathology slide percent tumor cells/nuclei is separate again.
- Report exact source version and barcode matching level; if eventual eligible cohort permits any purity sensitivity, prespecify alternative estimates, missingness and direction of discordance and report all results rather than cherry-picking.
- No image–RNA associations run; manuscript claim ceiling **S0**. HCC-16 remains PARTIAL because exact RNA purity, TSS and sample composition still uncertain. HCC-14 and HCC-17 remain treatment/MRI eligibility bottlenecks.
- Full [purity QC evidence report](HCC_MRI_14_CROSSMETHOD_PURITY_VALIDATION_20261031.md), source [ABSOLUTE](HCC_MRI_14_PANCAN_ABSOLUTE_PURITY_PROXY_20261031.csv) and [historical CPE](HCC_MRI_14_ARAN2015_CPE_REFERENCE_PURITY_20261031.csv).


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
