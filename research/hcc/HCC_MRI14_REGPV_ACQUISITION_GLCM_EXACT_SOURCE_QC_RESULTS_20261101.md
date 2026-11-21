# HCC P0 — Official registered PV exact-spacing, acquisition and GLCM exploratory QC

**Source completed 2026-11-01 KST.** [Original GitHub Actions run #41214675184](https://github.com/kimtk94/Codex/actions/runs/41214675184) **9/9 SUCCESS**, including the synthetic test, seven official-source two-case MRI header shards, and the 14-patient descriptive integration. This is **exploratory measurement reproducibility**, not tumor pathway biology, prediction, prognosis, clinical registration approval or causal inference. Claim ceiling **S0**.

## Source integrity and analysis denominators

- Original complete 14-patient [LiverHccSeg v1.1](https://zenodo.org/records/8179129) **official arterial-registered PV `art_pv.nii.gz`** and each patient's frozen expert index-tumor mask (A10Y tumor3; 13 tumor1); signed NIfTI axis flip corrected to mask physical coordinates and ≤0.5 mm max affine corner offset.
- **14/14** source-image and published reader1 mask **SHA256** identifiers match the exact material previously used to compute the [original 168-row registered PV 2×3 PyRadiomics factorial](HCC_MRI_P0_REGISTERED_PV_2X3_FACTORIAL_14_CASE_RESULTS_20261101.md). The original 168 rows were read from four checksum-verified artifact members. Its **112/112** registered `native / binWidth25` four-feature reference comparisons were independently previously PASS.
- Exactly **14** source headers and patients (not 28 independent rater cases); **20** Spearman+LOO descriptive records (5 source spacing variables × 4 feature-change responses); **12** contrast-label descriptive rows (3 × 4); **0** MRI–RNA association tests and **0** qualified image review decisions. No p-values were computed or reported.
- Original GitHub artifact ID **13047649835**, `hcc-mri14-official-regpv-exact-spacing-agent-glcm-descriptive-20-loo` (GitHub Actions time-limited archive). Contains 14 full source hashes and voxel spacings; 20 rank/LOO rows; 12 group descriptives; complete JSON decision. Permanent 14-case [compact extracted original source audit table](HCC_MRI14_REGPV_EXACT_SPACING_GLCM_STUDY_CONTRAST_FROZEN_20261101.csv) is committed alongside this report. The source SHA file, not unverified independent labels, remains the image reference.

## Fundamental registration/source distinction resolved

**All 14 official registered PV `art_pv` source NIfTI headers have the same measured z spacing as the corresponding previously inspected native raw PV NIfTI**, comparing actual numeric z-spacing to the previously committed raw-PV spacing column: **14/14 equal at stored source precision**. The spatial grids' **intensities and interphase registration can still differ substantially**; equal NIfTI header spacing does **not** imply equal pixels or that raw-PV ROI anatomy is authorized. The source-resampling factorial is distinct from the archived authors' arterial-to-PV registration.

Observed registered PV z spacing **2.4–10.8 mm**; z/in-plane ratio **1.78–14.55**. A10Y carries the frozen technical anisotropy/thick-slice flag with registered z=10.8 mm, native in-plane approximately 0.742 mm and tumor3. Published study-level MRI field strength is 1.5 T in **all 14**; no within-cohort magnetic field-strength effect can be identified.

## Main technical observations — patient means from 2 expert masks

The locked engineering comparison is the absolute relative change of GLCM Contrast under **3 mm isotropic B-spline imaging resampling, binWidth25**, against **the exact same registered native spacing binWidth25** baseline in each patient. Mask resampling is nearest-neighbor. The results across 14 technical candidates have median absolute change **86.59375%**, prior 95% 4,000-patient paired-bootstrap interval **[76.4005%, 97.8784%]**.

| Patient | Registered PV z mm | 3 mm native-bw25 → 3mm-bw25 GLCM Contrast absolute shift | Prior technical review priority |
|---|---:|---:|---|
| BC-A10Y (tumor3) | **10.80** | **0.328%** | 10.8 mm thick-slice source outlier; keep patient, examine true 3D ROI response |
| BC-A3KG | 2.50 | 92.480% | 3 mm grid affects rank and contrast |
| BC-A5W4 | 3.50 | 61.183% | Study-level contrast category only |
| BC-A69I | 3.50 | 70.381% | No published contrast label |
| DD-A4NF | 3.00 | 85.228% | Small index lesion / moderate inter-reader Dice |
| DD-A4NH | 2.70 | 137.194% | Clinical HCC therapy timeline P0 separately unresolved |
| **DD-A4NJ** | **2.40** | **251.406%** | Largest measured 3 mm contrast response; check mask and edge effects |
| G3-A25T | 2.50 | 87.960% | Clinical P0 separately unresolved |
| G3-A3CJ | 2.80 | 111.012% | Small cohort context |
| G3-A7M7 | 3.00 | 92.697% | No approved exact series/agent linkage |
| G3-AAV1 | 2.55 | 97.878% | Reader intermask Dice flagged; clinical P0 unresolved |
| G3-AAV2 | 2.50 | 85.209% | Cohort source control |
| G3-AAV3 | 2.50 | 82.420% | Cohort source control |
| G3-AAV7 | 2.50 | 69.246% | Small index lesion, original raw/registered PV intensity identity separately verified |

**13/14** cases exceed absolute 10%; **A10Y is the one exception**. This is not sufficient to infer which image-level interpolation or acquisition factor causes each difference.

### Registered spacing vs GLCM source sensitivity — descriptive rankings

| Measured source factor | Spearman ρ with absolute 3mm/bw25 GLCM change | Range across all 14 leave-one-patient-out (LOO) |
|---|---:|---|
| Exact registered through-plane z mm | **−0.419** | **−0.531 to −0.269** |
| Registered in-plane mm | +0.075 | −0.158 to +0.251 |
| Registered z/in-plane anisotropy | −0.207 | −0.393 to −0.008 |
| Registered \|z−3 mm\| | −0.423 | −0.733 to −0.266 |
| Historical raw PV z mm | −0.419 | −0.531 to −0.269 |

The historical raw PV z value is numerically equal to the registered PV z value in all 14 patients, so the last row **is not an independent five-variable effect**; it is an explicitly disclosed provenance comparison. `z`, `z/in-plane`, and `|z−3|` are mechanically related. No regression adjusted for their collinearity. These 20 numbers describe feature measurement heterogeneity **without any p-value or multiple-testing discovery claim**.

**Pre-existing anisotropy-flag sensitivity:** removing *only* A10Y from the descriptive rank calculation (13 analyzed, no clinical exclusion) changes z-spacing versus 3mm contrast absolute shift ρ from **−0.419 to −0.269** and anisotropy ratio ρ from **−0.207 to −0.008**. This corroborates instability of an apparent simple spacing relationship rather than a mechanistic proof. Across those 13, median GLCM absolute shift becomes **87.960%** versus **86.594%** with all fourteen.

### Published study-level contrast-agent metadata (not exact PV-series verification)

| Published study label | Independent patients n | Median absolute 3mm-bw25 contrast shift | Range |
|---|---:|---:|---:|
| Extracellular | **7** | **87.960%** | 0.328–111.012% |
| Hepatobiliary-specific | **4** | **114.837%** | 61.183–251.406% |
| Unavailable as labeled in workbook | **3** | **70.381%** | 69.246–85.228% |

These labels originate in **original publication's per-study spreadsheet**, not separately certified *for the exact selected ART_PV MRI series*. Agent category is not independently equivalent to MRI scanner model, and four-versus-seven-versus-three participants are inadequate for attribution. The 251.4% A4NJ source outlier is in the small hepatobiliary-specific group. **Do not perform an agent efficacy or scanner effect statistical test, assume matching exact series, or run ComBat in n=14**.

## Scientific decisions

**Technical source-methodology GO:** Frozen public data support a narrow finding: official registered-PV MRI radiomic GLCM Contrast is highly sensitive to voxel grid and binWidth, despite high intra-condition expert-reader ICC, and patient-level heterogeneity is not well explained by slice z-spacing alone. Clear scanner batch, field-strength or contrast agent mechanism **NOT ESTABLISHED**. Independent source visual anatomy verification, scanner sequence metadata, and a second cohort would be needed for external claims.

**Biological/clinical HOLD:** 14 source-methods candidates are not a qualified MRI–RNA paired cohort. Neither exact pretreatment scan timing nor matching index tumor RNA specimen was established, qualified local expert ROI review **NOT_ASSESSED**, eligible n **NOT_ASSESSED**, locked MRI–RNA tests **0/12**, publication ceiling **S0**. Do not select resampling/bins by downstream RNA score association.

**Next methodological decision:** extend the image-only, source-locked analysis with an explicit explanation of partial-volume artifact, different source intensity/registration behavior and small-sample uncertainty, or seek real image-only external validation. No biological testing is authorized by this engineering QC alone.
