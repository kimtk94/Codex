# HCC Radiomics × RNA-seq — Public cohort research

## Start here (required for every continuation)

- **Master verification standard and manuscript significance/claim rubric:** [HCC_VERIFICATION_AND_PUBLICATION_FRAMEWORK.md](HCC_VERIFICATION_AND_PUBLICATION_FRAMEWORK.md)
- **27 live evidence checkpoints:** [HCC_VERIFICATION_LEDGER.csv](HCC_VERIFICATION_LEDGER.csv)
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
