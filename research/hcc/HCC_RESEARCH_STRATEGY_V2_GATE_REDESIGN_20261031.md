# HCC MRI × RNA-seq research decision V2 — 2026-10-31

> **Decision: CONDITIONAL GO for source/eligibility work; HOLD for paired biological inference.** All 14 cases remain technical candidates, not clinically eligible patients. HCC-20's 12 prespecified associations remain **NOT EXECUTED**. Manuscript claim ceiling **S0**.

## 1. What is actually established

- GitHub PR [#228](https://github.com/kimtk94/Codex/pull/228), feature branch `feat/hcc-public-ci-20261022`; **not merged**. Separate technical and clinical verdicts. Heavy jobs can be intentionally skipped.
- **MRI:** 14 LiverHccSeg HCC cases with matching case-level GDC STAR RNA file identities, image pixels, lesion masks, original two-reader segmentation feature extraction (14 × 2) and 10-feature ICC/LOO; 8/10 pass the declared reader reliability screen. No qualified per-case same-lesion/treatment-date clinical approval.
- **RNA:** 14 original STAR count/TPM files size + MD5 verified; exact source Hallmark GMT (MSigDB 2025.1.Hs) pinned; 14 × 4 quantitative rank-based pathway scores computed. The four molecular scores are strongly correlated (Angiogenesis vs EMT rho ~0.982), with possible stromal/tumor-purity/site confounding; **not four independently validated biology signals**.
- **MRI robustness:** 14 × 2 × 2 × 3 = 168 factorial extraction cells in original vs 3mm, binWidth 12.5/25/50. GLCM Contrast is highly dependent on voxel size and discretization (native→3mm ~77% median absolute relative change, 25→12.5 ~253%). Thick-slice A10Y z≈10.8mm outlier; patient-level vendor/phase/tissue validity remains unknown.
- **IBSI source:** Official digital phantom 10/10 original radiomic features reference-compatible on PyRadiomics 3.1.0; independent 13-direction GLCM math. Official IBSI1 CT PAT1 config A reference: independent 5/5 and PyRadiomics 4/4 PASS ([run 41186059566](https://github.com/kimtk94/Codex/actions/runs/41186059566)). Config B: independent 5/5 and PyRadiomics 4/4 PASS ([run 41186558822](https://github.com/kimtk94/Codex/actions/runs/41186558822)); however both B methods share one SimpleITK interpolator, so interpolation is not independently cross-validated. CT C–E and IBSI2 filters **not run**. These are IBSI **lung CT phantom**, not HCC biology.
- **Clinical**: original GDC 130 treatment rows, 42 affirmative; four people have HCC-diagnosis-context Yes treatment with dates before the recorded specimen day; one separate earlier intervention is cecal/appendiceal; none is proof of MRI-after-therapy. No safe join from shifted TCIA image dates to GDC relative treatment/sample days. **14 unresolved; final qualified n NOT ASSESSED**.
- **CT-RNA expansion**: 75 CT cases, 73 linked to GDC tumor RNA metadata; **zero verified exact source CT tumor-lesion ROIs** in the audited candidates. Liver-organ SEG is not tumor ROI. n=73 is not eligible n.
- All 12 primary MRI–RNA Spearman/BH-FDR tests remain untouched. MRI-14 n is a technical upper bound, not a biological publication cohort.
- Evidence gates in `HCC_VERIFICATION_LEDGER.csv`: 7 PASS_METADATA, 5 PASS_TECHNICAL, 8 PARTIAL, 6 PENDING, 1 BLOCKED. Counts describe checkpoint status, **not percentage scientific completion**.

## 2. Newly elevated first-priority source discrepancy: MRI phase/ROI reference space

The **official LiverHccSeg data description** states tumor masks were drawn in arterial reference space and can be applied to `art.nii.gz` and the **co-registered** `art_pv.nii.gz` (among other registered series):

- https://zenodo.org/records/8179129
- https://pmc.ncbi.nlm.nih.gov/articles/PMC10587725/

The current pipeline instead extracts original radiomics from `pv.nii.gz` with `rater1_tumor*.nii.gz`, relying on shape/affine similarity and output overlays. Existing `HCC_G3_IMAGE_REVIEW_AND_PHASE_LOCK.md` says raw PV and ART matched header geometry for 14/14, but `art_pv` did not. **This is a source-convention discrepancy, not proof that the measurements are wrong.** Identical NIfTI geometry does not establish deformable anatomical correspondence, and source mask intended phase may require an explicit warp.

**Before any biological claim or a new CT benchmark, independently inspect the original publication/source definition and actual arterial/PV/registered PV pixel overlays in all 14 cases; keep original image/mask hashes, describe mask creation reference, and obtain reader assessment.** Check selected `A10Y` tumor3. Report `SOURCE_REGISTRATION_CONFIRMED`, `REQUIRES_TRANSFORM` or `UNRESOLVED` per case. If PV extraction is wrong, **recompute the whole frozen MRI ICC/factorial dataset with correctly registered volumes**; do not silently rewrite old numbers or keep earlier reliability PASS.

## 3. The critical, prioritized program

### P0a — Image-to-lesion anatomical validity
- Source-verify each mask's intended reference space and transformation, compare `art`/`pv`/`art_pv` overlays with image-space coordinates and actual tumor anatomy.
- Preserve machine geometry QC and **independent radiologist/manual decision** separately; automated image checks are not qualified reader approval.
- No patient is biologically eligible until acquisition phase, chosen tumor index and mask anatomy are independently assessed.

### P0b — Pretreatment image-to-specimen linkage
- One evidence row per case: patient barcode; MRI series/scan identity; index tumor; RNA file UUID/sample+portion; source treatment/biopsy/resection chronology; same-lesion evidence; reviewer ID/date; decision and evidence links.
- Prioritize four HCC-diagnosis early-treatment flags (**A10Y, A4NH, A25T, AAV1**); then five discordant cases; then five diagnosis-only `prior_treatment=No` cases.
- Contact LiverHccSeg/TCIA/TCGA source stewards or use qualified local reader clinical review for **relative sequence and lesion identity only**, not identifying patient dates. Deidentified image StudyDate is **not** directly comparable to GDC days-to-event.
- Explicit states `QUALIFIED` / `EXCLUDED_REVIEWED` / `UNRESOLVED`; no automatic exclusion, no automatic GO.

### P1 — Biological feasibility decision
- Respect the pre-outcome frozen family: **first-order Entropy, GLCM Contrast, first-order IQR** × **Hypoxia, Angiogenesis, EMT, Glycolysis** = 12 hypotheses; one BH-FDR family.
- If clinically qualified n ≥10 and image–RNA lesion identity/phase/therapy gates are satisfied, allow **only exploratory**, fully reported 12 tests, with 95% bootstrap CI, permutation p, LOO and predeclared volume/reader/voxel sensitivity. n≥10 is a procedural floor, not adequate statistical power.
- If n ≤9 or no defensible source linkage, **STOP** the frozen primary 12-test study. Do not replace unmatched cases with other phases/lesions or optimize associations after viewing p.
- BH first-discovery threshold is p ≤0.05/12≈0.00417; rough Fisher-z 80%-power effect size for n=14 is |rho|≈0.81 and n=10 ≈0.89 (independent-pair approximation). Thus even if eligible, modest effects are extremely underpowered. Clinical prediction/causal statements are not defensible.

### P2 — Evidence-generating fallback manuscript, independent of RNA associations
- Quantify two-reader reproducibility vs **absolute numeric robustness** under voxel size, acquisition anisotropy and binWidth; demonstrate how excellent ICC can coexist with poor cross-protocol portability. Include explicit A10Y thick-slice and raw-PV/registered-PV source diagnostics.
- Do not confuse resampling of a single acquisition with scanner test–retest or multicenter robustness. Need external imaging cohorts and source-specific baseline comparison for a competitive **measurement-methods** paper; a 14-patient descriptive sensitivity analysis alone may not merit a stand-alone article.
- Evaluate HCC-TACE-Seg / WAW-TACE as **independent image-only technical/clinical benchmarks** only when their features/outcomes are defined; do not treat as MRI–RNA molecular replication.

### P3 — CT molecular rescue / external cohort
- Start from 2026 Xu et al. DOI **10.1186/s12967-025-07627-4**, which reports 41 TCIA contrast CT+RNA patients, plus 754 retrospective external imaging cases. Determine public availability and exact series/lesion ROI access, not merely GitHub code existence. Their biological conclusions already cover broad immunoradiogenomics; our 14-image candidate design cannot compete on treatment-response biomarker prediction.
- Seek actual CT HCC tumor masks with exact source-series UID and target-tissue match; **73 metadata-linked** is a ceiling only. If no authoritative masks or accessible clinical relation, do not launch manual 73-case contour workload.
- The separate HCC proteogenomics feasibility project `kimtk94/IS_Analysis_V3#251` is **not part of this paired MRI–RNA study** and remains separately assessed.

### P4 — Nonblocking IBSI
- Freeze CT-A/B artifact hashes and per-feature reference/tolerance JSON in regular CI. Maintain a separate source-acquisition, reference-measurement and clinical-readiness status.
- CT-C/D/E and IBSI-2 filtered response maps are distinct projects, not prerequisites for contacting cohort stewards or adjudicating G3/G4.
- Fix PR CI-only failures without asserting mathematical mismatches: an updated CT-B evidence link must not erase preserved CT-A original run ID. Pin node/action runtime later as maintenance, not science.

## 4. Mandatory decision outputs

| Gate | PASS criterion | HOLD/STOP consequence |
|---|---|---|
| Source image-space validity | Original masks demonstrably aligned to intended arterial/registered PV analysis phase; anatomical reviewer signoff | Hold all prior PV feature biological interpretations, repeat if necessary |
| Treatment/tissue matching | Reviewed scan-before-intervention and same tumor specimen lineage | Unresolved patient cannot be silently qualified |
| Eligible sample size | Freeze n and patient flow. Original SAP minimum n≥10 | n≤9: stop primary molecular family; source ambiguity: HOLD |
| Imaging robustness | Report two-reader ICC **and** grid/binWidth value changes, with outliers | Do not claim stable or predictive radiomics across protocols |
| Biological signal | All 12 tests, uncertainty + FDR and sensitivity; not a selected tiny p | Null/mixed result reported; do not reformulate post hoc |
| External claims | Non-overlapping molecular matched patients and clinically meaningful comparison | No replicated, causal, therapy-response or clinical-utility claim |

**Manuscript direction:** Primary title (conditional) *Pretreatment HCC MRI radiomic heterogeneity and tumor hypoxia/angiogenesis-related transcriptional programs: an exploratory public-cohort radiogenomics study*. Fallback title *Source-space and preprocessing sensitivity of HCC MRI radiomic biomarkers: an auditable public-data reproducibility analysis*. Both are provisional and must be independently compared with literature, clinical source status and actual figures.

**Next execution order:** (1) source-space diagnostic for 14, (2) per-case clinical evidence matrix P0/P1/P2, (3) CT 41-case published cohort ROI provenance check, (4) MRI-only methodological reproducibility and figures, (5) optional IBSI C. **Do not let (5) displace (1)–(3)**.
