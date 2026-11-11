# HCC Stage 33 — original external HCC venous MRI dual-reader mask QC and independent expert review handoff

**2026-11-01 KST. Protocol and provenance only until the real source run is finished.** [Source-locked Stage 33 workflow](../../.github/workflows/hcc-external59-stage33-reader-mask-qc.yml) and [source computation](ci/mri_external59_stage33_two_reader_mask_qc.py).

## Exact denominators and permitted claims

- Original OpenSwissHCC v2 [Zenodo record 21992461](https://zenodo.org/records/21992461): 90 HCC-labeled portal-venous manual source masks from 59 independent subjects. 8 of the **90 lesions** have a second-reader mask.
- The frozen outcome-blind **largest index HCC lesion per patient** source selection leaves **only 3/59** selected index lesions with two reader masks. Do not promote 8/90 to 8/59 or assume all 59 cases have second-reader contours.
- All 59 independent patients remain in the prior **MRI-method technical source extraction denominator**. The paired reader subset is a **separate illustrative n=3**, *not* validation of n=59 anatomy.
- Main original venous source 59/59 analysis and SHA: [#41221356861](https://github.com/kimtk94/Codex/actions/runs/41221356861), integrity audit [#41223161712](https://github.com/kimtk94/Codex/actions/runs/41223161712).
- Freeze index selection; **do not substitute a secondary lesion** to increase the reader-pair n. Do not use radiomics outcome to choose patients or lesions.

## Technical metrics and source identity gates

1. Download only original ZIP members from the official Zenodo source using byte ranges; no entire large image archive.
2. SHA-256 check original 59-case source roster, 90-venous lesion candidate roster, and 59-case verified source profiles against frozen prior artifact digests.
3. For exactly the selected n=3, verify original first-reader mask and native venous image SHA-256 match the already validated main source run. Read second-reader exact filename from the original **90-case source preflight**, not from a guessed path.
4. Require unique original acq-water venous T1w NIfTI per patient and exactly one first and second reader mask corresponding to the same `subject/selected_lesion`.
5. Enforce same source 3D array shape, finite nonempty binary lesion labels and source image/mask corner affine discrepancies **<=0.5 mm**; otherwise **HOLD**, not silent registration/resampling.
6. Compute native-space voxel intersections, volumetric Dice, Jaccard, signed reader-2 versus reader-1 ROI volume difference (physical mL using affine determinant), and physical **95th-percentile pooled symmetric surface-to-surface distance** (mm; commonly called *pooled HD95*; state convention clearly). No 3 mm resampling for these source-to-source reader comparisons.
7. Generate three orthogonal voxel-axis display panels with colored contours from the original MRI for a review **screening** aid only. These are not independently oriented/anatomically adjudicated diagnostic images.

## External anatomical expert review — NOT YET COMPLETED

For each of 3 cases, have an appropriately qualified abdominal MRI radiologist independently inspect the complete image series and original reader masks, not merely the automatically chosen three center slices.

| Mandatory recorded item | Required evidence / status |
|---|---|
| Original MRI venous phase and source series identity | Confirm venous source and exact image UID / NIfTI identity |
| Source image anatomy / reference orientation | Original 3D image orientation and native anatomy visually inspected |
| Index lesion identity | Same source HCC lesion location for the two masks; source lesion-selection rule unchanged |
| Tumor contour correctness | Boundary, vascular inclusion, necrosis / artifacts, conspicuous non-tumor tissue assessed |
| Technical misregistration | Source mask/venous image visually overlaid in all planes; no suspicious offset |
| Reviewer ID / credentials / date | Qualified independent clinician identity and attested review |
| Disagreement / adjudication | Document reasons and second expert adjudication if clinically material |
| Review decision | APPROVE, REJECT, or HOLD with supporting notes, no inferred clinical approval from Dice |

**Review status: PENDING.** Source original annotation quality, even when independently double-read, is not equivalent to a new blinded expert adjudication.

## Interpretation and next evidence gates

- Quantitative paired segmentation metrics for **n=3** may serve as an exploratory QC case study. No cross-cohort/general-population ICC, no validated segmentation reliability cutoff, no prognostic/diagnostic utility inference.
- The n=59 MRI preprocessing effect is source verified but could still reflect source contour and acquisition differences. Do not interpret observational associations from Stage 32 as isolated causal effects.
- **MRI methods technical GO** remains separate from **independent anatomy expert HOLD** and **MRI–RNA same-tumor pretreatment clinical pairing HOLD**.
- Biological tests **0/12**, no scanner/center causal inference, clinical/biological claim ceiling **S0**.
- Once the Stage 33 real run finishes, record its exact run ID, per-case metrics, any HOLD and artifact digest in a separate immutable results report rather than overwriting this review protocol.
