# HCC Stage 45 / 45b — Live GDC molecular biospecimen lineage verified; MRI–RNA clinical bridge remains HOLD

**Date:** 2026-11-02 KST

## Actual reproducible original public evidence

- **Stage 44** frozen 14 TCGA-LIHC MRI source Study/SeriesUID and original GDC STAR RNA UUID/MD5/aliquot manifest, CI [#41439608602](https://github.com/kimtk94/Codex/actions/runs/41439608602) **SUCCESS**.
- **Stage 45** actual live original GDC public `cases` and `files` API queries, CI [#41441332105](https://github.com/kimtk94/Codex/actions/runs/41441332105) **SUCCESS**. Live source API returned **14/14 cases and 14/14 exact RNA files**. Original GDC nested `sample→portion→analyte→aliquot` explicitly includes all 14 frozen RNA aliquot submitter IDs; all 14 original RNA file UUID and MD5 values match the frozen source manifest; all 14 original files' `associated_entities` include the matching aliquot ID. No token required for these public metadata records.
- **Stage 45b** separate independent audit of original Stage45 result artifact, CI [#41441835295](https://github.com/kimtk94/Codex/actions/runs/41441835295) **SUCCESS**. All **14/14** molecular GDC hierarchy links remain valid, **14/14** sample→analyte→aliquot barcode prefixes coherent; **13/14** portion-to-analyte *submitter-id number* prefixes coherent.
- Stage45 artifact **13141000753**, ZIP SHA256 `8abafbb608c8dcb9715bfaa72666dfda4b4ae38a14b2fb43b9cb389e8fbd1150`.
- Stage45b artifact **13141071538**, ZIP SHA256 `47df9cbed1045935c9a9ab33b15bde752a9b0df16b4460888e01f83efabbac22`.

## Important source exception to retain (not an automatic biological sample error)

`TCGA-G3-A7M7` (RNA aliquot `TCGA-G3-A7M7-01A-12R-A352-07`):
- GDC public nested **portion** submitter ID = `TCGA-G3-A7M7-01A-01`.
- GDC public nested **analyte** submitter ID = `TCGA-G3-A7M7-01A-12R`.
- GDC public **aliquot**, RNA file UUID and MD5 all match the Stage44 frozen manifest and official hierarchy.
- The portion/analyte *text identifier numbering* differs (`01` vs `12`). Keep `REVIEW_SOURCE_SUBMITTER_NOMENCLATURE`; do **not** silently rewrite the official identifiers or assume two separate samples / wrong RNA.

**All 14/14 sample records have `tissue_type=Tumor`, but `biospecimen_anatomic_site` was empty or not reported in the returned sample lineage.** Thus liver as a tissue-level anatomical annotation, subsegment/lesion number and the exact sampled MRI index tumor cannot be confirmed solely from public GDC biospecimen metadata. A `Primary Tumor` sample barcode and patient-matched MRI image is *not* proof of the same physical focus in multifocal HCC.

## Peer-reviewed original imaging / chronology evidence

Official LiverHccSeg [Zenodo v1.1](https://zenodo.org/records/8179129) and [original public paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC10587725/) state two board-certified abdominal radiologists scientifically reviewed MRI and lesions, and prioritized pre-treatment imaging in subjects with multiple scans. This is **published dataset-level professional image reading**; it does not replace an independently signed review of our frozen selected index lesion / registered PV ROI.

Official [TCIA TCGA-LIHC collection](https://www.cancerimagingarchive.net/collection/tcga-lihc/) notes baseline TCGA images are *pre-surgical*, but says DICOM image dates are privacy shifted and TCGA treatment timestamps are *relative to diagnosis*. Pre-surgical **does not establish before all HCC treatments** (TACE, RFA, chemotherapy, etc.). Subtracting shifted DICOM dates from GDC relative days is invalid.

GDC official [API field appendix](https://docs.gdc.cancer.gov/API/Users_Guide/Appendix_A_Available_Fields/) and [biospecimen hierarchy](https://docs.gdc.cancer.gov/Encyclopedia/pages/Biospecimen_Data/) corroborate official sample/portion/analyte/aliquot entity roles, but provide no explicit MRI-selected tumor ROI→resection block/portion ID in these tested public records.

## Updated scientific gates

| Gate | Status | Scope and meaning |
|---|---|---|
| Original MRI↔PV DICOM source 3D technical provenance | **14/14 GO** | 1,095 DICOM slices Stage43 independent audit |
| Original MRI Study/Series UIDs to GDC case/barcoded RNA file | **14/14 GO** | Stage44 |
| Original live GDC sample→portion→analyte→aliquot and RNA file UUID/MD5 | **14/14 GO** | Stage45, public GDC API |
| GDC portion/analyte *identifier-text* consistency | **13/14 PASS; 1 REVIEW** | `TCGA-G3-A7M7`, no patient exclusion inferred |
| GDC anatomical site in returned sample lineage | **0/14 informative** | Empty in all 14 sampled source records |
| Original selected MRI lesion→exact GDC RNA sequenced portion | **NOT_ASSESSED** | No lesion-specific source evidence |
| MRI scan before all relevant HCC therapies | **NOT_ASSESSED** | No source-authoritative unshifted image-to-clinical-episode bridge |
| Independent new abdominal radiologist index-lesion verification | **NOT_ASSESSED** | Original publication reader review acknowledged |
| Clinically qualified / excluded case count | **NOT_ASSESSED** | Not 0 eligible, not 14 excluded |
| MRI–RNA Hallmark biological association panel | **0/12 tests** | STOP pending inclusion and pretreatment qualification |
| Publication-level biological/clinical claims | **S0** | No association or mechanism claim |

## Decision: no further repetitive source-identity queries

**Technical image + molecular sample provenance verification is substantially complete for this *public* subset.** Automated searches of the same GDC public case, portion and treatment fields cannot manufacture the missing image-to-resection-index-lesion bridge or valid pretreatment chronology. If no additional lesion-specific source evidence can be obtained, the specific TCGA-LIHC MRI×RNA paired biology design remains **HOLD**. Do not run 12 association tests with unqualified patients.

For a master's thesis without source-custodian confirmation, separately consider an **image-only radiomics/segmentation reproducibility and external validation** question using the fully verified original MRI provenance and existing external OpenSwissHCC cohort. This is a *different*, potentially publishable analytical design and needs its own independent statistical validation and clear claim ceiling; it must not be presented as MRI–RNA molecular association.

Preserve the Stage45/45b artifacts, the original 14-person evidence matrix, source links and the single GDC identifier anomaly in Issue #497. No attempt was made to establish a new true treatment date by de-shifting TCIA records.
