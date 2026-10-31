# HCC P0 source-space gate — LiverHccSeg arterial-space mask and raw PV concern

## Evidence and hard rule

- Official dataset **LiverHccSeg v1.1**: https://zenodo.org/records/8179129
- Peer-reviewed data description: https://pmc.ncbi.nlm.nih.gov/articles/PMC10587725/
- Source explicitly differentiates raw `pv.nii.gz` from `art_pv.nii.gz`, a non-rigid B-spline registered PV acquisition in arterial reference space.
- Official masks are documented as applicable to `art.nii.gz` and corresponding co-registered `art_pre/art_pv/art_del.nii.gz`. **Raw `pv.nii.gz` is NOT in that documented applicability list.**
- Existing HCC PV ICC/factorial scripts use raw `pv.nii.gz` paired with `rater[1,2]_tumor*.nii.gz`; earlier 14-case shape/affine and pixel QC is *not sufficient* to show correct tumor correspondence or motion-corrected source space.
- Another prior header audit reported raw PV & ART shapes/affines matching for 14/14 but `art_pv` mismatching 14/14. That result and official manuscript must be reconciled with actual NIfTI source files. **An unexpected mismatch is REVIEW, never force registration or implicitly choose a phase.**
- One case (`TCGA-BC-A10Y`) has explicitly frozen selected index tumor `tumor3`, not `tumor1`.

## New real-data GitHub Actions

- Read-only source audit: [P0 source-space workflow](../../.github/workflows/hcc-mri-source-space-p0.yml)
- Code: [official-source phase/mask gate](ci/mri_phase_mask_source_gate.py)
- Initial pilot: `TCGA-BC-A10Y` and `TCGA-DD-A4NH`; compare three NIfTI source phases `art`/`pv`/`art_pv` against frozen selected mask, including CRC-bounded member downloads, per-member SHA256, physical FOV-corner affine displacement, ROI geometry, voxel counts and median signal when geometrically compatible.
- Initial 14-case queue: every source/clinical decision `HOLD_UNRESOLVED_NOT_EXCLUDED` regardless of metadata match. Clinical priorities P0 four, P1 five, P2 five. Qualifying expert reviewer and source chronology documents are explicitly missing.
- Privacy/usage: no source NIfTI or full pixel arrays uploaded, only derived individual QC provenance metrics and clinical review queue. No image-RNA correlation calculations.
- A successful source file integrity or header-only comparison **does not permit biological tests**. Original raw-PV radiomics remains documented *technical measurement conditional on verifying mask-to-source correspondence*.
- After actual pilot data, record `geometry`, `source-space interpretation` and `manual review` separately for each case. Do not change selected image or biological hypotheses based on RNA scores.

## Decision gates

| Gate | PASS evidence | Pending decision |
|---|---|---|
| G3 ROI and phase | Independent inspection of intended mask reference, native and registered images, physical alignment and actual tumor overlay | **REVIEW / PARTIAL** until qualified reader verifies |
| G4 chronology | Authoritative scan-before-therapy / biopsy / resection ordering, no subtraction of shifted DICOM vs GDC dates | **HOLD** |
| G6 biological pair | Explicit same tumor lesion at imaging and RNA specimen, 14-patient inclusion/exclusion flow | **PENDING n** |
| G7 reproducibility | Reextract all MRI source features from clinically and geometrically valid source if original pairing not validated | Existing raw PV 14×2 ICC and factorial **descriptive only** |
| HCC-20 MRI–RNA | Full G3-G6 and frozen n≥10 minimum + predeclared 12-test SAP | **STOP/NOT EXECUTED** |

**Publication ceiling remains S0.** Source QCs are real but are not MRI-RNA biological effect, patient pretreatment verification, scanner harmonization, or standard-certified radiomics.

## Real source NIfTI pilot result: GitHub Actions #41187537805

All **three** source-space workflow jobs passed. This means source integrity and fail-closed review guard ran; the *scientific* state remains `REVIEW_SOURCE_REGISTRATION_AND_EXPERT_ADJUDICATION_REQUIRED`.

| Frozen case | ART↔ROI corner offset | Raw PV↔ROI corner offset | ART_PV↔ROI corner offset | Result |
|---|---:|---:|---:|---|
| A10Y, tumor3 | 0 mm | 0 mm | **284.257812 mm** | HOLD |
| DD-A4NH, tumor1 | 0 mm | 0 mm | **498.906274 mm** | HOLD |

All three NIfTI files in each case have the same 3D *array shape* as the selected mask. The large affine discrepancy for `art_pv` is real **header geometry mismatch**, not evidence that the actual B-spline image registration failed; e.g. a coordinate-header issue could coexist with aligned pixel arrays. The unregistered `pv` affine equality similarly does not prove pixel-level anatomical registration.

MRI signal median inside the **geometry-matched** ROI:
- A10Y: ART **152**, PV **251**; ROI **124,420** voxels.
- A4NH: ART **146**, PV **193**; ROI **234,873** voxels.

These are source signal diagnostics only, **not** a comparison of biologically qualified MRI phases or enhancement.

Evidence:
- [Actual 3-job source-space GitHub Action](https://github.com/kimtk94/Codex/actions/runs/41187537805)
- [Permanent 6-per-phase measurements + NIfTI member SHA256](HCC_MRI_P0_2CASE_ACTUAL_SOURCE_SPACE_20261031.json)
- Action artifact `hcc-mri-p0-arterial-rawpv-registeredpv-source-evidence` (download retention 30 days).

**Next:** compare image voxel indexing and NIfTI qform/sform/affine provenance, with actual ART↔registered ART_PV tissue landmarks in overlays. Avoid rewriting affine headers without documented original transform. Seek the dataset authors' validation of registered NIfTI headers, then a qualified radiologist's source-phase/ROI anatomical review. Do not automatically promote all 14 after a two-patient pilot; all remain unresolved.
