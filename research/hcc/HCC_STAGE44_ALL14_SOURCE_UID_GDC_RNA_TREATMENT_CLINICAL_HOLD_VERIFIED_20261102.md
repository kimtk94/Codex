# HCC Stage 44 — original Study/Series UID to GDC RNA and HCC-treatment source-evidence gate

**Evidence verified:** [Stage44 GitHub Actions #41439608602](https://github.com/kimtk94/Codex/actions/runs/41439608602) **SUCCESS**, original source 14/14. Date 2026-11-02 KST.

## Frozen sources and independently verified evidence

- Original PV image provenance: independent [Stage43 original 14-case artifact audit #41438155270](https://github.com/kimtk94/Codex/actions/runs/41438155270), **14/14 original DICOM ↔ native PV NIfTI source technical links PASS**, 1,095/1,095 CRC-verified source DICOM slices, global minimum full-resolution Pearson 1.0, max LPS-to-RAS error 0.0005257443 mm. These are image-provenance results, NOT pretreatment or same-lesion tissue proof.
- Original DICOM StudyInstanceUID: [Stage38 original headers #41383511403](https://github.com/kimtk94/Codex/actions/runs/41383511403), 247 source-folder representative DICOM headers with authenticated Study/Series UID. **14/14 selected original Stage43 SeriesInstanceUIDs uniquely matched a Stage38 original StudyInstanceUID**.
- GDC source: frozen original `research/hcc/HCC_MRI_14_GDC_PRIMARY_TUMOR_RNA_FILE_MANIFEST_20261030.csv`, `HCC_MRI_14_GDC_CLINICAL_TREATMENT_GATE_20261031.csv`, `HCC_MRI_10_DATED_YES_TREATMENTS_SOURCE_20261031.csv`, `HCC_MRI14_QUALIFIED_REVIEW_EVIDENCE_MATRIX_20261031.csv`, `HCC_MRI_14_PREOUTCOME_INDEX_LESION_SELECTION_20261030.csv`.
- Original GDC STAR RNA Primary Tumor file UUID, MD5 and aliquot case/sample barcodes: **14/14 PASS at TCGA patient/case/sample level**; this **does not** prove the actual GDC tissue portion comes from the exact selected MRI tumor lesion.
- Original treatment source: **10 dated Yes events preceding RNA specimen collection**, of which **9 HCC-diagnosis-context events across 4 patients** and **1 other-organ surgery** (`TCGA-BC-A5W4`, **Cecum/Appendix**, NOT independently HCC treatment).
- Priority: **P0 4**, **P1 5**, **P2 5**. Source evidence priority is not clinical exclusion or eligibility.
- Original DICOM acquisition dates are potentially privacy-shifted; **do not compare them numerically with GDC days-since-diagnosis**.

### Audit results

| Source evidence / clinical gate | Count | Decision |
|---|---:|---|
| Original 3D source DICOM ↔ native PV image | 14/14 | Technical GO |
| Native original Study UID ↔ selected verified Series UID | 14/14 | Technical GO |
| GDC Primary Tumor RNA file/aliquot same patient barcodes | 14/14 | Technical same-case GO |
| Verified original MRI episode **before all HCC-relevant therapy** | **0/14 provenance-confirmed** | HOLD, NOT_ASSESSED |
| Selected MRI index lesion ↔ RNA tumor block/portion/aliquot physical chain | **0/14 provenance-confirmed** | HOLD, NOT_ASSESSED |
| Independent abdominal radiologist original anatomy and registered PV acceptance | **0/14 independently reviewed** | HOLD, NOT_ASSESSED |
| Clinically eligible and excluded denominator | **NOT_ASSESSED** | Not 0 eligible or 14 excluded |
| Frozen MRI–RNA Hallmark tests | **0/12** | STOP |
| Clinical/biological claim ceiling | **S0** | No radiogenomics association claims |

### Patient-level priority

- **P0 treatment episode review (4):** `TCGA-BC-A10Y`, `TCGA-DD-A4NH`, `TCGA-G3-A25T`, `TCGA-G3-AAV1`. Early relative GDC treatment exists in HCC diagnosis context before RNA tissue, not necessarily before scan, and not necessarily the MRI index lesion.
- **P1 reconcile discordance / site (5):** `TCGA-BC-A3KG`, `TCGA-BC-A5W4`, `TCGA-DD-A4NF`, `TCGA-DD-A4NJ`, `TCGA-G3-A3CJ`. `A5W4` other-organ surgery MUST NOT be attributed to liver HCC.
- **P2 demonstrate baseline pretreatment and lesion source (5):** `TCGA-BC-A69I`, `TCGA-G3-A7M7`, `TCGA-G3-AAV2`, `TCGA-G3-AAV3`, `TCGA-G3-AAV7`. A prior_treatment=No or absence of dated Yes events cannot establish untreated imaging.

## What Stage44 actually produced

Actual [Stage44 CI #41439608602](https://github.com/kimtk94/Codex/actions/runs/41439608602) **SUCCESS**: offline negative controls, pinned Stage38 247-header and Stage43 14-case evidence restores, per-patient 14-item source join, and separate independent final false-clinical-promotion guard.

Final Artifact ID **13137678492** with ZIP SHA256 `d111fec872da5c7ff882c6df3b094a92d0312481d1edb7be08ea8279f5c5b553`. Includes:

1. `stage44_original_MRI_UID_GDC_RNA_treatment_14patient_evidence.csv` — exact patient Study/Series UIDs, selected MRI index lesion, original GDC STAR RNA file UUID/MD5, primary-tumor aliquot, GDC-relative specimen collection days, HCC-context treatment flags and clinical HOLD statuses.
2. `stage44_14patient_clinical_source_gaps_priority.csv` — P0/P1/P2 missing proof, unblocking request per patient, NO fabricated treatment chronology or tissue provenance.
3. `stage44_independent_radiology_source_review_template.csv` — study/series-qualified expert anatomy, registration, source reference and clinical evidence review template. All assessor fields blank / NOT_ASSESSED, no expert review imputed.
4. `stage44_original_MRI_GDC_clinical_source_summary.json` and `stage44_MRI_UID_GDC_case_specimen_treatment_evidence_report.md` — frozen accounting/decision.

Source script `research/hcc/ci/mri14_stage44_uid_gdc_clinical_evidence.py`; CI `.github/workflows/hcc-stage44-original-mri-uid-gdc-clinical-evidence.yml`.

**Next:** evidence-source availability audit, rather than inventing or inferring clinical eligibility: seek publicly accessible source-custodian relative-to-treatment MRI episode and original tumor-resection block-to-RNA-aliquot linkage, plus qualified independent radiologist. Stop if source does not explicitly connect the *selected lesion*. Do not redo the already completed original PV source technical image verification.
