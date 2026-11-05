# HCC MRI14 — registered PV acquisition sensitivity source audit protocol

**Protocol frozen 2026-11-01 KST before seeing the new voxel-spacing association statistics.** Research mode: source measurement methodology; not diagnostic imaging, treatment response, risk prediction or radiogenomics. Baseline technical validation: original [14-patient 168-row 2×3 registered PV study](HCC_MRI_P0_REGISTERED_PV_2X3_FACTORIAL_14_CASE_RESULTS_20261101.md), [9/9 jobs PASS](https://github.com/kimtk94/Codex/actions/runs/41208617950). Current supplementary acquisition-source workflow: [#41214675184](https://github.com/kimtk94/Codex/actions/runs/41214675184); **completion, effect sizes and interpretations must be taken from an actually verified CI result**, not this protocol.

## Scientific reason and source-metadata mismatch to prevent

Original historical `pv.nii.gz` voxel spacing is archived in `HCC_MRI_14_PV_NATIVE_SPACING_QC_20261031.csv`. The canonical official **registered** portal venous source is **`art_pv.nii.gz`**, reoriented into published arterial tumor mask coordinates. Its physical header spacing **has not yet been verified as numerically identical** to the raw `pv` image; therefore never label raw-PV spacing as the actual registered-PV spacing.

In this audit, re-read all 14 **actual original official `art_pv.nii.gz` source members** and the selected frozen reader1 index tumor masks from LiverHccSeg Zenodo v1.1. Use exact source member decompression, SHA256 digest, rigid voxel-axis orientation correction, image-to-mask affine corner tolerance 0.5 mm, and calculate voxel spacing **using norms of the 3 affine basis columns** (post-orientation). Match registered PV image and reader1 mask SHA to the **original 168-row GitHub Actions source** (not only sample ID) before any descriptive analysis. Keep historical raw PV spacing as a separately labeled comparator.

### Frozen data and outcome-blind analysis

- Population: **exactly 14 predetermined TCGA-LIHC cases**, selected tumor3 for A10Y and tumor1 for the other 13, **two fixed reader masks**. No patient exclusion, scan re-selection or source replacement based on feature change.
- Fixed primary engineering response: **absolute percentage change in GLCM Contrast** after re-extracting official registered `art_pv` with `3mm isotropic / binWidth25`, relative to registered native / binWidth25. Average the two reader feature values **within each patient before** computing per-case change; this is **n=14, not n=28**.
- Other descriptive responses: signed 3mm25 change, native binWidth12.5 absolute change, and 3mm binWidth50 absolute change. Calculated from **original 168-row SHA-pinned MRI-only data**, not molecular outcomes.
- Candidate source geometry explanatory factors: actual registered PV z-spacing (mm), actual registered in-plane mean (mm), actual registered z/in-plane ratio, registered |z–3mm|, and **separately identified** historical raw PV z-spacing (mm) as a source comparator, not a substitute. Twenty rank-correlations = five geometry variables × four measurement responses. They are **screening descriptions, not 20 confirmatory statistical tests**.
- Report Spearman rank correlation and the minimum/maximum across all **14 leave-one-patient-out** recalculations. **Do not compute or promote p-values**; with n=14 these are unstable, unadjusted descriptive relationships and can be affected by single cases. Note any sign flip across leave-one-out as an instability warning.
- Separate publication-derived *study-level* contrast-agent labels into **Extracellular n=7**, **Hepatobiliary-specific n=4**, and **unknown n=3**. Report n, median and range of four changes, **not agent-specific inferential comparisons**. Published acquisition workbook values are **not confirmed as the exact selected registered PV acquisition series**. A10Y has three official workbook rows, which are not three independent patients.
- All fourteen published-study field strength entries are **1.5T**: there is **no within-cohort field-strength variation to analyze**. The source workbook field `Contrast Agent Manufacturer` is an agent manufacturer, **not an MRI scanner manufacturer**; exact scanner vendors/sequence/coil and exact selected PV series-level agent remain unverified. Do not run scanner models, dose normalization, ComBat or multivariable regression with this data.
- The initial source-space mismatch, official nonrigid registration and independent 3mm intensity resampling can all contribute to texture differences. An association of slice spacing with 3mm effects does **not identify a causal mechanism** or imply that lost anatomical detail was restored.

### Fail-closed and interpretation criteria

| Validation gate | Required result | Meaning if missing |
|---|---|---|
| 14 original official `art_pv` NIfTI sources and frozen masks | 14 unique signed-orientation-corrected source headers, exact image/mask SHA256 match | STOP, no measured registered spacing claim |
| Engineering data baseline | 168 rows in six grid/binWidth conditions, **112/112 frozen registered native25 feature value crosschecks** from source aggregate | STOP, no merged association |
| Case-level data join | All 14 patient IDs unique, no extra/missing case, two readers averaged *inside patient* | STOP, no engineered n=28 |
| Clinical boundaries | All 14 `NOT_ASSESSED` anatomy/clinical eligibility; locked 12 MRI–RNA tests `NOT_EXECUTED`; S0 | STOP on unauthorized promotion |
| Numerical descriptive interpretation | 20 source-geometry rank/LOO rows and 12 agent group descriptives; explicit low-n and missing series labels; no p-value, no FDR | HOLD on causal or predictive interpretation |
| Scientific novelty | Source sensitivity remains methodologically credible but external replication and qualified anatomy QC absent | Methods GO, clinical biology HOLD |

**Next decision conditional on actual run:** If numerical/metadata checks all PASS, persist the exact patient/source table, 20 LOO summaries, 12 agent descriptors and a cautious descriptive methods note; if any fail, correct the source join/error before claiming scientific findings. Do not select image parameters based on downstream RNA associations.
