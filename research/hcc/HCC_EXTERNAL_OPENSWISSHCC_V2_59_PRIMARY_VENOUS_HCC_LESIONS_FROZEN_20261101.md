# HCC OpenSwissHCC v2 — frozen one manual HCC venous lesion per 59 independent subjects

**2026-11-01 KST.** [Source-only original GitHub Actions #41219039484](https://github.com/kimtk94/Codex/actions/runs/41219039484) **SUCCESS**. This is independent source metadata and prespecified MRI lesion selection only. The original image-mask geometry has not been checked for all 59; external cohort Radiomics comparison is **NOT EXECUTED**. MRI-RNA 0/12, S0.

## Original verified population

- [OpenSwissHCC v2, Zenodo 21992461](https://zenodo.org/records/21992461): 132 original subjects, 140 lesions, 97 HCC-labeled lesions in 63 subjects.
- [Actual MD5-verified metadata + 113.8MB original derivatives ZIP #41217646089](https://github.com/kimtk94/Codex/actions/runs/41217646089): **90/90** HCC-labeled portal-venous lesion masks map to unique original source 1st-reader NIfTI mask paths, in **59 independent subjects**. Exactly 8 of the 90 have second-reader masks.
- Source artifact **13048738836**, member CRC and SHA256 frozen in [primary-selection verification script](ci/mri_external_openswisshcc_v2_one_lesion_per_patient.py). Original metadata `participants.tsv` official MD5 **e3df2cc4a825828d0fafdd09155a97c9**.
- **59/59** subjects have a deterministic primary lesion identified by largest original `Lesion size` in mm among those **already identified as HCC and with venous annotated mask**; ties smallest numeric L index. **0 missing-size HOLD**.
- Breakdown by number of source HCC portal-venous masks per subject: **37** subjects with one candidate, **16** with two, **3** with three, **3** with four = 37 + 32 + 9 + 12 = **90** lesion candidates.
- Only **3/59 primary selected lesions** have a second-reader mask in the actual source; the earlier **8/90 all-lesion** count must not be misreported as 8 eligible two-reader independent subjects for the primary paired study.
- Actual source selection artifact **13049177735**, `hcc-openswiss-v2-source-verified-largest-venous-lesion-one-per-patient`, includes (a) **59 independent primary subject/lesion IDs and source original mask filenames**, (b) all 90 candidates with selected=TRUE/FALSE and original size, and (c) complete source-state JSON. Time-limited GitHub Actions artifact; all input metadata and the deterministic algorithm are publicly retrievable.
- Workflow [`.github/workflows/hcc-openswisshcc-v2-primary-index.yml`](../../.github/workflows/hcc-openswisshcc-v2-primary-index.yml) validates no outcome-based selection. This selection uses no GLCM change/reader ICC/biological phenotype.

## What this source selection does and does not establish

The 59 indices are **frozen technical source candidates** but not yet 59 successful original venous image–mask pairs. It does **not** establish image voxel alignment, mask area quality, venous phase source correctness, accessible original 4–5GB ZIP member, presence of independent double-reader pairs, clinical eligibility or any MRI–RNA data.

One-source feasibility [OpenSwiss `sub-003/L1` original venous MRI mask](HCC_EXTERNAL_OPENSWISSHCC_V2_FIRST_REAL_VENOUS_PILOT_20261101.md) has already achieved 0 mm affine corner mismatch, valid 136 voxel HCC segmentation and six PyRadiomics measurement conditions [#41218370090](https://github.com/kimtk94/Codex/actions/runs/41218370090) **2/2 PASS**; GLCM Contrast **+55.688595%** for 3mm vs native bw25. This observation is **n=1**, not source cohort replication.

The full technical replication pilot uses a **fail-closed 4-patient smoke-test first** and separate source ZIP HTTP-range reads of individual venous `acq-water` NIfTI files. No whole 14.5GB image archive download is necessary; missing source image, affine mismatches, too-small/nonfinite lesion ROI or extractor exceptions become explicit **HOLD**, never a silently omitted subject. [4-person multi-case smoke test](https://github.com/kimtk94/Codex/actions/runs/41219978007) must be checked before starting any 59-patient source extraction and before reporting validated technical n.

**Original LiverHccSeg imaging methodology remains distinct:** OpenSwiss native venous originals and anatomical transformations are not LiverHccSeg's official arterial-registered PV source. A replicated 3mm/bw25 within-image GLCM Contrast shift is an external *voxel grid/discretization robustness* experiment, not proof of the original HCC raw PV vs official registered PV source difference of ~22.08%. There is currently no verified clinical/tumor tissue connection for any MRI–RNA pathway test; retain source claim ceiling S0.

## Source-safe GO/HOLD next gate

**GO:** original 90 manual HCC portal-venous mask files, 59 independent one-index selected subjects, 1 actual paired venous HCC image/mask source PyRadiomics pilot.

**HOLD:** every remaining patient's original MRI/ROI anatomical coordinate and tumor mask pixel validation, multi-patient source effect distribution, 59-person external result, full second-reader ICC (only 3 selected primary have second-mask provenance), scanner/processing differences.

**STOP:** clinical MRI-RNA associations, ComBat with arbitrary missing labels, outcome-driven image feature/ROI selection, claiming n=90 independent subjects or 59 clinically eligible radiogenomics patients.
