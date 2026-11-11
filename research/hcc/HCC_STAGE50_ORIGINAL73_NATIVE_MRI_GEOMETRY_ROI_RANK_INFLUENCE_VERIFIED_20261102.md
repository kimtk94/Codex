# HCC Stage 50 — Native MRI thickness, ROI volume and GLCM rank sensitivity (source-verified)

**Evidence date:** 2026-11-02 KST. **Actual successful CI:** [GitHub Actions #41461359646](https://github.com/kimtk94/Codex/actions/runs/41461359646), full original-source verification **SUCCESS**. Archive artifact **13150285593**, ZIP SHA256 `4f5985ad23fe441af909c530d6086a1e2294c4fdd90f9cb6f6f207849108ce15`.

## Frozen original source and statistical unit

- Internal LiverHccSeg/TCGA-LIHC native portal venous original n=14, one original frozen index tumor, rater1 mask per patient. Real full original 28-rater source measurement extraction [#41161863748](https://github.com/kimtk94/Codex/actions/runs/41161863748) and independently reproduced paired reader1/reader2/reader-mean original GLCM ranks [Stage49 #41448904879](https://github.com/kimtk94/Codex/actions/runs/41448904879). Frozen native through-plane spacing and native original rater1 ROI volume from `HCC_MRI_PV_14_NATIVE_3MM_ROI_VOLUME_AND_PRIMARY_FEATURE_CHANGE_20261031.csv`.
- Independent OpenSwissHCC original HCC portal venous n=59, one original index lesion primary mask per person, original 3-axis image spacing and voxels from `HCC_EXTERNAL_OPENSWISSHCC_V2_59_INDEX_PATIENT_GLCM_NATIVE3MM_FROZEN_20261101.csv` [source #41221356861](https://github.com/kimtk94/Codex/actions/runs/41221356861). Original ROI physical volume derived from **original mask voxel count × original voxel volume /1000**; not the resected tumor pathology volume.
- Source original Stage49 **14/14** patients, internal rank ρ **0.810989010989**, original external 59 **0.940794856809**, reproduced exactly from original paired native versus 3mm PyRadiomics GLCM feature values.
- **No original MRI re-download, no feature re-extraction, no new expert review, no MRI-RNA biology test.** Across 14+59 original independent subjects = 73, not 73 scanner test–retest pairs.

## Primary post-results influence result: TCGA-BC-A10Y

| Original native PV reader1 metric | All 14 | A10Y excluded, 13 (posthoc sensitivity) |
|---|---:|---:|
| Native↔3mm GLCM Contrast patient-rank Spearman ρ | **0.810989** | **0.895604** |
| Median patient absolute GLCM Contrast percentage drift | **74.880823%** | **75.651031%** |

Removal of **one specific leverage case** changes rank ρ by **+0.084615** and absolute magnitude drift median by just **+0.770208 percentage points**. This calculation **recomputes ranks among the remaining 13 patients**; it is not simply dropping one observation from precomputed 14-person ranks. **No automatic exclusion:** n=14 remains the primary frozen denominator; n=13 is a posthoc influence sensitivity result.

A10Y uniquely has original through-plane slice spacing **10.8mm**; other 13 have **≤3.5mm**. Its frozen source original selected index lesion is **tumor #3**, native rater1 ROI volume **740.186622 mL**, absolute GLCM Contrast drift **17.6975%** and native→3mm patient ordering displacement **6 rank places**. Median native original internal rater1 ROI volume for all 14 is **114.6435425 mL**, and median source through-plane spacing **2.625mm**.

The exceptional thickness and large ROI occur **in the same patient**, so slice thickness and tumor size cannot be disentangled in this single case. The lower relative magnitude drift accompanying a large rank change shows that **percentage feature stability and rank stability are separate estimands**.

## Eight exploratory geometry/rank correlations (Spearman, no p-values)

All metrics below are **POST-RESULTS descriptive checks**, not prespecified causal hypotheses; no p-values, multiple-comparison claims or external scanner-equivalence inference.

| Cohort | Source covariate | Descriptive association with | Spearman ρ | LOO ρ range |
|---|---|---|---:|---|
| TCGA-LIHC n14 | Original native z spacing | Absolute GLCM drift | **−0.575** | −0.646 to −0.465 |
| TCGA-LIHC n14 | Original native z spacing | Absolute patient rank displacement | **0.298** | 0.108 to 0.536 |
| TCGA-LIHC n14 | Native rater1 mask ROI volume | Absolute GLCM drift | **−0.051** | −0.242 to 0.126 |
| TCGA-LIHC n14 | Native rater1 mask ROI volume | Absolute patient rank displacement | **0.014** | −0.204 to 0.109 |
| OpenSwissHCC n59 | Original native z spacing | Absolute GLCM drift | **0.075** | −0.014 to 0.110 |
| OpenSwissHCC n59 | Original native z spacing | Absolute patient rank displacement | **0.014** | −0.023 to 0.055 |
| OpenSwissHCC n59 | Original native mask volume | Absolute GLCM drift | **0.094** | 0.057 to 0.139 |
| OpenSwissHCC n59 | Original native mask volume | Absolute patient rank displacement | **0.011** | −0.036 to 0.049 |

No covariate's descriptive rho should be interpreted as a scanner effect, cause of feature instability, patient-level risk biomarker, or proof of voxel-grid extrapolation. n14 and n59 have different acquisition and segmentation contexts, ROI volumes and effective slice-thickness distributions; the independent cohorts are not automatically exchangeable. The inferential strength of rho −0.575 with only 14 subjects and one z=10.8mm outlier is weak, and the n59 correlation has a distinct source geometry distribution. We did not test inter-cohort rho differences or multiplicity-adjusted hypotheses.

## Thesis scientific interpretation / decision

**HCC MRI-only methods MSc direction: CONDITIONAL GO; final submission: HOLD.** The supported contribution is quantification of **large radiomic feature magnitude drift with heterogeneous and case-sensitive patient-rank preservation**, across independently obtained original HCC portal-venous MRI cohorts. Avoid blanket statements that ranks always remain stable: source n14 rater1 rho 0.811, external n59 rho 0.941, n14 A10Y-exclusion sensitivity rho 0.896.

**M1 remaining:** independent sources' exact scanner, image intensity normalisation, ROI physical sizes and through-plane geometry are heterogeneous. The provenance-complete descriptive sensitivity analysis is not enough to infer mechanism or define a universal 3mm feature selection recommendation. Report native spacing and ROI volumes, bootstrap uncertainty and influence diagnostics; do not call post-results exclusion a new primary cohort.

**M2 remaining:** independent qualified abdominal radiologist blinded original MRI index-lesion phase/contour review, or explicitly restrict paper to computational measurements under published masks, with no new anatomical validation claim.

**M3 remaining:** direct full-text and Supplementary Methods review of existing HCC MRI reproducibility, bin width and 3mm-resampling papers to establish a limited defensible novelty gap. Crossref six-article bibliography verification in Stage48 does not establish methods originality.

**Original MRI–RNA radiogenomics remains clinically unqualified:** MRI before all relevant HCC treatment not verified, selected MRI index tumor ↔ GDC sequenced RNA specimen portion not proven. Clinically eligible patient n **NOT_ASSESSED**, biological tests **0/12**, claim ceiling **S0**.

## Machine-readable CI outputs

- `stage50_frozen73_patient_geometry_roi_rank.csv` — each person's original native through-plane spacing, native ROI volume, two GLCM features, patient rank/displacement, sample provenance and clinical S0.
- `stage50_geometry_roi_spearman_descriptive_correlations.csv` — 8 source correlations and full leave-one-patient-out bounds, explicit posthoc status.
- `stage50_A10Y_rank_influence_and_roi_volume_summary.json` — 14 vs 13 source influence result and full 14+59 original cohort bookkeeping.
- `stage50_HCC_MRI_acquisition_ROI_rank_influence_report.md` — GitHub-generated comparison.

Code `research/hcc/ci/mri14_stage50_geometry_rank_influence.py`; CI `.github/workflows/hcc-stage50-native-mri-geometry-rank-influence.yml`. First initial failed run was a literal quotation syntax error in the Markdown report (no statistical computation). Corrected and audited final CI run **#41461359646 SUCCESS**, with all source guards PASS.
