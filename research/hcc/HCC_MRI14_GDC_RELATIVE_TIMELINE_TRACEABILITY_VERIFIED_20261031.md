# HCC P0 — MRI14 GDC treatment ↔ RNA specimen relative-day clinical traceability

**Run:** 2026-10-31 KST. [Actual GitHub Actions #41206214233](https://github.com/kimtk94/Codex/actions/runs/41206214233), **2/2 PASS**. Research interpretation **SOURCE DATA PASS, clinical paired-cohort eligibility HOLD, S0**.

## Source inputs and reproducible outputs

This is an **existing-source reclassification and traceability audit**, not new treatment data or a radiologist's approval. It is independent of all MRI–RNA pathway scores and associations.

Inputs checked one-to-one across exactly 14 fixed MRI candidate patients:

- [GDC case-level relative-treatment review](HCC_MRI_14_GDC_CLINICAL_TREATMENT_GATE_20261031.csv)
- [10 dated treatment-or-therapy Yes original GDC records](HCC_MRI_10_DATED_YES_TREATMENTS_SOURCE_20261031.csv), preserving source treatment UUIDs, diagnoses, sites, GDC relative treatment start and RNA specimen relative collection days
- [14 exact GDC STAR RNA file identifiers, aliquot barcode and MD5](HCC_MRI_14_GDC_PRIMARY_TUMOR_RNA_FILE_MANIFEST_20261030.csv)
- [14 frozen patient/index-lesion selection](HCC_MRI_14_PREOUTCOME_INDEX_LESION_SELECTION_20261030.csv)
- [14-case clinical source / expert review matrix](HCC_MRI14_QUALIFIED_REVIEW_EVIDENCE_MATRIX_20261031.csv)

Actual output: **14 rows × 24 columns** preserving patient ID, fixed index tumor number, RNA aliquot barcode, GDC file UUID, treatment record UUIDs, original relative sample day, dated HCC-diagnosis-context treatment count, earliest dated HCC-context treatment, actual GDC-relative interval, unrelated-organ events, case priority, and explicit missing case-level MRI chronology / source image–RNA lesion matching / reviewer approval.

Reproduce by running `python3 research/hcc/ci/mri_p0_clinical_gdc_relative_timeline_crosswalk.py --offline-test` (five negative fixtures) or without `--offline-test` for 14-row output. CI artifacts:
- `hcc-mri14-gdc-relative-timeline-source-evidence-hold` (artifact **13044478800**), member `HCC_MRI14_GDC_TREATMENT_TISSUE_SOURCE_TRACEABILITY_20261031.csv`, SHA-256 **10aa3a435c98df8b2485dd6c052c3693b85338f5699111c5b59cb6716a879d8d**.
- `hcc-mri14-gdc-relative-timeline-summary` (artifact **13044508712**), JSON SHA-256 **9ae90f94022b2faae5ccd0ba855e42627b3054f33d00a3f38edeb07e0a62aefa**.

## Actual GDC relative timeline

**Important:** Treatment records here are connected with an **HCC diagnosis**, but their treated organ/index lesion can still be unknown. The treatment onset and RNA specimen collection numbers below are **GDC days from diagnosis**; the original MRI date is not on this scale.

| Frozen HCC case | HCC-context Yes rows before tissue | Distinct recorded start days | Earliest HCC-context treatment day | RNA specimen day | Interval (days) | Case priority |
|---|---:|---|---:|---:|---:|---|
| TCGA-BC-A10Y (MRI tumor3) | **6** | 0, 420, 470, 527 (**4 unique days**) | 0 | 2961 | **2961** | P0 |
| TCGA-DD-A4NH | 1 | 162 | 162 | 335 | **173** | P0 |
| TCGA-G3-A25T | 1 | 452 | 452 | 1224 | **772** | P0 |
| TCGA-G3-AAV1 | 1 | 75 | 75 | 146 | **71** | P0 |

- **A10Y**: six GDC Yes treatment rows represent **four distinct documented days**, not six verified clinical treatment sessions. Explicit radiofrequency ablation day 0, reported chemoembolization at days 420/470/527; organ and tumor index identity remain unverified. The long tissue interval makes source episode continuity a high priority.
- **A4NH**: HCC-diagnosis-context chemotherapy day 162, specimen day 335; actual treated lesion and MRI timing unknown.
- **A25T**: HCC-diagnosis-context surgery NOS day 452, specimen day 1224; whether the surgery concerned the RNA-sampled MRI index lesion is unknown.
- **AAV1**: HCC-diagnosis-context chemoembolization day 75, specimen day 146; no verified MRI-before-locoregional-treatment evidence.

### Separate other-organ finding

`TCGA-BC-A5W4`: one dated Yes **surgery NOS at day 0**, specimen day **224**, associated with a **Cecum / Appendix** site and diagnosis `Not Reported`. **This is not proven liver/HCC treatment** and should not be counted among the four HCC-diagnosis-context early-treatment patients. Other potentially relevant undated Yes records and MRI timing remain unresolved. Priority P1.

Other P1: BC-A3KG, DD-A4NF, DD-A4NJ, G3-A3CJ — conflicting or incompletely dated longitudinal records; no earlier dated HCC-context Yes record in the verified 10 original rows.

P2: BC-A69I, G3-A7M7, G3-AAV2, G3-AAV3, G3-AAV7 — diagnosis prior-treatment `No` is not proof of baseline MRI before all HCC-specific interventions.

**Source QC counts:** 10 original dated Yes event rows across 5 patients; **9 HCC-diagnosis-context events in 4 people**, **1 different-organ event in 1 person**. Total 14 unique MRI candidates, priority **P0 4 / P1 5 / P2 5**. RNA aliquot barcode starts with the corresponding case ID and `-01` primary tumor prefix in **14/14**; case/sample agreement is not image-lesion agreement.

## Official dataset date semantics — red-line prohibition

[TCIA's official TCGA-LIHC collection page](https://www.cancerimagingarchive.net/collection/tcga-lihc/) says that baseline TCGA imaging studies in TCIA were acquired **before surgery**. However, collection-level `pre-surgical` does **not** establish that the specific published LiverHccSeg study, selected MRI tumor or individual imaging scan occurred before prior **ablation, TACE, systemic chemotherapy, etc.** The 2023 [LiverHccSeg source release](https://zenodo.org/records/8179129) also describes the original acquisition hierarchy and registered imaging; it does not provide the missing case-level clinical episode bridge.

TCIA DICOM image dates are deidentified with **site/collection-based shifted dates**, whereas GDC diagnoses/treatment/sample days are relative to each case's pathologic diagnosis index date. These two scales **cannot be directly subtracted or compared**. Even if two scans within one TCIA patient retain their temporal ordering, an MRI scan cannot be placed relative to a GDC treatment without an independently verified date/episode bridge. [TCIA deidentification explanation](https://www.cancerimagingarchive.net/submission-and-de-identification-overview/).

Machine safeguards explicitly forbid making these inferences. The source may allow patient ID linkage but provides **no validated selected-lesion MRI → HCC treatment episode → RNA-sampled specimen** chain for any of the 14.

## Go/Hold/Stop and next clinical evidence requests

- **GO for source traceability / imaging methods:** source crosswalk 2/2 PASS, 14-case ART/registered PV reviewer images [9/9 PASS](https://github.com/kimtk94/Codex/actions/runs/41199138622); MRI methodology and phase sensitivity research remain technically reproducible.
- **HOLD for MRI–RNA biological pairing:** expert anatomical approval of the selected liver tumor and registered PV, authoritative scan-before-treatment chronology, and exact resected tumor → GDC aliquot connection all missing; all fourteen cases remain `NOT_ASSESSED`. Nothing here proves clinical inclusion or exclusion.
- **STOP for locked 12 MRI–RNA association tests:** not executed; do not relax the study's predeclared minimum qualified n ≥10 nor choose an MRI phase after seeing RNA p-values.
- **Conditional feasibility arithmetic, not an exclusion claim:** with 14 candidates, if all four P0 eventually fail, at most 10 may remain; a fifth verified exclusion would leave **at most 9**, below the procedural n ≥10 exploratory gate. Power at n=10–14 is intrinsically poor. No current patient is formally excluded.

**Required source request, without demanding identifying real dates:** for the exact TCIA/LiverHccSeg selected MRI `StudyInstanceUID/SeriesInstanceUID` and index tumor, obtain a source-authoritative deidentified **before/after HCC therapy** annotation relative to each relevant RFA/TACE/resection episode; verify MRI index lesion corresponds to the GDC primary tumor RNA aliquot/sample portion or use a qualified local review. A radiologist can judge image anatomy, but cannot on image appearance alone establish the GDC sample lineage or whether the actual scan predated therapy.

## Claims locked

HCC-12 image engineering technically PASS but clinically PARTIAL; HCC-13 reliability technically PASS but anatomical interpretation PARTIAL; HCC-14 clinical treatment sequence PARTIAL; HCC-17 eligible n NOT_ASSESSED; HCC-20 0/12 tests NOT_EXECUTED; manuscript ceiling **S0**. Alternative methods publication is more feasible than biological pathway claims absent source-custodian evidence.
