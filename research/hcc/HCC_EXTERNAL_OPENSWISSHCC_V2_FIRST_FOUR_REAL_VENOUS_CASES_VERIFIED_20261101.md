# HCC OpenSwissHCC v2 — First four real independent venous MRI sources, 24 PyRadiomics measurements

**Validated 2026-11-01 KST. Original GitHub Actions [#41219978007](https://github.com/kimtk94/Codex/actions/runs/41219978007): 2/2 SUCCESS.** Four real HCC-positive source-size-preselected **independent** subjects, one original public manual HCC venous lesion per subject; **4/4 source image-mask geometry and six configurations pass; zero HOLD.** Publication scientific claim ceiling **S0**. This is an **MRI-only external technical feasibility smoke-test**, *not* a full 59-patient external radiomics study and not an external validation of diagnosis/therapy/biology.

## Previously source-verified independent cohort and frozen selection

- Original separate public institutional OpenSwissHCC **v2** source (Zenodo record [21992461](https://zenodo.org/records/21992461)); 132 subjects, 140 lesions, 97 HCC-labeled lesions in 63 subjects. Official HCC venous expert lesion masks **90/90** source ZIP member paths verified, spanning **59 different individuals**, 8 second-reader masks among all 90.
- Source-selected primary subset frozen **59/59** subjects, 1 venous HCC lesion per subject by largest original published lesion size, ties lowest L number, **0 missing-lesion-size HOLD**. [Actual one-index source-selection PASS](https://github.com/kimtk94/Codex/actions/runs/41219039484), original selection artifact **13049177735**.
- Patient source IDs `sub-003`, `sub-004`, `sub-005`, `sub-006` are the **first four in the frozen sorted roster**. No post-hoc selection on texture change or clinical outcomes.
- Source images are `acq-water phase-venous T1w`; **not** artificially relabeled as the LiverHccSeg original author's arterial-reference `art_pv`. Exact source ZIP NIfTI paths, image/mask SHA256 and physical-space corner offset are in the source artifact.
- Original #41219978007 artifact **13049338566**, `hcc-openswiss-v2-4-patient-real-venous-radiomics-source-shard0`. Three members with full SHA256: `external_hcc_venous_pyradiomics_shard_0.csv` `6179a25aa92ef22946df5d6e43c51dcc1069580e0dee27fd2fe1842ac2eb129e`, `external_hcc_venous_source_hold_shard_0.csv` `fea31c8e37c2b4837ac9789d8b5cb915c207d1ad0fa6751b9ce16ea6e7543a2c`, `external_hcc_venous_source_shard_0.json` `b44517d3544bfb825887644c8935c202ee3e3c5401f47119340fa4fc10deed53`. Do not treat the 90-day artifact as permanent repository source data.
- Exactly **24 measurements** (4 independent subjects ×6 [native, 3mm]×[binWidth12.5,25,50]). Each has **four** original PyRadiomics features. Image B-spline vs mask nearest-neighbor 3mm interpolation, version **3.1.0**, fixed source normalization and GLCM settings consistent with the 14-case methods protocol. No RNA feature/biological test.

## Actual imaging and source measurement results

Primary technical percentage change is `100×(3mm_bw25 GLCM Contrast−native_bw25 GLCM Contrast)/abs(native_bw25 GLCM Contrast)` in the **same original OpenSwiss HCC venous image and same expert lesion mask**.

| Source HCC patient | Original manual ROI voxels | Native GLCM Contrast binWidth25 | 3mm GLCM Contrast binWidth25 | Signed source percentage shift | Max image-mask physical affine corner mm |
|---|---:|---:|---:|---:|---:|
| `sub-003` / `L1` | **136** | **1.957960** | **3.048320** | **+55.6886%** | 0 |
| `sub-004` / `L1` | **173** | **0.690247** | **1.094321** | **+58.5406%** | **0.000229** |
| `sub-005` / `L1` | **3,870** | **0.652649** | **1.099964** | **+68.5384%** | 0 |
| `sub-006` / `L1` | **6,151** | **0.333020** | **0.420784** | **+26.3542%** | **0.000017** |

Image and manual lesion mask source NIfTI shape and image affine were validated per patient; **zero technical HOLD or failed records**. This small four-case convenience sample has high heterogeneity in source ROI volume (136→6151 voxels) and relative texture changes (26.4→68.5%). No cohort-level CI, patient ranking, inference or ICC is claimed from this smoke test. A previously validated separate `sub-003` single-case pilot [#41218370090](https://github.com/kimtk94/Codex/actions/runs/41218370090) reproduces the exact `sub-003` source values, further grounding the reused case.

## Full 59-independent-subject rollout: precommitted plan and gate

[59-person GitHub Actions](https://github.com/kimtk94/Codex/actions/workflows/hcc-openswisshcc-v2-external-59-original-venous.yml) uses the exact pilot shard0 artifact **without recomputation** and 14 further shards for the remaining 55 source-frozen independent subjects. Only individual HCC original venous image/mask compressed NIfTI members are fetched by ZIP HTTP range, not complete `sub-001-sub-044.zip` etc.

The [full 59-case aggregate](ci/mri_external_openswisshcc_v2_59_shard_aggregate.py) fails closed on original metadata selection SHA, the pilot artifact's three exact SHA256, missing or duplicated patients, zero/partial 6-condition case cell outputs, original mask NIfTI path, source phase, clinical claim contamination and source SHA/mask inconsistencies. Every one of 59 is either a technically verified original venous image-mask case with six radiomics settings, or explicitly source-HOLD with an error category. If 10 or more people qualify for technical descriptions, report 24 feature-condition changes, median abs, source-rank Spearman and **4,000 patient-clustered bootstrap intervals**, not 6×n pseudo-independent scans. The full external arm is the **original native portal venous MRI** and cannot prove that the Swiss originals reproduce the original LiverHccSeg **raw-vs-registered** image source effect of 22.08%; it tests *within-source voxel grid and binWidth sensitivity*.

Do not claim a two-reader external ICC for 59 people: only **3 of 59 preselected primary index tumors** have a second-reader mask. In external technical study, a stable native→3mm texture shift may support preprocessing sensitivity transfer, **not** a clinical biomarker, prognostic MR, correct index tissue, causation, or real world generalizability.

**Scientific status:** Source-feasibility **PASS (n=4)**. External 59-person methods study **pending full CI and patient accounting**. Original 14-person clinical MRI–RNA matched n **NOT_ASSESSED**, locked MRI–RNA hypothesis tests **0/12**, claim ceiling **S0**.
