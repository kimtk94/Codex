# HCC MRI × RNA research V3 decision — source-phase evidence vs clinical eligibility

**Decision updated 2026-10-31.** The original V2 plan's "MRI source-space discrepancy" is now **technically resolved** on 14 source cases; the blocking problem has shifted to **case-level anatomy and clinical linkage**. No imaging methods milestone is equivalent to MRI–RNA cohort approval.

## Evidence completed (actual GitHub Actions, not hypotheses)

| Dimension | Frozen empirical result | Correct interpretation |
|---|---|---|
| Official anatomical source-space headers | [14 patients × three MRI arms, 42 comparisons, PASS](https://github.com/kimtk94/Codex/actions/runs/41188630515) | Registered `art_pv` requires axis reorientation to fixed tumor ROI space; header pass does not validate anatomical tumor correspondence |
| Actual registered-source PyRadiomics | [14 patients × two experts × two phases = 56 feature rows, all 9 jobs PASS](https://github.com/kimtk94/Codex/actions/runs/41191599451) | Ten features, frozen index lesions, two-reader ICC from raw/registered PV |
| Locked GLCM Contrast phase sensitivity | Median absolute change **22.08%**; **11/14** source-change ≥10%, **9/14** ≥20%; registered ICC(A,1) **0.95161** | Reader reliability does **not** imply phase/source preprocessing invariance |
| Exception AAV7 | Raw and registered PV identical intensity across **8,064,000 voxels** after signed axis changes [3/3 PASS](https://github.com/kimtk94/Codex/actions/runs/41193062797) | Avoid falsely calling zero feature change an analysis or registration error |
| Exact source snapshot preservation | Original 56-row artifact, four member SHA-256, frozen changes and S0 [2/2 PASS](https://github.com/kimtk94/Codex/actions/runs/41198458859) | Reproducibility of methods extraction; artifact not clinical eligibility |
| MRI tumor anatomical review aids | 14 ART / registered PV 3-plane R1/R2 contact sheets, 14 traceable provenance rows [9/9 PASS](https://github.com/kimtk94/Codex/actions/runs/41199138622) | **0/14 qualified independent review**; image creation alone does not approve tumor anatomy |
| Qualified review evidence controls | 14 frozen cases, P0 4 / P1 5 / P2 5, five negative state tests [PASS](https://github.com/kimtk94/Codex/actions/runs/41201911353) | No eligibility without reviewer identity, evidence and date |
| GDC original treatment ↔ RNA specimen trace | 14×24 table, 9 HCC-diagnosis-context dated Yes records across 4 P0, 1 unrelated colon/appendix operation, 5 negative tests [2/2 PASS](https://github.com/kimtk94/Codex/actions/runs/41206214233) | GDC diagnosis-relative treatment-to-specimen days **cannot** be compared directly with shifted TCIA DICOM MRI acquisition days |

## Immediate study tracks

### Track A — scientifically defensible image measurement methods (technical GO)

Primary demonstrable hypothesis is that choice of **official registered PV vs historical raw PV**, voxel size and gray-level discretization can materially alter HCC MRI radiomic texture even where two expert readers agree highly. This is technically supported by actual frozen data. Keep the published MRI masks and `art_pv` official-space provenance; no gene-expression inference.

**Remaining requirements before publishable claims:** derive uncertainty intervals for paired n=14 image-source effects using patients (not 28 reader profiles) as independent resampling units; report median absolute changes, paired signed changes, per-patient rank changes, ICC confidence intervals, shape features as negative controls; inspect voxel-spacing effects and scanner contrast agent heterogeneity; obtain independent visual source registration QA; distinguish effects of nonrigid interpolation vs original acquisition changes (not isolated here). Replication with an independent image cohort and stringent method references strengthens impact. A 14-patient convenience public cohort is small; avoid a universal calibration or clinical biomarker claim.

Candidate manuscript direction: *Impact of portal-venous MRI registration and image discretization on hepatocellular carcinoma radiomic measurement reliability: a public-data reproducibility audit*. Title is provisional; significance is **technical** only, and currently capped at S0 until independent confirmation.

### Track B — original pretreatment MRI–RNA radiogenomics (clinical HOLD)

- Original 3 frozen MRI features × 4 frozen MSigDB 2025.1.Hs Hallmark signatures = **12 associations; 0/12 run**. Do not select source condition, features or participants based on RNA p-values.
- Official `art_pv` is canonical if and only if registered index lesion anatomy passes independent review; historical raw PV retained as an external data preprocessing sensitivity benchmark.
- Public GDC RNA primary-tumor sample barcode/MD5 corresponds to case ID but **not proven to be the exact tumor visible in MRI**. TCIA baseline scan being pre-surgical does not prove it was before ablation/TACE, etc. GDC relative treatment days and TCIA shifted MRI dates are incompatible without an authorized episode bridge.
- Clinical P0 group **A10Y, A4NH, A25T, AAV1**. Four independent HCC-diagnosis-context dated treatment-to-RNA specimens; the 4 are not confirmed post-treatment MRI or exclusions. A5W4 earlier Yes event belongs to cecum/appendix, not confirmed HCC therapy.
- Original SAP exploratory minimum **≥10 fully documented independent paired patients** is a procedural floor, **not adequate power**. If all P0 were later excluded, maximum possible eligible n would equal 10; one additional exclusion would block that floor. This is a conditional calculation, not an actual exclusion.
- Require an independent expert anatomical review of all 14 and source-authoritative deidentified before-/after-HCC-therapy relationship of the exact scanned index lesion to the GDC RNA sampled lesion/aliquot. If reliable patient-level mapping cannot be obtained, keep Track B on HOLD/STOP indefinitely rather than manufacturing biological association statistics.

### Track C — CT-to-RNA expansion (data access HOLD)

CT 73 case-ID-linked RNA sources do not contain 73 verified same-source HCC tumor ROIs. Do not equate liver-organ contours or scanner series presence with tumor masks; do not contour 73 patients speculatively. Retain IBSI CT phantom numerical benchmarks as separate methods reproducibility only.

## Next discrete decision gates

| Gate | Pass criterion | Current result |
|---|---|---|
| A — image technical comparison | Frozen 14 patient/56-row source features, source hashes, source-header geometry, ICC validated | **PASS** |
| A — registered ROI anatomical correctness | 14 accepted or explicitly classified by a qualified reviewer on actual three-plane source volumes, registration motion and tumor outline | **HOLD; unreviewed** |
| B — patient MRI before intervention | Case-level source-authoritative scan vs HCC interventions, not a DICOM-vs-GDC date subtraction | **HOLD; 0 documented** |
| B — same MRI index lesion sampled for RNA | Actual selected index tumor ↔ sample/portion/aliquot tissue lineage | **HOLD; 0 documented** |
| B — biological analysis | At least 10 fully eligible independent cases, original 12-test plan and multiplicity control intact | **STOP; 0/12 executed** |
| Scientific interpretation | Clinical/external replication and complete methods-level limitations | Current manuscript ceiling **S0** |

## Next useful human-dependent request

Ask the LiverHccSeg/TCIA source custodians or site-approved study experts for deidentified selected MRI `StudyInstanceUID/SeriesInstanceUID` to HCC treatment episode and resected/biopsied tumor specimen relation. Do not request patients' real identities or dates. An abdominal radiologist's image review and a biospecimen/clinical source mapping are two different approvals; obtain both. Meanwhile continue Track A's nonbiological measurement confidence intervals and full methods figures.

Detailed evidence: [registered MRI feature source-sensitivity report](HCC_MRI_P0_ALL14_REGISTERED_PV_SOURCE_SENSITIVITY_REPORT_20261031.md), [clinical source crosswalk](HCC_MRI14_GDC_RELATIVE_TIMELINE_TRACEABILITY_VERIFIED_20261031.md), [reviewer handoff](HCC_MRI14_ART_REGPV_ANATOMY_EXPERT_HANDOFF_20261031.md), [pre-outcome source SAP addendum](HCC_MRI_RNA_SOURCE_PHASE_SAP_ADDENDUM_20261031.md), and [verification ledger](HCC_VERIFICATION_LEDGER.csv).
