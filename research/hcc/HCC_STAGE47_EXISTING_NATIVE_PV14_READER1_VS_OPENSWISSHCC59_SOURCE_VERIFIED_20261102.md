# HCC Stage47 — Original native venous MRI sensitivity source harmonization (n14 and n59)

**Evidence date:** 2026-11-02 KST. **Real successful CI:** [GitHub Actions #41444439116](https://github.com/kimtk94/Codex/actions/runs/41444439116), SUCCESS. Artifact **13140149400**, ZIP SHA-256 `11fb12869031788111ac55142d09c361a4804b3e1e4a96aac49978063cf26563`.

This follow-on corrects a planned Stage46 inefficiency: **native PV→3mm MRI features for the TCGA-LIHC 14 were already extracted and validated** on [GitHub Actions #41161863748](https://github.com/kimtk94/Codex/actions/runs/41161863748). We reused the permanently committed `HCC_MRI_PV_14_NATIVE_3MM_ROI_VOLUME_AND_PRIMARY_FEATURE_CHANGE_20261031.csv` and `HCC_MRI_PV_14X2_NATIVE_VS_3MM_FEATURE_REPRODUCIBILITY_20261031.csv`. External original native venous 59 used [#41221356861](https://github.com/kimtk94/Codex/actions/runs/41221356861). **No repeated image download, extraction or reconfiguration.**

## Strict independent-patient analysis n14 and n59

The per-patient unit is one original selected HCC lesion and one primary mask / rater1 image per subject. MRI source is original native venous phase; processing comparison is native/binWidth25 versus PyRadiomics 3mm-isotropic/binWidth25. Note differences in acquisition scanner/protocol, original masks, lesion sizes, voxel anisotropy and independent original imaging institutions; nominal settings alone do NOT establish exact comparability of underlying source acquisitions.

| Original cohort, source | Patients | Median absolute native→3mm GLCM Contrast % | 95% interval | Leave-one-out patient median interval |
|---|---:|---:|---:|---:|
| LiverHccSeg/TCGA-LIHC original native PV, **reader1** | **14** | **74.880800** | **68.0073–88.6917** (new exploratory 4,000 patient bootstrap) | 74.1106–75.6510 |
| OpenSwissHCC v2 original native venous HCC, original expert mask | **59** | **64.635863** | **56.7537–74.4359** (previously frozen 4,000 bootstrap) | 64.2487–65.2071 |

Descriptive difference in medians: **+10.244937 percentage points**, internal n14 minus external n59. **No test of inter-cohort equality/difference was performed**; do not claim a statistically significant difference or scanner cause. The original internal 14×2 two-reader *28-row* median was **77.0667%**, a different estimand with repeated reader observations, not a 28-person denominator. The previously reported 86.594% median was for a distinct *registered ART/PV* source protocol, and must NOT be substituted for native PV.

## Meaning, limitations and thesis decision

- Existing original native PV source sensitivity is nontrivial in both *independent, HCC index-lesion cohorts*. The previous n59 patient-rank Spearman under native→3mm was ~0.9408; the internal n14 14×2 patient-averaged rank Spearman 0.8505 from existing frozen ICC source summary is NOT the same as the new reader1-only analysis and is **not** paired here as an identical estimand. Reconstruct reader1 per-case paired feature value ranks from existing source artifact before a formal cross-cohort rank comparison.
- High reader-mask ICC **does not imply grid-resampling invariant radiomic values**. Internal reader ICC demonstrated on 14×2 only; external second-reader index lesions only **3/59**.
- This is not scanner test-retest and is not external validation of classification, survival or MRI–RNA biology. Avoid using "external validation" without naming the exact *methods* endpoint. This is **independent-cohort descriptive sensitivity replication with acquisition differences**.
- No original MRI source-aliquot same physical lesion linkage or pretreatment HCC clinical episode proven. Clinical eligible n NOT_ASSESSED, MRI–RNA tests 0/12, biology ceiling S0. This restriction does not erase the valid MRI-only technical descriptive outcomes.
- Existing source independent abdominal MRI annotation reports do not constitute new blinded expertise for all selected index masks; explicitly note anatomical independent review remains pending.

### Novelty risk: existing high-relevance HCC MRI prior literature

**Mandatory direct comparator**, not merely generic IBSI:
- *Precision of MRI radiomics features in the liver and hepatocellular carcinoma* (European Radiology, 2021, PMID 34564745), https://pubmed.ncbi.nlm.nih.gov/34564745/. This study had 55 liver MRI patients including 16 untreated HCCs, and performed actual scanner test–retest, inter-platform and inter-observer MRI radiomics precision. Accordingly, **do not claim the first HCC MRI reproducibility study**, and do not imply ours has real test–retest scans. Contrast: our particular source-reproducible, larger independent 59 HCC-lesion voxel grid perturbation and rank/magnitude metric compared across separately annotated cohorts. Full-text methods must be checked to ensure these exact contrasts and texture definitions are not duplicate published findings.
- IBSI1 Radiology 2020, https://pmc.ncbi.nlm.nih.gov/articles/PMC7193906/ (already established radiomics standardization).
- OpenSwissHCC 2026 dataset, https://www.nature.com/articles/s41597-026-08506-3 (132 original MRI patients, 63 HCC, of which n59 match our frozen venous tumor source endpoint). Novel source resource, but use of a new database is not automatically a new scientific finding.
- MRI preprocessing radiomics reproducibility study 2026, https://pmc.ncbi.nlm.nih.gov/articles/PMC13178426/ (non-HCC modality-specific preprocessing influence).

## Final gate at this step

**MRI-only HCC methods MSc study: CONDITIONAL GO**, with strong existing reproducible technical results and **no new source MRI extraction needed for the current native→3mm test**. Major remaining:
1. **Novelty**: direct comparative table to 2021 HCC MRI precision and other HCC preprocessing studies; isolate what is genuinely new and report limits honestly.
2. **Anatomical image/ROI expert review**: independent qualified radiologist adjudication of lesion/phase and source contour quality; if not available, restrict claims to computational stability under provided published masks.
3. **Statistical design and protocol accounting**: keep n14/n59 individual-patient units and CI method explicit; ensure binary native PV/3mm source definitions and patient ranks have exactly matched features/rater estimands; do not use reader duplication as extra patients. Avoid post-hoc optimized preprocessing claims.

If these cannot be met, this is **HOLD as a thesis with clinical significance**, despite a technically complete sensitivity result; it may still support a limited nonclinical methods report. MRI×RNA biological analysis remains STOP without source-authoritative exact same index lesion and pretreatment proof.
