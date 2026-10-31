# HCC MRI 14 — Independent tumor purity cross-validation: DNA ABSOLUTE vs historical consensus CPE

**Date:** 2026-10-31 KST. **Interpretation:** research confounder QC, **not** case inclusion or biological MRI–RNA inference.

## Provenance / exact source fingerprints

1. Official [NCI GDC PanCancer Atlas ABSOLUTE DNA purity/ploidy](https://gdc.cancer.gov/about-data/publications/pancanatlas), `TCGA_mastercalls.abs_tables_JSedit.fixed.txt`, GDC file UUID `4f277128-f793-4354-a13d-30cc7fe9f6b5`. Downloaded 901,812 bytes, SHA256 `f430a975433d82e0098d7405619d4f12a0c765fcd97e7d63cc9b1de7f2d763cd`. Real [GitHub audit #121](https://github.com/kimtk94/Codex/actions/runs/41090891246).
2. Independent [Aran, Sirota and Butte (2015), Nature Communications, DOI 10.1038/ncomms9971](https://doi.org/10.1038/ncomms9971), **Supplementary Data 1** (`ncomms9971-s2.xlsx`, official Springer Nature `media.springernature.com` publisher link). Downloaded 553,082 bytes, SHA256 `fce1ba13ff3a6432b7e4f260eb516e407c967d615ca87bc8dffa7765baf97529`. Real [GitHub audit #128](https://github.com/kimtk94/Codex/actions/runs/41091879111). Publication uses historical RNA-seqV2 RSEM, copy-number, methylation and slide pathology for different estimators; it is **not** the currently downloaded GDC STAR-Counts aliquot.
3. Patient-level frozen public identifier and values: [14-case ABSOLUTE DNA proxy CSV](HCC_MRI_14_PANCAN_ABSOLUTE_PURITY_PROXY_20261031.csv), [14-case Aran CPE/ESTIMATE/LUMP/IHC CSV](HCC_MRI_14_ARAN2015_CPE_REFERENCE_PURITY_20261031.csv).
4. Deterministic cross-method discrepancy script `research/hcc/ci/mri_purity_crossmethod_discrepancy_qc.py`: enforces the **same 16-character TCGA specimen barcode**, does not invent exact aliquot matching, retains missingness and blocks any clinical eligibility promotion.

## Validated findings

| Measure | Valid patient/sample identifier matches | Summary | Missing |
|---|---:|---|---:|
| ABSOLUTE copy-number DNA purity proxy | **13/14** at same 16-character tumor specimen | median **0.74**, range **0.20–1.00** | TCGA-DD-A4NJ |
| Aran historical consensus CPE | **14/14** at same 16-character specimen | median **0.81565**, range **0.4591–0.9763** | none |
| Aran historical ESTIMATE | 14/14 with a numeric value | Gene expression/stromal/immune estimate, not matched modern RNA aliquot | none |
| Aran historical LUMP and pathology IHC | 14/14 with numeric value | Methylation and histopathology-based measurements | none |
| Aran 2015 historical ABSOLUTE column | **0/14 nonmissing** | It is **not** the same copy-number measurement as PanCanAtlas ABSOLUTE | all 14 |

At the descriptive `0.50` *review threshold* (not a prespecified patient-exclusion threshold), **3/13 DNA ABSOLUTE estimates** and **2/14 historical CPE estimates** fall below 0.50. This confirms sample purity is **method-dependent** and cannot be inserted as an unquestioned HCC bulk-RNA purity covariate.

## Patient-level discrepancies and review priorities

| Patient | PanCanAtlas DNA ABSOLUTE | Independent historical CPE | Aran ESTIMATE | What needs adjudication |
|---|---:|---:|---:|---|
| TCGA-G3-A3CJ | **0.20** | **0.8806** | 0.9107 | Extreme discrepancy **0.6806**; independently linked GDC slide minimum tumor cells 100%. Different assay/portion/method; **do not assume either is correct**. |
| TCGA-G3-A7M7 | 0.58 | 0.8360 | 0.9253 | Difference 0.2560; assess DNA purity call quality and linked sample/slide provenance. |
| TCGA-DD-A4NH | 0.34 | **0.4730** | 0.8472 | Both composite CPE and DNA are low, but ESTIMATE differs; also treatment-priority review. |
| TCGA-G3-AAV3 | 0.47 | **0.4591** | 0.7929 | Consistently under 0.50 in DNA/CPE; do not exclude without frozen threshold or independent sample-level review. |
| TCGA-DD-A4NJ | *no ABSOLUTE record* | 0.7000 | 0.8129 | CPE fills historical reference gap, **does not retroactively create DNA ABSOLUTE evidence**. |

No biological MRI–RNA association has been run. The strength of these discrepancies supports using tissue mixture as a high-priority **potential confounder**, not a demonstrated causal explanation for Hallmark Angiogenesis/EMT RNA-score collinearity (observed RNA-only rho ~0.982).

## Study-level interpretation

- RNA source technical count integrity, index MRI shape/signal QC, 2-rater PyRadiomics ICC, four Hallmark sample-score QC and now two independent specimen-level tumor purity references exist. They help define measurement quality but **do not** establish the 14 patients have pretreatment imaging of the sequenced lesion.
- CPE/ESTIMATE from an older assay, DNA ABSOLUTE and pathology slides measure different tissue composition proxies; **do not use them interchangeably**. Current GDC STAR RNA analyte-specific purity remains NOT VERIFIED.
- The primary frozen 12-image/4-pathway family remains on HOLD pending HCC-12 expert MRI source/ROI review, HCC-14 source-treatment chronology and HCC-17 patient-level qualifying denominator. If ≤9 patients qualify, original study plan's minimum N=10 fails and primary inference STOPs.
- Keep all 14 patients as **unresolved technical candidates**, no exclusion based solely on a purity value. `ABSOLUTE<0.5` or `CPE<0.5` are *descriptive QC review flags*, not clinical ground truth.
- A permissible followup **without image associations**: inspect exact DNA purity `call status`/solution model and whether matched specimen has genomic purity quality labels; inspect separate R-based ESTIMATE on verified GDC STAR TPM, explicitly labeling it as a new algorithmic estimate distinct from Aran's published one. Avoid outcome-driven sample curation.

## Downstream record

- **HCC-16 = PARTIAL**: two independent published tumor purity proxy sources matched 13/14 and 14/14 specimens, but exact RNA aliquot, batch and tissue mix still unresolved.
- **HCC-14 = PARTIAL**: five patient treatment-before-tissue relative-day review flags already recorded; no MRI pretherapy safe date bridge.
- **HCC-17 = PENDING**: fully qualified clinical paired n NOT ASSESSED.
- **HCC-20 = PENDING**, no Spearman image–RNA tests; maximum manuscript significance claim remains **S0**.
