# HCC Radiomics × RNA-seq — Public cohort research

## Start here (required for every continuation)

- **Master verification standard and manuscript significance/claim rubric:** [HCC_VERIFICATION_AND_PUBLICATION_FRAMEWORK.md](HCC_VERIFICATION_AND_PUBLICATION_FRAMEWORK.md)
- **27 live evidence checkpoints:** [HCC_VERIFICATION_LEDGER.csv](HCC_VERIFICATION_LEDGER.csv)
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
- HCC-13 and HCC-18 now have real supporting evidence but stay **PARTIAL**. HCC-17 qualified paired patients, HCC-19 frozen hypotheses and HCC-20 biological correlations remain **PENDING**. Maximum manuscript claim **S0**.
- Heavy remote GitHub PR pilot jobs removed after successful audited run; PR CI retains deterministic offline tests only. Artifacts expire in ~30 days, permanent derived feature ICC values and source run evidence are in tracked Markdown/CSV.
