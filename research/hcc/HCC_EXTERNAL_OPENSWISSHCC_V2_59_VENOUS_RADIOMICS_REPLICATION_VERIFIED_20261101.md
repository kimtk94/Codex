# HCC MRI methods — complete independent 59-subject OpenSwissHCC v2 external venous MRI source replication

**Evidence frozen 2026-11-01 KST.** [GitHub Actions #41221356861](https://github.com/kimtk94/Codex/actions/runs/41221356861) **16/16 SUCCESS**: 1 fail-closed source fixture + 14 actual independent subject-MRI mask extraction shards + 1 59-person denominator/source-provenance aggregation. Source result artifact **13050138178** `hcc-openswiss-v2-external59-original-venous-radiomics-24-condition-4k-bootstrap-result`. This is external **MRI-only technical preprocessing-sensitivity corroboration**, *not* validation of HCC diagnosis, MRI-RNA pathway biology, treatment timing, patient prognosis or predictive discrimination. Clinical claim ceiling **S0**.

## Patient/ROI provenance and exact effective n

- Independent external institution/source: official [OpenSwissHCC v2 Zenodo record 21992461](https://zenodo.org/records/21992461), `acq-water phase-venous T1w`, one manually annotated HCC lesion selected per independent patient from original published lesion-size rankings, not radiomics features. LiverHccSeg `TCGA-*` study patients are not reused.
- Original public dataset: **132 people, 140 lesions, 97 HCC-labeled lesions in 63 individuals**. Exactly **90 HCC-labeled venous annotated expert ROI NIfTI masks in 59 independent subjects** matched original Zenodo derivative-archive directory under source MD5 validation; [actual official source manifest #41217646089](https://github.com/kimtk94/Codex/actions/runs/41217646089).
- **One HCC index venous lesion per each of 59 independent subjects** predetermined by maximum original `Lesion size` (ties lowest L index), **59/59** without missing size. Original SHA-verified primary index selection [#41219039484](https://github.com/kimtk94/Codex/actions/runs/41219039484), immutable 59-manifest artifact **13049177735**. The **8/90** second-reader source masks become only **3/59** second-reader selected index lesions. A two-reader ICC analysis for all 59 is NOT supported or executed.
- First four independent patients `sub-003` through `sub-006` verified [#41219978007](https://github.com/kimtk94/Codex/actions/runs/41219978007), original shard0 SHA-256 frozen source artifact **13049338566**. Reused without reselecting or re-extracting subjects.
- Fourteen additional source shards measured **55/55 remaining subjects** with HTTP range reads of original NIfTI image and mask ZIP members, not whole approximately 14.5 GB public MRI archive. All patient image/mask NIfTI source geometries <=0.5 mm affine-corner mismatch, finite nonempty expert selected ROI (minimum **118 voxels**, maximum **28,312 voxels**), and 6 fixed PyRadiomics source conditions succeeded.
- Final source denominator: **59/59 technically matched and extracted**, **0 geometry/source/extraction HOLD**, **354 case-condition rows** (59×2 spatial grids×3 binWidths), each with four features, **24 feature-condition summaries**, original case-level SHA256/geometry/selected index lesion full detail. Maximum image-mask affine corner mismatch observed **0.000832 mm**, 15 distinct exact source voxel-spacing triples.
- Original reference settings: PyRadiomics **3.1.0**; MRI `normalize=True`, `normalizeScale=100`, `symmetricalGLCM=True`, distances [1]; `native` versus **3 mm isotropic** image B-spline and expert ROI nearest-neighbor resampling; binWidth 12.5,25,50. No cross-cohort image-source intensity harmonization, imputation, statistical fitting on biology, ComBat or post-hoc patient exclusion.
- Source artifact archive member SHA256s:
  - `external_venous_59_primary_source_technical_summary.json`: `c29e84857f08f2f03de587e282ff664b43a75a66efba338406d8817fd010f7af`
  - `external_venous_59_primary_patient_source_profiles.csv`: `50de8bbaa897f99aa8b2bc9b7a0cd7d972b820e5cfaa9af4399adee4b964dba6`
  - `external_venous_59_primary_6_condition_4_feature_extraction.csv`: `65a9cbaad86ac7eca2ad9f772d3fa7f64de981349ac678187fcf76bb1b216986`
  - `external_venous_24_feature_condition_patient_bootstrap_ci.csv`: `6399e5ffaadcb16d4da0132fe67c7b2b045a34c370738408c2df0a8a97f27568`
  - `external_venous_59_source_case_level_HOLD.csv`: `fea31c8e37c2b4837ac9789d8b5cb915c207d1ad0fa6751b9ce16ea6e7543a2c`
  - Two true data-driven PNG figure members from same artifact (original GitHub Actions retention 90d): `external_openswisshcc_venous_glcm_ranked_source_sensitivity.png`, `external_openswisshcc_glcm_native_vs_3mm_same_image.png`.

## Main external measurement endpoint, fixed before inspecting 59-image features

The primary engineering endpoint, in every subject, is **`abs((3mm/bw25 GLCM Contrast - native/bw25 GLCM Contrast) / abs(native/bw25 GLCM Contrast))×100`** computed on the same manually segmented tumor/venous image. **59 independent subjects**, not 354 independent feature records; 4,000 paired-patient-with-replacement bootstrap draws, seed 20261101, simple 2.5/97.5 percentile 95% confidence intervals. This bootstrap describes source study variability, *not* a general-population or prediction-performance guarantee.

< table is descriptive only — no GLCM p-values, cutoff selection or biological inference >

| External original venous MRI setting | Patient median absolute GLCM Contrast change % [95% bootstrap CI] | Patient source-arm Spearman ρ [95% bootstrap CI] |
|---|---:|---:|
| Native / binWidth **25** reference | **0.00 [0.00–0.00]** | **1.000 [1.000–1.000]** |
| Native / binWidth 12.5 | **233.72 [221.69–253.39]** | **0.996 [0.988–0.998]** |
| Native / binWidth 50 | **63.82 [61.71–65.70]** | **0.953 [0.890–0.981]** |
| **3 mm / binWidth 25** | **64.64 [56.75–74.44]** | **0.941 [0.886–0.966]** |
| 3 mm / binWidth 12.5 | **489.50 [450.16–543.50]** | **0.945 [0.894–0.967]** |
| 3 mm / binWidth 50 | **46.15 [44.42–49.61]** | **0.898 [0.804–0.948]** |

Main 3mm/bw25 source-relative **signed median +64.635863%**; full patient absolute range **12.978–168.192%**. **59/59** subjects have >10% abs change; **55/59** >20% change. A higher ICC with two readers cannot be inferred because only one external rater mask was used for the cohort.

Four source-locked features' observed external **3mm/bw25 median absolute change** compared with original venous native/bw25 baseline:

| Feature | Median absolute change (95% independent-person bootstrap interval) | Patient rank ρ |
|---|---|---:|
| **GLCM Contrast** | **64.64% [56.75–74.44]** | **0.9408** |
| GLCM Joint Entropy | **4.73% [3.77–6.46]** | 0.9388 |
| First-order Entropy | **2.72% [1.66–3.93]** | 0.9781 |
| First-order IQR | **3.64% [2.67–5.37]** | 0.9770 |

**Interpretation:** GLCM Contrast and gray-level binning change materially in both independent image cohorts, but the variation is **feature-specific**, not proof that all radiomics measurements are unreliable. Also the original registered LiverHccSeg `art_pv` n14 main shift for native→3mm bw25 was **86.594% [76.400–97.878]**, versus Swiss native venous n59 **64.636% [56.754–74.436]**. These intervals arise from different image source preprocessing, lesion sampling, acquisition voxel anisotropy and institutions. The patient-cluster percentile intervals' apparent separation is **not** a predeclared formal cohort-difference hypothesis test or causal evidence. Do not label 22.08% original **raw-PV versus arterial-registered PV** difference as independently replicated: Swiss uses original native venous and does not contain the same paired author-registered versus raw-PV source contrast.

## Scientific quality gates and limitations

| Gate | Observed evidence | Decision |
|---|---|---|
| Original external HCC venous lesion source masks | 90 unique official files in 59 independent HCC subjects | PASS source files |
| One source-size-determined index lesion/person | 59/59; 0 selection HOLD | PASS frozen source cohort |
| Original NIfTI exact source and mask geometry | 59/59, 0 HOLD; maximum corner discrepancy 0.000832 mm | PASS technical geometry |
| Six original source conditions and four features | 354 source rows, 24 condition point estimates and 4k person-bootstrap CI | PASS numerical technical processing |
| Independent MRI protocol/method result | Large native→3mm source effect in n14 and independent n59 | **GO descriptive external MRI methods corroboration**, not phase-specific external source replication |
| Generalized MRI harmonization/translatability | Acquisition sequence and registration workflows differ, no reader validation of every lesion, no proper cross-site calibration | HOLD external clinical generalization |
| Case-level GDC HCC RNA aliquot and pretreatment MRI | Original TCGA source not clinically verified for same index lesion and therapy timeline | HOLD clinical pairing |
| Biological MRI–RNA test plan (3 frozen MRI × 4 Hallmark) | 0/12 original predeclared tests run | STOP; claim ceiling **S0** |

No diagnostic AUC, progression or survival outcomes, no tested HCC therapeutic benefit, no causal impact of MRI acquisition parameters, and no 59-person external expert reader consensus were inferred. External HCC labeled lesion masks are original source annotations but **independent qualification of tumor anatomy is NOT_ASSESSED**.

## Next high-value steps (do not skip scientific gates)

1. Publish a clear methods Figure combining the **original n14** registered source arm with the **independent n59** original venous arm for identical native-to-3mm grid comparisons, with full per-cohort observation counts, independent confidence intervals and no biological claims. Two additional single-cohort figure PNGs are already in the original artifact.
2. Sensitivity study for small ROI/partial-volume effects using source-verified n59 per-patient **original manual mask voxel counts**; predeclare Spearman/LOO descriptive only and report original image voxel spacing. Do not confuse resampled ROI count with actual tumor volume.
3. Check the handful of second-reader independently delineated selected HCC lesions (only n=3 primary) for quantitative reader consistency as an *illustrative quality-control subset*; avoid a generalizable ICC conclusion.
4. Seek independent abdominal radiologist review of original TCGA/LiverHccSeg ART/PV images and original scan-to-HCC-treatment-to-RNA sample identity. Without this, **MRI–RNA remains HOLD**, regardless of MRI-only source replication.

Run reproducibility: [external original patient source extraction](ci/mri_external_openswisshcc_v2_cohort_radiomics_sharded.py), [59 source accounting and statistical aggregator](ci/mri_external_openswisshcc_v2_59_shard_aggregate.py), [59-source immutable original patient selection](HCC_EXTERNAL_OPENSWISSHCC_V2_59_PRIMARY_VENOUS_HCC_LESIONS_FROZEN_20261101.md), [15-shard workflow](../../.github/workflows/hcc-openswisshcc-v2-external-59-original-venous.yml), [fully qualified source archive run](https://github.com/kimtk94/Codex/actions/runs/41221356861).
