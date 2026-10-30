# HCC MRI 14 matched GDC STAR RNA — numerical source-QC evidence

**Verified 2026-10-30** by [HCC GitHub Actions #76](https://github.com/kimtk94/Codex/actions/runs/41069103398). Original TCGA-LIHC primary tumor public STAR-Counts files (GDC augmented gene counts) retrieved by exact UUID. The raw gene matrices were *not* committed or uploaded as artifact.

## Audited cohort and reproducibility

- [Immutable public metadata manifest (14 UUID + MD5 + sample barcodes)](HCC_MRI_14_GDC_PRIMARY_TUMOR_RNA_FILE_MANIFEST_20261030.csv)
- 14 patients have **one** primary-tumor file-linked aliquot STAR-Counts file each; no duplicate tumor file selection ambiguity in the current GDC retrieval.
- 14/14 original file size and MD5 checks PASS, 14/14 GDC TSV rows and numeric fields PASS; consistent GENCODE v36 gene model and **60,660 distinct ENSG gene IDs** per sample.
- No invalid/missing/negative unstranded counts, no invalid TPM gene rows or duplicate ENSG IDs in inspected data.
- 14/14 gene-ID sets identical. Unstranded TPM sums range **999999.981–1000000.006**; unstranded raw counts are the primary exploratory RNA input, not TPM reinterpreted as counts.
- Total gene-level unstranded counts: **minimum 30,608,420**, **median 49,185,211**, **maximum 58,716,336**.
- Detected nonzero-count gene rows: **minimum 24,264**, **median 28,706**, **maximum 33,701**.
- 0/14 preliminary library-size outlier flags under the code's 0.5×–2× cohort median heuristic; **not** a clinical sample-quality threshold, independent replication, tumor purity or batch-correction validation.
- Downloaded ~59.06 MB across 14 files using https://api.gdc.cancer.gov/data/{file_uuid}; result metadata summary only preserved in GH Actions.
- GDC official source: [mRNA STAR gene counts / augmented TPM pipeline](https://docs.gdc.cancer.gov/Data/Bioinformatics_Pipelines/Expression_mRNA_Pipeline/), [GDC API data endpoint](https://docs.gdc.cancer.gov/API/Users_Guide/Downloading_Files/).

## Per-patient quality indicators

| Patient | Detected genes (unstranded > 0) | Total unstranded gene counts |
|---|---:|---:|
| TCGA-BC-A10Y | 31,204 | 58,716,336 |
| TCGA-BC-A3KG | 33,218 | 57,943,719 |
| TCGA-BC-A5W4 | 26,184 | 38,988,266 |
| TCGA-BC-A69I | 25,344 | 46,805,235 |
| TCGA-DD-A4NF | 28,607 | 51,678,294 |
| TCGA-DD-A4NH | 33,701 | 46,062,743 |
| TCGA-DD-A4NJ | 29,633 | 30,608,420 |
| TCGA-G3-A25T | 28,805 | 57,113,225 |
| TCGA-G3-A3CJ | 24,264 | 51,467,784 |
| TCGA-G3-A7M7 | 26,255 | 44,194,112 |
| TCGA-G3-AAV1 | 28,498 | 53,281,325 |
| TCGA-G3-AAV2 | 27,309 | 49,547,364 |
| TCGA-G3-AAV3 | 29,040 | 48,823,058 |
| TCGA-G3-AAV7 | 29,862 | 43,936,666 |

## Gate and manuscript implications

- **HCC-15 source counts/aliquot technical provenance = PASS_TECHNICAL.** Exact 14 single-file primary tumor links, checksum and numeric gene count schema validated.
- **HCC-16 full RNA QC/pathway inference = PARTIAL.** Raw counts and detection QC done, but gene-name mapping, pathway releases, normalization, batch, tumor purity, RNA integrity and pathway-score model not yet validated.
- **HCC-17 qualified paired cohort = PENDING**, as reviewer image/mask anatomic validity, pretreatment tumor tissue chronology and clinical variables remain to be verified. Final n cannot be declared 14.
- **HCC-20 molecular association = PENDING.** No correlations, coefficients, p-values, BH-FDR, independent biological replication or clinical model were computed.
- **Permitted manuscript claim remains S0:** Reproducible small public multimodal technical cohort, not yet a scientifically validated radiogenomics pathway biomarker.

## Next actions

1. Freeze a precise PV MRI index lesion selection and extraction protocol (largest rater1 HCC tumor; inter-rater reliability or alternative lesion sensitivity) **before** any RNA association analysis.
2. Version-lock count-to-gene mapping, gene filtering, normalization and Hallmark gene-set release; generate independent sample-level RNA score QC without joining to radiomics outcomes.
3. Retrieve clinical covariate/pretreatment eligibility using authoritative TCGA time-relative documentation, and obtain professional review of original PV MRI/ROI overlays. Never infer timing from deidentified imaging calendar dates.
4. Only with approved paired patient list calculate predeclared imaging-feature–pathway association tests, with effect+CI and FDR, sensitivity to lesion size/scanner and no patient leakage.
