# HCC Stage 33 — original external venous HCC paired-reader mask source QC: real results VERIFIED

**Report date:** 2026-11-01 (Asia/Seoul)  
**Original official imaging cohort:** OpenSwissHCC v2, Zenodo 21992461.  
**Actual run:** [GitHub Actions #41224906345](https://github.com/kimtk94/Codex/actions/runs/41224906345) — **SUCCESS, all steps passed**, original source artifact **13052025505**, digest SHA256 `dbc3d616fa66865254ef8090eb6457fdecffd68e8a33bff7f8b4107895376cb8`, 90-day artifact retention; full NIfTI review panel PNGs, 3 pair measurements, HOLD CSV, and source QC JSON available in artifact.  
**Immutable three-case compact summary:** [HCC_EXTERNAL_STAGE33_3_INDEX_READER_SOURCE_METRICS_FROZEN_20261101.csv](HCC_EXTERNAL_STAGE33_3_INDEX_READER_SOURCE_METRICS_FROZEN_20261101.csv).

## Technical results using actual original source NIfTI and reader masks

| Source patient | Original selected index lesion | Dice | Pooled symmetric HD95 (mm) | Source geometry |
|---|---|---:|---:|---|
| sub-017 | L1 | 0.904796 | 1.679379 | PASS |
| sub-066 | L1 | 0.908127 | 3.000000 | PASS |
| sub-067 | L1 | 0.898405 | 1.187500 | PASS |

**Three paired source patients technically valid, 0/3 geometry/extraction HOLD.** Descriptive median Dice **0.904796**, median pooled symmetric HD95 **1.679379 mm**. The measure reported here is the 95th percentile of *concatenated bidirectional source-surface nearest-neighbor distances*, in original NIfTI image affine physical millimeter space (not the maximum of separate directed 95th percentiles). Please use that definition consistently.

## Provenance and denominator safeguards

- Full external image source: [16-of-16 PASS original n=59 image/mask extraction #41221356861](https://github.com/kimtk94/Codex/actions/runs/41221356861) and [7-member immutable result audit #41223161712](https://github.com/kimtk94/Codex/actions/runs/41223161712).
- Original OpenSwiss metadata: **90 HCC-labeled venous annotated lesions in 59 patients**; second-reader source mask available for **8/90 lesions**, but **only 3/59 frozen index lesions** possess matched second-reader masks.
- Source index selection was frozen before feature extraction, based solely on original reported largest HCC lesion size per subject. **No extra lesions substituted** to increase the two-reader sample.
- Original 59-patient source selection and 90 lesion manifest were SHA-matched to original Actions artifacts **13049177735** and **13048738836**.
- Original full 59-case extraction artifact **13050138178** source profile SHA matched. For each of three pairs, both same-patient native venous image identity and reader-1 source mask SHA-256 were matched to the original n=59 extraction; reader-2 NIfTI read from official Zenodo derivatives original path.
- Three original source-image and reader-mask NIfTI pairs passed binary segmentation, same 3D shape, nonempty finite ROI, and original source image/mask physical affine corner mismatch <=0.5mm.
- The workflow computed real original-space Dice, Jaccard, original physical mask volumes and signed volume difference, pooled symmetric HD95, mean symmetric surface distance, and independent 3 orthogonal voxel-axis overlay PNG panels. Full values and supporting figures are stored in the artifact.

## Scientific interpretation and claim levels

1. The original two-reader delineations exhibit descriptive **Dice approximately 0.90 in the three frozen index lesions**. This is *supportive illustration of within-image manual mask overlap*, not formal external-cohort segmentation reliability. Do not infer 59-subject inter-rater ICC or select a clinical acceptability cutoff after reading the metrics.
2. Pairwise mask agreement **does not certify accurate tumor anatomical inclusion/exclusion**. An independent qualified abdominal radiologist must inspect full original NIfTI series with blinded contours and record lesion identity, phase and anatomic validity. [Independent expert review protocol / checklist](HCC_EXTERNAL_59_STAGE33_READER_MASK_EXPERT_REVIEW_PROTOCOL_20261101.md) remains **PENDING**.
3. The **external MRI-method descriptive source replication** is already 59/59 for the main preprocessing change, separate from this n=3 two-reader QC.
4. MRI–RNA study **same pretreatment lesion, imaging and tumor RNA evidence remains HOLD**; frozen planned MRI–RNA biology panel **0/12 tested**. No diagnostic, treatment response, prognosis, predictive model or biological claims; ceiling **S0**.

## Stage 33 gate decisions

| Gate | Decision |
|---|---|
| Original source reader-pair provenance n=3 | PASS |
| Original venous source NIfTI and both reader masks n=3 | PASS |
| Native-space quantitative masks and 3-case reviewer screening panels | PASS |
| Independent anatomical correctness adjudication by qualified radiologist | **HOLD** |
| Generalizable independent segmentation reproducibility in n=59 | **NOT ESTABLISHED** |
| Pretreatment MRI–same tumor RNA identity | **HOLD** |
| MRI–RNA 12 Hallmark biological tests | **STOP (0/12)** |

**Next action:** arrange independent abdominal MRI expert review of source images and original masks (only 3 paired-reader examples initially; add stratified review across larger n=59 sample if inferential anatomy generalization is desired), then separately audit exact pretreatment MRI/RNA tumor/aliquot identity for any MRI–RNA association. The Stage 33 technical QC can be labeled complete; full anatomical expert qualification cannot.
