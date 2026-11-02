# HCC Stage 41 — complete original DICOM vs PV NIfTI 3D source verification

**Verified run:** https://github.com/kimtk94/Codex/actions/runs/41431710438 (2 patient jobs + independent aggregate **3/3 SUCCESS**). Code commit `8cbcbe662fb38cc32e560159e4012750d0027de3`. 2026-11-02 KST.

## Source-level independent technical verification

The original LiverHccSeg v1.1 `dicoms.zip` DICOM members and original `pv.nii.gz` NIfTI sources were accessed individually with bounded HTTP Range requests. The selected original source series was determined **without any RNA outcome or MR biological result** by the frozen Stage40 strong pixel-pattern candidate. Every DICOM slice from the chosen source series was decoded, ZIP CRC checked, PatientID and SeriesInstanceUID checked, and sorted by source ImagePositionPatient projected onto ImageOrientationPatient normal. A **single fixed** 2D orientation transform and monotonic z order was used for the complete image, rather than per-slice optimization. Full-resolution pixel Pearson, normalized intensity-linear-fit residual and DICOM LPS-to-NIfTI RAS physical coordinate errors were computed for all slices.

| Original patient | Exact source DICOM slices | NIfTI dimension | Min full-resolution Pearson | Max normalized fit RMSE | Max LPS-to-RAS error | Decision |
|---|---:|---|---:|---:|---:|---|
| TCGA-BC-A3KG | **88/88** | 256×208×88 | **1.000000** | **0.0** | **0.0000064857 mm** | STRONG_FULL_3D_PIXELS_AND_LPS_RAS_AFFINE_TECHNICAL_MATCH |
| TCGA-BC-A69I | **88/88** | 320×260×88 | **1.000000** | **0.0** | **0.0000052802 mm** | STRONG_FULL_3D_PIXELS_AND_LPS_RAS_AFFINE_TECHNICAL_MATCH |

Original DICOM source SeriesInstanceUIDs:
- TCGA-BC-A3KG: `1.3.6.1.4.1.14519.5.2.1.8421.4008.707679953718282918093761171766`
- TCGA-BC-A69I: `1.3.6.1.4.1.14519.5.2.1.8421.4008.213571243455101458875039412372`

In both cases, best in-plane mode: **transpose + both flips**; sorted DICOM z order **forward**, no reversal. DICOM interslice spacing A3KG **2.5mm**, A69I **3.5mm**.

Provenance:
- Patient A3KG artifact **13135230447**, artifact ZIP SHA256 `7358e56e00f86bf6796de0e8a902db61d90e2db05e7de68a8a819dcb13bebd43`.
- Patient A69I artifact **13134368814**, ZIP SHA256 `1136ccd5455a5b577174bd55b8f3d151b2782f3d3ed30944a6fd8eca6fffe812`.
- Original Stage41 run #41431172400 had both source stacks downloaded but a missing `os` import failed results serialization. Run #41431710438 reexecuted and confirmed all final results and aggregate.
- Full original source ZIP MD5 was not independently recomputed. Direct bitwise pixel equality and independent expert anatomical review were not asserted; the observed fullres regression residual was zero with Pearson 1.0 and micron/submicron physical coordinate errors.

## Gate interpretation

**Technical original selected PV NIfTI ↔ source DICOM series linkage: 2/14 verified, 12/14 remaining.** These two results prove source-image provenance, *not* HCC treatment-naïve or exact sampled tumor.

**Clinical MRI-to-GDC RNA and treatment gate remains HOLD:** no source-authoritative evidence proving scan preceded relevant HCC treatment, nor that the frozen index MRI tumor corresponds to the same GDC tumor portion/aliquot sequenced. Independent qualified abdominal radiologist assessment not completed. **Eligible patients NOT_ASSESSED**, not zero eligible. **Biological MRI–RNA association tests 0/12; publication claim ceiling S0.**

## Next actions

Expand the 3-slice distinctive pattern ranking to the other 12 frozen TCGA-LIHC MRI patients, following fixed source-only criteria, then full-DICOM stack verification for the unique candidate per patient. In parallel obtain independent radiology and authoritative clinical/tumor-aliquot links; never infer pre-treatment status by directly subtracting TCIA shifted DICOM dates from GDC diagnosis-relative treatment days.
