# HCC Stage 43 — original PV MRI DICOM source fully verified across all frozen 14 cases

**Date:** 2026-11-02 KST. **Provenance:** original public LiverHccSeg v1.1 Zenodo record `8179129`, original `pv.nii.gz` NIfTI and original DICOM image source.

## Source of truth — actual CI and artifacts

- Stage41 first two full-stack original source patients: [GitHub Actions #41431710438](https://github.com/kimtk94/Codex/actions/runs/41431710438), both patient jobs and independent aggregate **SUCCESS**.
- Stage42 original 12-patient pixel-candidate discovery: [#41434645131](https://github.com/kimtk94/Codex/actions/runs/41434645131), **12/12 original source patient jobs SUCCESS**, 75 geometry candidates, 225/225 original DICOM pixel comparisons, exactly one strong candidate per case. Original stage42 aggregate-only job failed because `numpy` not installed. Independent aggregate [#41435720562](https://github.com/kimtk94/Codex/actions/runs/41435720562) **SUCCESS** without source image recomputation. Artifact **13136387504**.
- Stage43 each remaining source patient full-volume DICOM↔NIfTI: [#41436023580](https://github.com/kimtk94/Codex/actions/runs/41436023580), **12/12 original patient jobs SUCCESS**. Original final aggregate job failed solely due to absent `numpy` in its runner.
- **Authoritative independent all-14 source-artifact audit:** [#41438155270](https://github.com/kimtk94/Codex/actions/runs/41438155270), **SUCCESS**. This separately restored the two successful Stage41 original source artifacts and twelve successful Stage43 original source artifacts, verified every original-slice CSV against original source per-patient JSON with no original image redownload or recomputation, rejected duplicated source Study/Series/SOP identity and disallowed any clinical/biological promotion.
- Final audit artifact: **13138210929**, SHA256 `4a1118125c870875b8ede2b7648c35b22d21d979576bcef079819646405dc518`.
- Scripts: `research/hcc/ci/hcc_stage41_fullstack_original_source.py`, `research/hcc/ci/mri14_stage42_remaining_source_pixel_candidates.py`, `research/hcc/ci/mri14_stage43_remaining12_source_fullstack.py`, `research/hcc/ci/mri14_stage43_full14_source_artifact_audit.py`.

## Actual independently reconciled patient-level source image evidence

| Frozen TCGA patient | Original DICOM CRC-verified slices | Minimum all-pixel Pearson | Max DICOM LPS→NIfTI RAS coordinate error (mm) |
|---|---:|---:|---:|
| TCGA-BC-A3KG | 88 | 1.000000 | 0.0000064857 |
| TCGA-BC-A69I | 88 | 1.000000 | 0.0000052802 |
| TCGA-BC-A10Y | 19 | 1.000000 | 0.0000536589 |
| TCGA-BC-A5W4 | 72 | 1.000000 | 0.0000079227 |
| TCGA-DD-A4NF | 60 | 1.000000 | 0.0000053948 |
| TCGA-DD-A4NH | 64 | 1.000000 | 0.0001947285 |
| TCGA-DD-A4NJ | 88 | 1.000000 | 0.0005257443 |
| TCGA-G3-A25T | 80 | 1.000000 | 0.0000056872 |
| TCGA-G3-A3CJ | 80 | 1.000000 | 0.0003509789 |
| TCGA-G3-A7M7 | 64 | 1.000000 | 0.0000414706 |
| TCGA-G3-AAV1 | 96 | 1.000000 | 0.0000105170 |
| TCGA-G3-AAV2 | 88 | 1.000000 | 0.0000406072 |
| TCGA-G3-AAV3 | 88 | 1.000000 | 0.0000074051 |
| TCGA-G3-AAV7 | 120 | 1.000000 | 0.0000612374 |
| **TOTAL / WORST CASE** | **1,095 / 1,095** | **1.000000** | **0.0005257443** |

All **14/14 selected native portal-venous NIfTI images** have an original source DICOM series supported by all original source slices and full-resolution pixel, consistent image orientation and DICOM LPS–NIfTI RAS spatial correspondence.

Technical qualification is strong source image provenance, **not proof of exact bitwise array identity**. Each source ZIP member was CRC checked, but the whole original Zenodo `dicoms.zip` archive MD5 was **not independently computed**, so neither whole-ZIP integrity nor bytewise image equality is claimed.

## Scientific decision and claim ceiling

| Gate | Verified result | Decision |
|---|---|---|
| Original source DICOM ↔ original selected PV NIfTI technical image provenance | **14/14** | **TECHNICAL GO** |
| Frozen MRI index lesion verified by independent qualified abdominal radiologist | **NOT_ASSESSED** | **HOLD** |
| Image scan preceded patient lesion-relevant HCC therapy from authoritative source chronology | **NOT_ASSESSED** | **HOLD** |
| Selected MRI index tumor corresponds to actual GDC STAR Primary Tumor RNA tissue specimen/portion/aliquot | **NOT_ASSESSED** | **HOLD** |
| Validated clinically eligible radiogenomics N | **NOT_ASSESSED**, not 0 eligible | **HOLD** |
| Frozen Hallmark MRI–RNA tests | **0/12** | **STOP** |
| Publication clinical/biological claims | **S0** | No effect size claims |

Note: the TCIA/public source DICOM dates may be privacy shifted and **must not be subtracted directly** from the relative-to-diagnosis GDC treatment date offset. An original DICOM's series identity does **not** supply the unshifted treatment episode or exact GDC RNA sample tissue provenance. In particular one prior surgery recorded for `TCGA-BC-A5W4` has Cecum/Appendix, not proven HCC surgery, and cannot be conflated with HCC pretreatment.

## Next evidence-first workflow

The **technical source imaging retrieval gate is closed for the frozen 14**; avoid spending further effort on source candidate searches. Prioritize original source records for treatment chronology and tissue/aliquot identity, and independent radiology evidence. Maintain a fail-closed patient-by-patient status table. Only after those gates can a clinically qualified N be defined and the locked 12 biologic tests evaluated.

No data access or clinical eligibility is inferred from source DICOM UID alone.
