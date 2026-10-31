# HCC P0 — source pixel identity in TCGA-G3-AAV7 vs TCGA-BC-A10Y

**Actual public-source verification: 2026-10-31 KST.**
[GitHub Actions #41193062797](https://github.com/kimtk94/Codex/actions/runs/41193062797), **3/3 jobs SUCCESS**, source-only clinical ceiling **S0**.

## Motivation and prespecified comparison

The complete [14-person registered-versus-raw PV comparison](HCC_MRI_P0_ALL14_REGISTERED_PV_SOURCE_SENSITIVITY_REPORT_20261031.md) showed **zero changes across all 10 radiomics features** in case `TCGA-G3-AAV7` after orienting official `art_pv` into the source tumor reference frame. A10Y, with fixed `tumor3`, provides a contrast case with substantial GLCM Contrast change.

The ZIP-compressed source NIfTI hashes differ between each original and registered image. Different compressed/source-file hashes, however, **do not prove distinct voxel intensities** because header metadata, reorientation and compression bytes can change without changing biological pixel arrays.

Read official LiverHccSeg v1.1 `pv.nii.gz`, `art_pv.nii.gz`, both expert ROI masks and the rater1 liver segmentation from the source archive, with per-member ZIP CRC. Reorient `art_pv` to original mask coordinates by signed voxel-axis flips only; no interpolation at this comparison stage. Calculate exact voxel equality (not merely rounded difference) separately within each selected ROI, whole liver and whole volume. Freeze case choice and A10Y source SHA from the previous pilot where available. Do not export image pixel arrays or promote clinical eligibility.

## Actual results

| Fixed subject | Region | Comparable voxels | Exact pixel equality | Mean absolute raw-registered difference |
|---|---|---:|---:|---:|
| `TCGA-G3-AAV7`, tumor1 | rater1 selected tumor | 1,898 | **100.0000%** | **0.0000000** |
| `TCGA-G3-AAV7`, tumor1 | rater2 selected tumor | 1,893 | **100.0000%** | **0.0000000** |
| `TCGA-G3-AAV7`, tumor1 | rater1 liver | 409,730 | **100.0000%** | **0.0000000** |
| `TCGA-G3-AAV7`, tumor1 | full 3D volume | **8,064,000** | **100.0000%** | **0.0000000** |
| `TCGA-BC-A10Y`, tumor3 | rater1 selected tumor | 124,420 | **3.420672%** | 14.2640331 |
| `TCGA-BC-A10Y`, tumor3 | rater2 selected tumor | 135,739 | **3.378543%** | 14.5693426 |
| `TCGA-BC-A10Y`, tumor3 | rater1 liver | 374,753 | **2.805848%** | 15.8733086 |
| `TCGA-BC-A10Y`, tumor3 | full 3D volume | 3,735,552 | **6.391880%** | 15.8071592 |

All comparisons use source intensity units. They are **not** registered image quality measures, disease effect sizes, or a normalization between scanner settings.

**Confirmed finding:** AAV7 raw PV and axis-reoriented registered `art_pv` have exactly the **same pixel array over the entire 3D FOV**, even though the NIfTI source SHA-256 differs. Hence its zero source-phase radiomics differences are a real pixel-level invariance and not a feature-extractor bug. Do **not** infer why no voxel intensity changed—registration may have been unnecessary, an identity transform used, or a distinct dataset export pathway; source authors' documentation would be required to identify the mechanism.

**A10Y control:** >96% of tumor ROI pixels are nonidentical, and the absolute difference is appreciable. This demonstrates that at least some subjects' official registered/source images contain genuinely different intensity arrays. It does **not** establish that every changed voxel is biologically meaningful, anatomically matched, or perfectly registered.

## Claim guard and next work

- `HCC-12`: **PARTIAL**, not PASS clinical/source anatomy.
- `HCC-13`: **PARTIAL**, scientific claim not upgraded by high two-rater ICC.
- `HCC-14`: **PARTIAL**, MRI timing relative to treatment not established.
- `HCC-17`: **PENDING**, eligible MRI/RNA paired n **NOT_ASSESSED**.
- `HCC-20`: **PENDING**, all prelocked 12 MRI–RNA association tests **NOT_EXECUTED**.
- Next actions: report exact source registered provenance and ROI images for an independent qualified anatomical reader; obtain case-level treatment/tissue chronology, and consider an explanatory request to dataset authors for the AAV7 identity export behavior.

Machine evidence: GitHub Action artifact `hcc-mri-p0-aav7-a10y-official-pixel-identity`, artifact ID **13039453477**, including `hcc_aav7_vs_a10y_source_pixel_identity.json`. Full image contents were not uploaded.
