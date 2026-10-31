# HCC MRI × tumor RNA — source treatment and ABSOLUTE quality adjudication, 2026-10-31

## Scope and evidence

Reassessment is **clinical-source provenance only**, not a radiologist or oncologist's clinical adjudication. The frozen 14 TCGA-LIHC MRI × primary tumor RNA technical candidates remain unresolved.

- Source run: [HCC public clinical-source audit #139](https://github.com/kimtk94/Codex/actions/runs/41155810208). The original public GDC `/cases` diagnosis-by-treatment records were fetched for 14 cases, plus checksum-pinned PanCancer Atlas ABSOLUTE `TCGA_mastercalls.abs_tables_JSedit.fixed.txt`.
- **130 individual GDC treatment records**, of which **42** are explicitly `treatment_or_therapy=Yes`; rows with `No` are not treated as administration. All source patient barcode matches remain one-to-one.
- 10 affirmative Yes source records were dated on/before GDC `samples.days_to_collection` in five persons; these 10 are committed with their treatment UUID, diagnosis barcode, primary diagnosis, treatment type, anatomy and relative start/day in [source early-treatment rows](HCC_MRI_10_DATED_YES_TREATMENTS_SOURCE_20261031.csv).
- Reproducible source extractor [mri_treatment_and_absolute_source_detail_audit.py](ci/mri_treatment_and_absolute_source_detail_audit.py), anatomic-context classifier [mri_treatment_anatomic_context_review.py](ci/mri_treatment_anatomic_context_review.py), latest [offline tests in Actions #142](https://github.com/kimtk94/Codex/actions/runs/41155994004). One-shot source network job was removed after evidence was captured; original audit run retains the complete 130-record derived CSV artifact for a limited period.

## Critical refinement of the earlier 5-person screen

**Only four** of the five people with any dated prior-treatment record have a Yes record tied to a diagnosis labeled `Hepatocellular carcinoma, NOS`. The fifth patient's *dated* record was an operation at a different anatomic site.

| Patient | Dated affirmative source treatment relative to RNA specimen | Diagnosis context | Interpretation |
|---|---|---|---|
| `TCGA-BC-A10Y` | Day 0 RFA, days 420/470/527 chemoembolization records vs tissue day 2961; **6 source rows**, multiple entries for the same date | HCC diagnosis, explicit organ treated unspecified | **P0 HCC-diagnosis-context therapy**; repeated records on same day are not evidence of six separate clinical sessions |
| `TCGA-DD-A4NH` | Chemotherapy day 162 vs tissue day 335 | HCC diagnosis, anatomic treatment site unspecified | **P0 HCC-diagnosis-context therapy**; therapy exposure/specific lesion unverified |
| `TCGA-G3-A25T` | Surgery NOS day 452 vs tissue day 1224 | HCC diagnosis, treated site unspecified | **P0 HCC-diagnosis-context surgery**; verify whether surgery refers to that lesion/sample or an earlier tumor |
| `TCGA-G3-AAV1` | Chemoembolization day 75 vs tissue day 146 | HCC diagnosis, treatment site unspecified | **P0 HCC-diagnosis-context therapy**; compare with radiology/intervention sequence before any eligibility decision |
| `TCGA-BC-A5W4` | Surgery NOS day 0 vs tissue day 224 | Diagnosis `Not Reported`, explicitly **Cecum / Appendix** | **P1 DIFFERENT ANATOMIC SITE**. This source treatment is not proven to be HCC therapy. Other Yes records for this patient lack comparable start days, so HCC pretreatment remains unverified |

This resolves a **classification artifact**, not clinical eligibility. The early screen still truly found **five patients with an affirmative dated intervention of some kind**, but only **four** have a dated intervention under HCC diagnosis context. Because those four source entries have missing specific target-site details, even these are **NOT proof** that the published PV MRI index lesion or resected RNA lesion was already treated.

### Refined case-review prioritization

- **P0 four**: A10Y, DD-A4NH, G3-A25T, G3-AAV1 — affirmative dated intervention connected with an HCC diagnosis, medical record adjudication needed.
- **P1 five**: BC-A5W4 (other organ, but undated HCC-treatment context unresolved) plus BC-A3KG, DD-A4NF, DD-A4NJ, G3-A3CJ (treatment history conflict, earlier dated HCC therapy unconfirmed).
- **P2 five**: BC-A69I, G3-A7M7, G3-AAV2, G3-AAV3, G3-AAV7 — diagnosis `prior_treatment` shows `No` only, but **no patient-specific MRI pretreatment confirmation**.
- These are **review priorities, not 4 or 5 exclusions**. All 14 final decisions remain `HOLD_UNRESOLVED_NOT_EXCLUDED`. Confirmed eligible n **NOT ASSESSED** and confirmed excluded n **NOT ASSESSED**.

## ABSOLUTE copy-number call metadata

- All **13/14** source specimens with an ABSOLUTE DNA-derived purity estimate have `call status=called` and `solution=new`. One, **TCGA-DD-A4NJ**, is absent from the source.
- Thus `TCGA-G3-A3CJ` ABSOLUTE=0.20 is **a recorded called estimate**; its divergence from independent 2015 Aran CPE=0.8806 is **not resolved**. The methods, versions, source portion and inferred tumor admixture may differ. A `called` record establishes neither DNA call accuracy nor RNA aliquot purity.
- Other priority purity checks remain G3-A7M7 (ABS=0.58 vs CPE=0.836), DD-A4NH (ABS=0.34, CPE=0.473), G3-AAV3 (ABS=0.47, CPE=0.4591), and DD-A4NJ missing ABS.
- [Previous purity study crosswalk](HCC_MRI_14_CROSSMETHOD_PURITY_VALIDATION_20261031.md) holds both original published model sources and all 14 patient-level estimates.

## Locked scientific gates and next decisions

1. Treat **GDC relative treatment/tissue days as GDC-only**, not directly comparable to shifted TCIA MRI acquisition dates. They may refer to separate diagnoses or episodes. No safe image–therapy alignment has been reconstructed.
2. Require qualified reader to verify PV source MRI lesion, tumor3 for A10Y, and whether selected MRI lesion is the resected primary tumor represented by the STAR-count RNA aliquot. Segmentation Dice and reader ICC do not establish this biological match.
3. Request provenance-aware relative scan/tissue/treatment order or deidentified case-level annotations from TCIA/LiverHccSeg data stewards. Do not request or publish identifiable clinical dates.
4. Clinically adjudicate HCC-diagnosis treatment site/episode in four P0 cases, separately distinguish the unrelated cecal/appendiceal surgery for A5W4 and investigate its undated liver-related treatments.
5. Preserve all 14, freeze eligible/excluded/unknown reasons only when clinically verified. The locked 12-test family still requires **eligible n >=10** and no unresolved pretherapy source gate; **DO NOT compute MRI–RNA association/p-values until then**. Purely technical study S0 remains an available fallback.

**HCC-14 = PARTIAL**, HCC-16 = PARTIAL, HCC-17 = PENDING, HCC-20 = PENDING; manuscript claim ceiling S0. Source treatment and ABSOLUTE quality checks have **PASS_TECHNICAL provenance**, not clinical eligibility PASS.
