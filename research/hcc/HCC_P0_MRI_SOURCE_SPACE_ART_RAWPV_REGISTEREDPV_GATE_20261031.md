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
