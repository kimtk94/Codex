# HCC Radiomics × RNA-seq — scientific direction reset and decision gates (2026-10-31 KST)

**Status:** Decision memo, not a new hypothesis protocol or permission to run MRI–RNA associations.  
**Repository:** kimtk94/Codex, PR #228 (`feat/hcc-public-ci-20261022`, head checked `8fde9e04f962949b8ca7033c36a713cec2caa27c`).  
**Verified GitHub Actions:** [#222 / 41180175184](https://github.com/kimtk94/Codex/actions/runs/41180175184) (8 success / 15 intentionally skipped, all required source-evidence jobs successful); [expanded IBSI #214 / 41179519399](https://github.com/kimtk94/Codex/actions/runs/41179519399).  
**Mandatory source-of-truth:** [verification ledger](HCC_VERIFICATION_LEDGER.csv), [research framework](HCC_VERIFICATION_AND_PUBLICATION_FRAMEWORK.md), [locked 12-test SAP](HCC_MRI_RNA_PREOUTCOME_HALLMARK_SAP_V1.md). A successful workflow is **not** clinical eligibility.

## Executive decision

Keep the MRI–RNA pathway pilot, but move the main effort from additional software benchmark PASS counts to the actual source-authoritative **MRI acquisition → HCC therapy → tumor tissue collection / sequenced lesion** bridge. Technical feasibility is already advanced and not the limiting factor. **Claim ceiling S0**, **clinical HOLD**, **12-association tests STOP**. All 14 MRI patients remain unresolved (not “14 eligible”, not “14 excluded”). Do not conflate clinical GO with technical QC GO.

## Verified status and binding constraints

| Workstream | Observed evidence | Claim/status |
|---|---|---|
| MRI × GDC STAR primary-tumor RNA | 14 public MRI source PV image/mask technical candidates; published two-reader segmentations, source pixels/ROI overlap QC, 14 original GDC counts with file size/MD5, 4 Hallmark scores | TECHNICAL GO; same resected HCC lesion and pretherapy chronology NOT established |
| Reader & acquisition sensitivity | 10 two-reader features measured; 8/10 pass prespecified native ICC/CI/LOO screen; 14×2×2×3 = 168 configuration cells tested | Method QC GO, **numerical portability REVIEW**; GLCM Contrast native→3mm median absolute relative change ~77% and native binWidth25→12.5 ~253%; A10Y 10.8 mm z resolution outlier |
| IBSI-1 reference | Official digital phantom 10/10 PyRadiomics v3.1.0 reference comparisons matched (4 published IBSI morphological tolerances, 6 explicit LOCAL diagnostic thresholds). Independent 13-direction GLCM math verified | Phantom-specific PASS only; not full IBSI MRI preprocessing certification |
| IBSI CT source | IBSI-1 and IBSI-2 official CT image/mask SHA and geometry match, 204×201×60, ROI 125,256 | SOURCE PASS; **IBSI-1 CT A–E and IBSI-2 filtered response NOT EXECUTED**; original CT is a **lung** phantom, not HCC |
| Clinical temporal/source review | 130 GDC treatment records/14 patients; 42 Yes; 4 cases with dated treatment in HCC diagnosis context before recorded GDC tissue collection; 1 distinct other-organ surgery; no valid shifted TCIA/GDC date bridge | P0 4, P1 5, P2 5 are *review priorities*; 14 unresolved; NO auto-exclusions |
| RNA tissue composition | PanCanAtlas ABSOLUTE specimen proxy 13/14, Aran CPE historical 14/14; A3CJ major method disagreement; exact RNA aliquot purity not known | PARTIAL; not interchangeable or reliable clinical covariates |
| CT × RNA | 75 distinct CT people, 73 RNA-linked case IDs; 0 source-linked HCC tumor lesion ROI in audited IDC SEG subset, 0 explicitly PV CT with liver SEG on same series | Metadata GO; molecular CT inference **BLOCKED** without real lesion ROI/time eligibility |
| Triple-modality & TACE | 2 patient barcode overlaps across CT/MRI; WAW-TACE and HCC-TACE-Seg have clinical endpoints but no matching HCC RNA cohort | Not independent molecular replication |
| Molecular inference | Three frozen MRI features × four frozen Hallmark pathways = exactly 12 primary tests | **0/12 RUN**; HCC-17 qualified n NOT ASSESSED, HCC-20 PENDING |

Latest exact [#222 readiness log](https://github.com/kimtk94/Codex/actions/runs/41180175184): technical cross-source GO, clinical pairing HOLD, association STOP, unchanged source baseline, S0. 15 skipped jobs are intentional manual heavy jobs, not 15 additional live passes.

## Scientific strategy: one primary, three bounded supporting tracks

### Track A — PRIORITY 1: MRI–RNA true-pair eligibility (decision-critical)

**Target:** per-person source-evidence matrix for all 14, preserving all 14 IDs and chosen lesions (A10Y tumor3). For each case record:
- original PV selected series identity, tumor mask and published expert evidence; independent *selected index lesion* anatomical review status / reviewer / evidence source;
- tissue STAR-Counts file UUID, TCGA specimen/aliquot lineage and whether the segmented lesion can actually be linked to the sequenced tumor (do **not** equate a patient barcode with same lesion);
- independently justified clinical event sequence (scan before qualifying HCC treatment? scan versus resection/biopsy?), source-specific evidence quality and whether time coordinates are comparable;
- purity and acquisition warnings, and explicit eligible / ineligible / unresolved decisions **without changing baseline from an unreviewed source**.

**Clinical read-out cannot be automated from deidentified StudyDate + GDC relative-day differences.** Obtain data-steward/author clarification or authorized qualified reader assessment when needed; no request for identifiable dates. Prioritize P0 four, P1 five, P2 five. Start with TCGA-DD-A4NH because of overlapping clinical/purity questions.

**GO:** source- and reviewer-supported cohort with explicit included/excluded/unresolved patient flow; original SAP permits *exploratory* primary tests only if confirmed eligible n >= 10 and all other mandatory gates satisfied. n >= 10 is a protocol floor, **not statistical power or publication-grade replication**.  
**HOLD:** source/reader evidence insufficient; do not infer eligibility.  
**STOP primary 12-test claim:** eligible n <= 9 under frozen design, inability to establish valid imaging/tissue/treatment chronology, or incompatible index lesion. Report technical/methods work separately; no opportunistic endpoint/patient swaps.

### Track B — PRIORITY 2: Small, outcome-blind imaging robustness paper / supporting methods

Freeze 14×2 image/ROI extraction and fully document native settings, 3mm resampling, distance-in-voxel caveat, 12.5/25/50 binWidth grid, ICC(A,1), patient bootstrap, LOO, and source 1.5T metadata versus unknown exact selected-series scanner. Produce patient-level figures without RNA linkage:
1. 14-case cohort flow + selected-lesion original PV overlays (expert review explicitly marked pending where relevant).
2. ICC versus actual binWidth/voxel-grid numerical drift **separately**; report patient rank preservation and influence of thick-slice A10Y.
3. MRI feature and ROI volume distribution, scanner/contrast metadata missingness, perturbation limits.

This is a reproducible **technical feasibility/methodology** outcome, not automatically a publishable novel imaging biomarker. Compare existing LiverHccSeg and other radiomics robustness publications before choosing journal. **Do not claim inter-scanner reproducibility or genuine multi-acquisition test–retest from resampling a single image.** No ComBat with sparse/unknown scanner strata.

### Track C — PRIORITY 3: CT cohort rescue via genuine lesion masks (bounded search)

Before drawing 73 tumor contours, audit existing publications/supplements/repositories and institutional data stewards for real **CT tumor-lesion** segmentation, exact series UID, treatment timing and reuse conditions. In particular, 2026 Xu et al. J Transl Med used **41 qualifying TCIA contrast CT + RNA** cases; inspect whether its cohort selections or ROI assets are actually released. The authors' public ML repository contains code; **do not assume reusable masks** without file-level evidence. Exact overlap and authority must be checked.

Proceed with a scoped lesion-annotation pilot only if imaging and diagnosis/phase source controls are viable. A liver-organ mask is not an HCC ROI. Treat 73 as metadata upper bound, not target sample size. Two MRI/CT overlap cases do not supply independent validation.

### Track D — OPTIONAL / BACKGROUND: IBSI CT configuration and external methodological checks

Reproduce IBSI-1 **CT configuration A** first with its official *lung CT* PAT1/GTV-1, 2D in-slice aggregation, no interpolation, HU range [-500,400], FBS 25HU and **official feature-specific CT A reference/tolerance**. Track image intensity rounding and morphological vs intensity masks. A mismatch is REVIEW, not auto-PASS or automatic threshold changes. Then B–E and IBSI-2 filtered-response checks are separate jobs. **Do not block Track A just to finish exhaustive IBSI compliance.**

## Statistical integrity — do not change the locked SAP after examining associations

- Pre-association 3 MRI features: firstorder Entropy, GLCM Contrast, firstorder IQR; four Hallmark sets: Hypoxia, Angiogenesis, EMT, Glycolysis; **12 tests**, two-sided, Spearman/permutation, single BH q<0.05 family, patient bootstrap and LOO sensitivity once clinically permitted.
- Hypoxia/Angiogenesis/EMT RNA scores are strongly collinear (Angiogenesis–EMT ~0.982); q-values cannot establish independent biological mechanisms. Source TSS/contrast and tissue purity are unresolved confounding concerns.
- High GLCM source-vs-grid magnitude drift and ROI anisotropy must be reported with every later association. Do not pick binWidth/voxel grid/ROI on the basis of low p-values.
- n=14 at most and likely fewer after eligibility: small-n study **cannot credibly deliver** complex multivariable prediction, response biomarkers, or high-impact replication with this cohort alone. Significant exploratory q-value would remain hypothesis-generating. If no clinically valid n>=10, stop the frozen test family rather than redefining it silently.

## Manuscript and resource decision

| Outcome | Recommended output | Maximum allowable claim |
|---|---|---|
| Clinical/tissue pairing remains unresolved | Public data lineage, source-provenance limitations, original-mask feature repeatability and acquisition/discretization robustness with transparent null/negative tests where defined | S0 technical feasibility / methodological QC, journal suitability uncertain |
| >=10 truly qualified paired cases, analysis inconclusive | Transparent underpowered exploratory study and analysis/CI evidence, report all 12 null/CI results | S1–S2 depending on verification (not proof of absence) |
| Prespecified BH q<.05 and reader/volume/grid sensitivity credible | Cohort-restricted exploratory MRI–RNA pathways, still no causal interpretation | S3 only after all prior evidence gates |
| Nonoverlapping matched external cohort with same biological hypothesis and reproducible direction | Replicated radiogenomics claim | S4, modality/setting-specific |
| Clinical outcome comparators and frozen independent evaluation | Carefully scoped predictive utility | S5 if validated; not current objective |

**Novelty guard:** Xu et al. *Journal of Translational Medicine* (2026; DOI 10.1186/s12967-025-07627-4) already explored immunoradiogenomics with 41 qualified TCIA CT–RNA cases and a much larger independent clinical evaluation. Therefore merely showing “radiomics predicts immune signal” with 14 unresolved MRI cases is not competitive. Pursue demonstrable *MRI-specific measurement reliability + carefully qualified pathway biology* or reposition to a high-quality methods/resource audit.

**Different project:** HCC proteogenomics multi-omics feasibility in `kimtk94/IS_Analysis_V3#251` remains separately on HOLD for full biology, GO for metadata feasibility. Do not merge its patient denominator or RNA/protein pairing claims into this MRI–RNA study.

## GitHub implementation priorities and acceptance

**Immediate:** freeze this direction memo in PR #228; update README entry point; retain HCC-12/14/16/18 PARTIAL, HCC-17/20 PENDING. Add a 14-case reviewer-ready eligibility evidence table with columns `source_url, image_series_identity, index_lesion, reviewer, MRI_treatment_order_source, tissue_lesion_match_source, technical_flags, decision, decision_date, evidence_hash`. If evidence absent, use explicit `UNRESOLVED`, not empty or derived GO.

**Next decision checkpoint:** report signed/authoritative answers per P0 patient, eligible denominator and exclusions; choose GO / HOLD / STOP for clinical analysis **without** reading MRI–RNA effect estimates.

**Parallel bounded jobs:** (i) frozen 14-case evidence drift + clinician adjudication audit, (ii) ROI/ICC/binWidth sensitivity summary, (iii) CT lesion ROI public source search, (iv) IBSI-1 CT A *nonblocking* benchmark design. Run workstreams independently and aggregate **technical readiness and clinical readiness into separate fields**.

**Automation:** GitHub PR CI can check code, hashes, ledgers and source identity; it cannot substitute for radiologist/data-steward adjudication. Manual heavy source jobs may be skipped on ordinary PR runs. CI output must show `verified job count`, `skipped job count`, `clinical eligible n`, `unresolved n`, `no association tests`, `claim ceiling`. Freeze safe small derived CSV/JSON in Git because artifacts expire in 30 days; do not redistribute original CT under CC BY-NC 3.0 or patient-level controlled images.

## Primary evidence pointers

- [Last full #222 source gate](https://github.com/kimtk94/Codex/actions/runs/41180175184)
- [Expanded IBSI reference #214](https://github.com/kimtk94/Codex/actions/runs/41179519399)
- [14×2×2×3 GLCM factorial #185](https://github.com/kimtk94/Codex/actions/runs/41170599536)
- [IBSI CT official reference configurations](https://ibsi.readthedocs.io/en/latest/05_Reference_data_sets.html)
- [LiverHccSeg original published dataset](https://doi.org/10.1016/j.dib.2023.109662)
- [CLEAR radiomics checklist](https://doi.org/10.1186/s13244-023-01415-8)

**No new patient adjudication, assay or statistical test is claimed by this memo.**
