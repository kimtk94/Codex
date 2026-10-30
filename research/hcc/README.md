# HCC Radiomics and public CT-RNA research

**Protocol:** [HCC Radiogenomics research and feasibility gates](HCC_RADIOGENOMICS_PROTOCOL_20261030.md)

Two related, but distinct analyses:

1. **Primary: TCGA-LIHC CT x tumor RNA-seq radiogenomics.** TCIA CT series metadata matched to GDC TCGA-LIHC primary-tumor STAR-Counts *case IDs*. Only patients with verified CT phase, pretreatment timing, tumor segmentation and linked tumor aliquots proceed to RNA/radiomics association analyses.
2. **Secondary: TACE prognosis radiomics benchmark.** Train on WAW-TACE (233 listed) and externally test a frozen model on HCC-TACE-Seg (105 listed) after eligibility/phase/endpoint harmonization. These two cohorts DO NOT contain matched RNA-seq cohorts. Existing studies already report weak model transfer; do not position this as new standalone molecular validation.

## Automated public metadata CI

Actions -> **HCC Public Cohort Audit** -> Run workflow (feature branch before merge, main after merge).

- TCIA NBIA public API queries CT series for HCC-TACE-Seg and TCGA-LIHC; writes patient-series metadata (no images).
- GDC public API queries TCGA-LIHC primary tumor STAR - Counts **metadata** and intersects against CT patients; writes candidate counts and public barcodes. This is *not* final CT/ROI/RNA matched eligibility.
- Pull requests run offline fixture tests without network calls.
- Workflow artifacts include TCIA CT series CSVs, JSON summary, TCGA RNA candidate CSV and metadata summary.
- No DICOM, genomic expression values, patient hospital data, or protected linkage data are transferred into public CI.

Local offline test:
    python research/hcc/ci/tcia_cohort_audit.py --offline-test
    python research/hcc/ci/tcga_rna_overlap_audit.py --offline-test

Actual validation still pending: confirm GDC live response schema, exact patient intersection, scanner phase, segmentations, tissue sample/aliquot, imaging date and effective cohort size. Avoid leakage through repeated CT series, multiple lesions or multiple RNA files.

## Existing exploratory Colab notebooks (Google Drive)
- HCC_Public_Radiomics_Model_Starter.ipynb: preliminary ROI-to-feature CNN; **no trained or validated model**.
- HCC_TCIA_External_Validation_Starter.ipynb: pre-treatment CT verification template; **no external testing results**.
- Folder: https://drive.google.com/drive/folders/1YVSssXSTn8S2Bau3ji7vhs33y5jnKxnZ

Sources: WAW-TACE https://zenodo.org/records/12741586 ; HCC-TACE-Seg https://www.cancerimagingarchive.net/collection/hcc-tace-seg/ ; TCGA-LIHC https://www.cancerimagingarchive.net/collection/tcga-lihc/ .
