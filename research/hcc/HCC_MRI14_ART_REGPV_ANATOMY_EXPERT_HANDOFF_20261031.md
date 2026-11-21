# HCC P0 — Full 14-case ART/registered-PV anatomical reviewer handoff (source-matched)

**Verified 2026-10-31 KST. Status: image panel generation PASS / expert anatomy and MRI–RNA clinical eligibility NOT ASSESSED / publication ceiling S0.**

## Actual public-image execution and source

- [GitHub Actions #41199138622](https://github.com/kimtk94/Codex/actions/runs/41199138622): **9/9 jobs SUCCESS** including a synthetic negative-fail-closed/three-plane test, all seven deterministic two-case source-data image jobs, and one compiled 14-case reviewer index verification.
- Primary full artifact: `hcc-mri14-art-registered-pv-qualified-review-contact-sheets`, artifact ID **13042520765**, 14 PNG images + `HCC_MRI14_ANATOMY_REVIEW_PENDING_INDEX.csv` + seven source-shard trace CSVs + markdown index. GitHub Actions 90-day archive, not an authoritative clinical record.
- Original public dataset [LiverHccSeg v1.1, Zenodo 8179129](https://zenodo.org/records/8179129). Two independent published expert tumor masks per case. Select one pre-outcome index lesion per case, `TCGA-BC-A10Y` `tumor3`, otherwise `tumor1`.
- ART and **official arterial-registered portal-venous `art_pv`** data are displayed side-by-side in 3 anatomical slices per source, each with rater1 magenta and rater2 cyan tumor boundaries. Pixel axes are exact NIfTI signed-orientation transform to the mask without creating a new deformable registration. The coronal/sagittal display aspect was corrected for physical voxel spacing; panels are expressly **not reoriented to a clinical radiology convention**.
- Bounded-range ZIP source NIfTI retrieval; each ART, registered PV and each rater mask has its own SHA-256 in the review index. No raw medical volume is checked into the Git repository.
- **14 unique PNG + 14 unique source case rows, 14/14 coordinate maximum affine corner difference ≤0.5mm, 14/14 rater mask overlap Dice ≥0.5; expert reviewer status 14/14 NOT_ASSESSED.**
- Original source feature analysis [#41191599451](https://github.com/kimtk94/Codex/actions/runs/41191599451) separately showed 14 patients, 56 rows, GLCM Contrast median absolute source phase change 22.080%, source phase cannot be selected by biologic association p-value.

## Actual measured source-mask QA, before expert decision

The original rater-vs-rater Dice values are physical mask overlap, **not a test of whether the lesion is biologically HCC or accurately aligned with RNA tissue**.

| Technical observation | Source result | Suggested independent review action |
|---|---|---|
| 14 of 14 source spaces | ART and axis-reoriented `art_pv` pass geometric 0.5mm tolerance | Compare actual lesion anatomy, vessels, borders and respiratory-motion deformation on full 3D source |
| Lowest mask Dice | `TCGA-G3-AAV1` 0.813619 | Highest image-reader disagreement flag; examine tumor perimeter and left-/right-reader included regions |
| Additional Dice <0.85 | `TCGA-DD-A4NF` 0.848457 | Examine whether small segmented lesion is consistently identified by both readers |
| Smallest frozen index tumor | `TCGA-G3-AAV7` 6.00539 mL | Check partial-volume/slice thickness and lesion identity in 3D, not just maximal axial slice |
| `TCGA-DD-A4NF` index tumor | 15.01465 mL | Prioritize small-lesion and borderline reader-Dice second look |
| `TCGA-BC-A10Y` | Tumor3, 740.18662 mL, source-specific thick axial slabs (~10.8mm z) | Verify locked tumor index and review boundaries across slabs; avoid interpreting source-phase texture change as biological signal |
| `TCGA-G3-AAV7` raw vs registered PV | 8,064,000/8,064,000 exact voxel values after orientation despite source file SHA differences; independently verified in [#41193062797](https://github.com/kimtk94/Codex/actions/runs/41193062797) | Do not call this automatic image registration failure; author/source metadata needed to explain identity |

**No clinical/anatomical PASS is inferred** from these image-only metrics or visual inspection by an unqualified reviewer.

## Frozen case-level clinical review queue

The clinical evidence priority is **not** the same as image-quality priority:

| Clinical bucket | Frozen TCGA cases | Why prioritized |
|---|---|---|
| **P0** (4) | BC-A10Y, DD-A4NH, G3-A25T, G3-AAV1 | Prior-treatment `Yes` with HCC diagnosis/treatment context in original GDC clinical records; case-specific imaging-before-therapy chronology unresolved |
| **P1** (5) | BC-A3KG, BC-A5W4, DD-A4NF, DD-A4NJ, G3-A3CJ | Conflicting/mixed clinical record or cross-source evidence; obtain authoritative original chart source before deciding |
| **P2** (5) | BC-A69I, G3-A7M7, G3-AAV2, G3-AAV3, G3-AAV7 | Record `prior_treatment=No` is insufficient to prove MRI preceded all HCC treatment |

**Machine-reviewable case handoff:** [14-case matrix with all observations and missing approval columns](HCC_MRI14_QUALIFIED_REVIEW_EVIDENCE_MATRIX_20261031.csv). Each row stores case ID, tumor index, frozen volume, rater Dice, registered-versus-raw GLCM signed percent change, separate automated image QC flags, clinical evidence queue reason, PNG basename and initial clinical HOLD state. **All fourteen** have `ART_tumor_ROI_expert=NOT_ASSESSED`, `registered_PV_tumor_ROI_expert=NOT_ASSESSED`, `MRI_pre_HCC_treatment=NOT_ASSESSED`, `RNA_same_selected_tumor=NOT_ASSESSED`, and `qualified_patient_eligible=NOT_ASSESSED`.

## Qualified reviewer SOP (do not infer PASS automatically)

1. Inspect the original multi-slice `art` and registered `art_pv` images for the same patient and index tumor, not only a screenshot. Confirm the lesion location on all three orthogonal planes and trace R1 and R2 independently.
2. Determine whether the selected tumor is HCC or other structure and whether the mask excludes normal parenchyma/vessels/necrotic regions when intended, noting any limits of original segmentation labels. Record explicit qualified reviewer name/role, date and evidence.
3. Review residual nonrigid mismatch across patient respiratory motion, large deformation and phased enhancement. Header/pixel axis geometrical PASS does not guarantee clinical image registration.
4. Obtain source-authoritative original MRI series/treatment sequence and GDC biospecimen provenance for the actual index tumor tissue. **Never directly join deidentified TCIA StudyDate and GDC days-to-event** without justified timeline mapping. Record credible same-lesion evidence separately from case-level RNA matching.
5. Record each decision as `PASS`, `FAIL` or `NOT_ASSESSED`; unknown/missing is **HOLD**, not implicitly excluded and not included in a significance test. Conflicting anatomy or tissue identity remains HOLD/FAIL with reason, do not silently drop patients.
6. **Only then** recalculate independently eligible paired n, apply the frozen prespecified minimum sample n ≥10 and all inclusion gates, and decide whether to execute exactly three prelocked imaging features × four Hallmarks = 12 MRI–RNA tests with the existing BH-FDR/permutation plan. With n=14 at most, any biology remains exploratory/underpowered. This document makes no diagnosis, treatment response, survival or causal claim.

## Decision as of 2026-10-31

- HCC-12 source-plane **geometric/pixel engineering PASS**, qualified anatomical matching **PARTIAL**.
- HCC-13 image reader ICC technically available, not evidence of biological matching, **PARTIAL**.
- HCC-14 patient treatment chronology **PARTIAL**, all required case-level dates/lineage unresolved.
- HCC-17 eligible patients **NOT ASSESSED**; 14 technical candidates ≠ 14 eligible tissue-matched patients.
- HCC-20 **PENDING**, 0/12 MRI–RNA association tests executed.
- The independent image-methodology fallback remains viable without clinical matching; a radiogenomics publication claim is **HOLD**.
