# HCC MRI 14 — GDC clinical treatment and RNA-tissue temporal eligibility audit

**Source evidence date:** 2026-10-31 KST. **Evidence run:** [GitHub Actions #111](https://github.com/kimtk94/Codex/actions/runs/41089216888), after code amendment distinguishing Yes treatments from placeholder "No" treatment records. **Review state: HOLD, not biological-cohort inclusion.**

## Scope / provenance

- Cohort: 14 frozen TCGA-LIHC MRI patients, each linked to one GDC STAR-Counts Primary Tumor RNA aliquot, all 14 verified by GDC case/sample barcodes.
- Source: publicly available GDC `/cases` diagnoses, treatments, sample days_to_collection and same-sample parent portion/slide metadata, not an image-level clinical study sheet.
- Reference: [NCI GDC clinical field dictionary](https://docs.gdc.cancer.gov/API/Users_Guide/Appendix_A_Available_Fields/), [TCIA TCGA-LIHC collection and baseline statement](https://www.cancerimagingarchive.net/collection/tcga-lihc/), [TCIA dates and identifiers](https://wiki.cancerimagingarchive.net/pages/viewpage.action?navigatingVersions=true&pageId=44499397).
- Patient-row machine evidence: [GDC clinical screening CSV](HCC_MRI_14_GDC_CLINICAL_TREATMENT_GATE_20261031.csv). Original full prescreen output and JSON: GitHub Actions run #111 artifact `hcc-mri-gdc-14-clinical-prescreen`. GitHub Actions artifacts have limited retention; the condensed row-level outputs are committed here.
- A barcode match demonstrates common TCGA case and sample-associated RNA, **not that the MRI index lesion is identical to the resected lesion**, nor that MRI imaging preceded all interventions.

## Observed data

| Check | Observed | What it does and does not mean |
|---|---:|---|
| GDC clinical case located | 14/14 | Public TCGA-LIHC case metadata exists |
| GDC exact Primary Tumor specimen linked to selected RNA | 14/14 | No apparent barcode mismatch; tissue-to-MRI lesion identity still unverified |
| `diagnoses.prior_treatment` exclusively `No` | 5/14 | No prior treatment *reported* in diagnosis records; not independent proof of untreated MRI |
| `prior_treatment` mixed `Yes` and `No` | 9/14 | Multiple diagnoses have discordant fields, requires temporal/record interpretation, no automatic exclusion |
| At least one `treatment_or_therapy == Yes` | 14/14 | Treatment may be *after* specimen acquisition; treatment type records saying `No` do not count as administered |
| Recorded **Yes** treatment start day on or before RNA sample collection day | **5/14** | **Priority clinical review flag**, not proof MRI occurred after treatment; treatment/tissue days are GDC index-relative |
| Slide-level tumor-cell/nuclei percentages found | 14/14 | Pathology slide proxy only; not sample-exact RNA purity nor genomic ABSOLUTE/ESTIMATE purity |
| Patient-specific original MRI date rejoined to tissue/therapy | **0/14** | TCIA images use date shift different from GDC relative days; no safe join |
| Expert confirmation original MRI shows the lesion resected for RNA | **0/14** | Three-plane automated image overlay is not independent radiologist review |
| Fully qualified MRI–RNA eligible patients | **NOT ASSESSED** | Do not report n=14 as finalized eligible cohort or n=0 as exclusions |

### Five priority cases — Yes therapy date on/before tissue date in GDC relative-day records

`TCGA-BC-A10Y`, `TCGA-BC-A5W4`, `TCGA-DD-A4NH`, `TCGA-G3-A25T`, `TCGA-G3-AAV1`.

This **does not** show that the archived MRI was post-therapy, because TCIA imaging dates have been offset, no patient-level date bridge has been validated, and the GDC treatment record may describe a different episode/tumor site. Each requires source context and expert adjudication before deciding inclusion/exclusion. The reported collection offsets (in days from diagnosis) include some very long intervals: A10Y 2961, A25T 1224; investigate the patient's longitudinal diagnoses and sample provenance.

### Four additional discordant prior-treatment cases without a verified earlier Yes treatment day

`TCGA-BC-A3KG` (Yes treatment date missing), `TCGA-DD-A4NF`, `TCGA-DD-A4NJ`, `TCGA-G3-A3CJ` (reported earliest **Yes** therapy date later than tissue collection). They are **not automatically classified as untreated or eligible**.

### Five cases reporting only No in the diagnoses prior-treatment field

`TCGA-BC-A69I`, `TCGA-G3-A7M7`, `TCGA-G3-AAV2`, `TCGA-G3-AAV3`, `TCGA-G3-AAV7`. These also have treatment records in the GDC longitudinal timeline (at least one explicitly Yes, dates missing in this prescreen) so status is `REPORTED_NO_PRIOR_TREATMENT_AT_DIAGNOSIS` only; **MRI–tissue pretreatment remains unverified**.

## Tissue purity / possible molecular confounding

- Linked-slide tumor-cell minimum across all patients: **50–100%**, and linked-slide tumor-nuclei minimum **70–100%**; values vary by slide. **Do not** treat these as bulk RNA purity estimates: slides are at a linked sample/portion level and may not come from the specific RNA aliquot analyzed.
- `TCGA-DD-A4NJ` has slide tumor cells 50% and tumor nuclei 100% (different metrics), showing that metrics cannot be substituted. `TCGA-G3-A7M7` has 70% for both. Both are **review flags rather than exclusions**.
- Strong pathway co-variation in the verified RNA-only HCC dataset (Angiogenesis–EMT Spearman rho ≈0.982) could reflect stromal fraction, biology or site/batch effects. Expression score correlation is neither evidence of HCC-specific tumor-cell signaling nor proof of the causal molecular pathway.
- Optional independent reference: Aran et al. / ABSOLUTE / PanCancer Atlas annotated purity, if **exact aliquot or sample mapping** is verified; do not impute cohort-level averages. [PanCancer Atlas portal](https://gdc.cancer.gov/about-data/publications/pancanatlas) lists purity/ploidy data.

## Scientific judgment — GO / HOLD / STOP

**Technical/source metadata retrieval: GO (PASS)** for all 14. **Clinical paired-cohort membership: HOLD** because exact pretreatment MRI chronology and expert same-lesion confirmation are absent. **Primary MRI–RNA 12-test association: STOP/NOT AUTHORIZED until eligibility gates pass** (do not even run the tests as exploratory screen until a written permitted pilot/denominator plan is agreed); HCC-20 PENDING; claim ceiling S0.

Required decisions with responsible evidence:

1. Obtain TCIA MRI DICOM acquisition identifiers and if possible deidentified scan order/source index consistent within the same image collection. Use clinical source chronology / expert review to establish **pre-intervention** status; never convert shifted DICOM dates into GDC diagnosis-relative days by naive subtraction.
2. At each case, reconcile discordant GDC diagnosis/treatment records: `prior_treatment`, `treatment_or_therapy`, start day, treatment method/site, and collect a dated reason for `VERIFIED_PRETREATMENT`, `POSTTREATMENT_EXCLUDE` or `UNRESOLVED_HOLD`.
3. Link exact RNA specimen portion/analyte to pathology slide and tumor purity reference if available. Separate slide `percent_tumor_cells` from `percent_tumor_nuclei` and from genomic purity estimates.
4. Reviewer confirms selected PV image + largest tumor mask is anatomically correct HCC, agrees with tissue target, and case is suitable for radiomics. If no reviewer/source bridge is feasible, make the manuscript a **technical feasibility or reproducibility study**, not an untreated HCC radiogenomics association paper.
5. After all 14 have an adjudicated clinical decision, save sample flow `14 screened -> N eligible -> M excluded -> U unresolved` with reasons and source references. Require **N + M + U = 14** and zero unresolved for confirmatory or fully qualified analysis.
6. If eligible n is too small (proposed analytical minimum 10), stop the frozen 12-test inferential analysis. Do not backfill control patients or change endpoints after checking associations.

## Gate changes

- HCC-14 (pretreatment/temporal) `PENDING -> PARTIAL`: GDC diagnosis/treatment/sample day/slide metadata was genuinely queried, but no exact MRI day bridge exists.
- HCC-17 (final paired subject denominator) **remains PENDING**: 14 are candidates, eligible count NOT ASSESSED.
- HCC-16 (RNA source/purity & pathway QC) **remains PARTIAL**: 14 gene expression vectors and four rank-score signatures validated technically, sample-specific clinical purity remains unresolved.
- HCC-20 (12 primary MRI–RNA tests) **remains PENDING**; no biological correlations or q-values permitted yet.

**Reproduction:** `research/hcc/ci/mri_gdc_clinical_eligibility_prescreen.py` and GitHub Actions run #111. Checkpoint truth is in [HCC_VERIFICATION_LEDGER.csv](HCC_VERIFICATION_LEDGER.csv).
