# HCC MRI P0 — official liver tumor ROI / registered portal venous phase coordinate validation

**Execution:** 2026-10-31 · Public reproducibility only, MRI–RNA biological inference not permitted.

## Official source

- LiverHccSeg v1.1 Zenodo: https://zenodo.org/records/8179129
- Gross et al. Data in Brief 2023: https://pmc.ncbi.nlm.nih.gov/articles/PMC10587725/
- The official source explicitly states that segmentation masks apply to arterial MRI and arterial-registered pre, portal-venous and delayed NIfTIs. Thus `art_pv.nii.gz`, **not** original `pv.nii.gz`, is the documented registered PV source-space for masks.
- Study uses 3D B-spline non-rigid registration based on normalized mutual information; simply flipping axes is **not** equivalent to re-performing that registration, and it must not be represented as such.

## Real-data verification

Source: GitHub Actions [HCC MRI 14-Case Orientation Header Audit #41188630515](https://github.com/kimtk94/Codex/actions/runs/41188630515), **all three jobs SUCCESS**.

- Source: official Zenodo v1.1 compressed NIfTI archive. 352 uncompressed NIfTI header bytes per member, selected index tumor prespecified.
- Exactly 14 frozen cases × (ART, original PV, registered ART_PV) = **42 source-space comparisons**.
- **ART and original PV:** 14/14 affine-compatible with mask **before** any orientation changes. This is not an endorsement of raw PV for registered tumor radiomics.
- **Registered `art_pv`:** 0/14 mask affine-compatible before orientation; **14/14 pass** physical 0.5-mm corner-distance tolerance **after only voxel axis reorientation without resampling**.
- **One Y-axis flip, thirteen X+Y flips; no axis permutations**. Registered PV source axis convention `LPS`; the 14 segmentation masks use their source `LAS` or `RAS` orientations.
- 10/14 corrected corner differences = 0.0 mm; remaining 4/14 corrected corner difference 0.11513–0.22536 mm.
- An unchanged header's raw 284–605mm disagreement is an orientation-coordinate convention issue; it does **not**, by itself, imply clinical misregistration.

| Frozen case | Selected tumor | ART_PV before (mm) | after axis-only (mm) | flips |
|---|---:|---:|---:|---:|
| TCGA-BC-A10Y | 3 | 284.25781 | 0 | Y |
| TCGA-BC-A3KG | 1 | 461.87125 | 0 | X+Y |
| TCGA-BC-A5W4 | 1 | 535.61882 | 0 | X+Y |
| TCGA-BC-A69I | 1 | 513.62985 | 0 | X+Y |
| TCGA-DD-A4NF | 1 | 498.90627 | 0 | X+Y |
| TCGA-DD-A4NH | 1 | 498.90627 | 0 | X+Y |
| TCGA-DD-A4NJ | 1 | 498.90627 | 0 | X+Y |
| TCGA-G3-A25T | 1 | 399.11427 | 0 | X+Y |
| TCGA-G3-A3CJ | 1 | 382.0195 | 0 | X+Y |
| TCGA-G3-A7M7 | 1 | 488.05867 | 0.22536 | X+Y |
| TCGA-G3-AAV1 | 1 | 605.39264 | 0.16245 | X+Y |
| TCGA-G3-AAV2 | 1 | 507.59398 | 0.13620 | X+Y |
| TCGA-G3-AAV3 | 1 | 493.42795 | 0 | X+Y |
| TCGA-G3-AAV7 | 1 | 429.09243 | 0.11513 | X+Y |

### Interpretation boundaries

**PASS_HEADER_ONLY** proves that applying exact voxel signed-axis orientation gives matching physical NIfTI voxel spaces to within declared tolerance. It does not establish the correctness of non-rigid deformation, tumor anatomy, treatment chronology, sample histology or match between image target lesion and sequenced RNA specimen.

**Locked biological claim:** HCC-12/13 remain PARTIAL; HCC-14 PARTIAL; HCC-17/20 PENDING. Qualified clinical patients n **NOT ASSESSED**, the 12 pre-registered MRI–RNA tests **NOT EXECUTED**, claim ceiling S0.

## Next gate: actual pixel validation, followed by methodological replication

CI: [HCC P0 MRI registered PV actual-pixel and locked-feature pilot](../../.github/workflows/hcc-mri-p0-registered-pv-pixel-pilot.yml).

Two high-priority frozen samples: `TCGA-BC-A10Y` index `tumor3`, `TCGA-DD-A4NH` index `tumor1`.

- Download exact official image/masks by bounded ZIP HTTP ranges, ZIP CRC + stored SHA256; reorient `art_pv` **voxel array** into unchanged reference-mask axes using nibabel orientation transforms; no interpolation, no artificial header rewriting.
- Perform tumor ROI intensity coverage and descriptive arterial-to-PV normalized mutual information over matched liver mask voxels to understand whether the source's pre-registered image preserves plausible anatomy. The NMI comparison is descriptive and cannot prove anatomic registration by itself.
- Compare **3 pre-locked MRI features** from original native PV and reoriented registered PV, each of two readers; both use identical PyRadiomics settings except the explicit same 0.5-mm geometry tolerance to accommodate known NIfTI rounding. The pilot is not powered to estimate a reliability ICC or select features according to gene association.
- **Only if** the pilot is reproducible should re-extraction be evaluated in all 14 with source-space provenance and full original-versus-registered feature sensitivity. Existing raw PV radiomics must remain unchanged historical technical evidence, not overwritten.
- Once image alignment and segmentation anatomy independently reviewed, clinical source timing, specimen origin, tumor lesion and eligible n must still be resolved. No MRI–RNA association allowed beforehand.

Result artifacts are private retained CI artifacts with no raw patient pixels or NIfTI files committed/uploaded.
