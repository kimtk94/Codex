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
