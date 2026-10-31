# HCC External OpenSwissHCC v2 — First source-verified real HCC venous MRI / mask feasibility

**Checkpoint 2026-11-01 KST. Original real source CI [#41218370090](https://github.com/kimtk94/Codex/actions/runs/41218370090): 2/2 PASS.** This is **n=1 image-only pipeline feasibility**, explicitly **NOT a successful external replication study, RNA-pathway association, diagnostic validation, or clinical-tissue eligibility**. Publication claim ceiling **S0**.

## External cohort source access actually verified before the pilot

Official [OpenSwissHCC v2 Zenodo 21992461](https://zenodo.org/records/21992461) metadata and derivative ZIP source integrity passed [#41217646089](https://github.com/kimtk94/Codex/actions/runs/41217646089) **2/2**: 132 unique patients, 140 annotated lesions, 97 HCC-labeled lesions in 63 patients. `annotation_status.tsv` includes 90 HCC-specific venous lesion masks across **59 distinct subjects**; all 90 manual first-reader mask paths exist in the **MD5 verified 113.8 MB derivative ZIP**. Eight of 90 have an actual second-reader venous mask. Original 90 candidate mask manifest GitHub artifact **13048738836**. These are not 59 verified individual MRI/ROI geometries or 59 completed radiomics analyses.

No member of original LiverHccSeg `TCGA-*` was used; external OpenSwissHCC subject identifiers are `sub-###`. Original full three NIfTI source ZIPs total ~14.5 GB, but the real pilot used **HTTP byte-range reads of only selected image/mask members**, not a whole 4.9 GB ZIP.

## One actual primary HCC lesion and source imaging pair

Case: **OpenSwissHCC `sub-003`, lesion `L1`**, official `acq-water phase-venous` (native venous series, **not** re-labelled or synthesized as LiverHccSeg arterial-reference `art_pv`).

- Original image: `sub-001-sub-044/sub-003/dyn/sub-003_acq-water_phase-venous_T1w.nii.gz`, SHA256 **`af04138045a8c96cba88bd854c88c0f36ca2d5ded98ded7161d100b45dbd9d22`**.
- Original manual lesion mask: `derivatives/manual_lesion_annotations/sub-003/dyn/sub-003_acq-water_phase-venous_T1w-L1_seg.nii.gz`, SHA256 **`27dcf98a8c785eb544a8714872612387dab68068a3f6555019259959a184e5e9`**.
- MRI and expert lesion-mask NIfTI shapes both **320×260×72**, original source image pixel spacing **1.1875×1.1875×3.0 mm**, physical corner affine mismatch **0 mm**, nonzero binary lesion mask **136 voxels**. This is geometric/technical verification only, not independent radiologist anatomical approval.
- Exact PyRadiomics distribution **3.1.0**, normalized `normalize=True` / `normalizeScale=100`, symmetric GLCM with voxel-neighbor distance `1`. Same bin widths 12.5/25/50 and original native vs BSpline `3mm isotropic` with nearest-neighbor mask resampling.

| External native venous source configuration | GLCM Contrast | GLCM Joint Entropy | First-order Entropy | First-order IQR |
|---|---:|---:|---:|---:|
| Native spacing, binWidth12.5 | 7.085260 | 5.977335 | 3.353145 | 44.663440 |
| **Native spacing, binWidth25** | **1.957960** | 4.510951 | 2.408422 | 44.663440 |
| Native spacing, binWidth50 | 0.671637 | 2.999504 | 1.559299 | 44.663440 |
| 3mm isotropic, binWidth12.5 | 13.546184 | 4.110209 | 2.979471 | 39.541342 |
| **3mm isotropic, binWidth25** | **3.048320** | 3.444001 | 2.032488 | 39.541342 |
| 3mm isotropic, binWidth50 | 0.962751 | 2.660049 | 1.439628 | 39.541342 |

One lesion technical effect: **GLCM Contrast +55.688595%** on switching native/bw25 to 3mm/bw25. This is **one observed data point**, not a confidence interval, a rank-based study, HCC clinical risk, a guarantee that same effect occurs in 59, or equivalence of two cohort registrations.

Original execution artifact: `hcc-openswiss-v2-one-subject-original-venous-2x3-pyradiomics-pilot`, ID **13048834533**, source 6-row CSV and provenance JSON, [download at original run](https://github.com/kimtk94/Codex/actions/runs/41218370090).

## Essential scientific design for the actual 59-source MRI external replication

1. Freeze **at most one index HCC lesion per independent subject** using published **numeric lesion size only** (largest first; ties smallest source L index), *before* examining any source radiomics values. All 90 lesion masks may be listed as a secondary within-subject sensitivity analysis; do not claim n=90 independent patients.
2. Actual venous image existence, image/mask NIfTI affine tolerance, ROI voxel count and source MD5/SHA must pass case-by-case. The 59 is a **source candidate upper bound**, not yet the qualified analysis sample size.
3. Use native/bw25 versus 3mm/bw25 and binWidth12.5/50 only on each official original Swiss venous image; retain the full source processing contrast and different reference registration spaces as caveats.
4. Report patient-level paired-source feature change distributions, 95% patient resampling CIs, patient-rank Spearman and technical failure/missing counts; **do not pick a favorable lesion/parameter after looking at texture changes**.
5. A separate true external two-reader ICC is permissible **only** for HCC tumors with two actually matched independent expert masks, presently **eight total venous mask candidates**, not an assumed 59-reader study.
6. **MRI–RNA stays HOLD**: these Swiss cases do not supply confirmed same-lesion tumor RNA data in this project. Original 12 prelocked tests 0/12; S0.

**GO**: OpenSwissHCC v2 source accessibility, HCC venous manual-mask family and first original-image pilot feasibility. **HOLD**: 59-case aligned image-mask QC and actual cohort-level external radiomics replication. **STOP**: unverified biological imaging–RNA or diagnostic utility assertions.
