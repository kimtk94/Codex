# HCC Radiomics and RNA-seq: Research protocol / feasibility gates
Updated: 2026-10-30. Public-data feasibility before modeling.

## Research question
Are pretreatment CT tumor radiomics features associated with independently predefined HCC tumor RNA-seq pathways (hypoxia, angiogenesis, ECM/EMT and metabolic rewiring), controlling for acquisition differences, lesion size and available clinical covariates? Associations are not causal evidence.

## Novelty warning
- A Journal of Translational Medicine paper published on 19 January 2026 used 41 eligible TCIA HCC CT+RNA-seq cases to build an immune-radiogenomics biomarker: https://doi.org/10.1186/s12967-025-07627-4 . Repeating a generic immune predictor does not establish novelty.
- An October 2026 Abdominal Radiology paper trained on WAW-TACE (n=221) and externally tested on HCC-TACE-SEG (n=98), documenting limited frozen radiomics survival-model transfer: https://pubmed.ncbi.nlm.nih.gov/42867540/ . Do not claim these cohorts prove generalizable survival models.

## Cohort separation
| Cohort | Published total | Proper role | Must not assume |
|---|---:|---|---|
| TCIA TCGA-LIHC | 97 mixed-modality imaging subjects | CT ID-GDC tumor RNA metadata match and subsequent CT+ROI/phase qualification | 97 paired CT+RNA cases |
| WAW-TACE | 233 HCC subjects | CT/ROI/clinical extraction benchmark, optionally separate TACE prognosis study | RNA-seq paired subjects |
| HCC-TACE-Seg | 105 HCC subjects | Pre-TACE CT/ROI and **frozen TACE prognosis external test only** | RNA-seq test cohort |
| Hospital | Approval pending | Molecular external validation only if same cases have usable pretreatment CT+tumor RNA | Unconditional transcriptomic validation |

## Go/No-Go gates
- G0: Download *metadata only*. Intersect TCIA TCGA-LIHC CT patients with GDC TCGA-LIHC primary tumor STAR-Counts file-associated case barcodes. This produces **candidate upper bounds only**.
- G1: Qualify each CT as pretreatment, correct anatomy, matching phase (prefer portal venous), consistent slice/voxel spacing, and verified tumor segmentation aligned to image.
- G2: Confirm tissue type, tumor sample (TCGA sample code 01), file-to-aliquot link, batch and collection dates; flag temporal discordance; distinguish tumor from adjacent normal.
- G3: Report counts of distinct *eligible* patients, lesion counts, missingness, expression QC, phase/scanner heterogeneity and exclusion reasons. With small n, use exploratory hypothesis tests rather than uncalibrated AI prediction.
- G4: Predefine PyRadiomics configuration, segmentation, pathways, clinical covariates, outcomes, CV groups and evaluation plan **before** looking at association results.

## Molecular association analysis
- Fixed radiomics with versioned feature extraction, feature stability/QC and tumour volume adjustment. No 2D CNN as default when deterministic PyRadiomics extraction is enough.
- Prespecified hallmark pathways: HYPOXIA, ANGIOGENESIS, EPITHELIAL_MESENCHYMAL_TRANSITION and metabolic pathways. Immune phenotypes secondary because already studied. Record exact MSigDB geneset release.
- Correlate CT features with expression-derived *pathway scores*, not all gene-by-feature pairs. Use Spearman and covariate-adjusted regression with BH-FDR; bootstrap intervals, permutation negative controls, no external outcome-driven feature tuning.
- For ML, feature selection and scaling only within train folds; split all phases/lesions by patient. Frozen hospital validation requires paired CT+RNA data; TACE-only cohorts validate a different clinical outcome.
- OS/TTP analyses must handle censoring (C-index/calibration). Do NOT evaluate survival times as ordinary regression using MAE or R2.

## Code / outputs
Existing PR: https://github.com/kimtk94/Codex/pull/228
Original TCIA metadata: research/hcc/ci/tcia_cohort_audit.py
Added overlap audit: research/hcc/ci/tcga_rna_overlap_audit.py
Offline test: python research/hcc/ci/tcga_rna_overlap_audit.py --offline-test
Live CI: HCC Public Cohort Audit via workflow_dispatch on branch, or scheduled after merge to main.
Outputs: TCGA-LIHC_ct_series.csv, tcga_rna_overlap_summary.json, tcga_rna_overlap_candidates.csv.
Status: TCIA-GDC-IDC public metadata audits validated by GitHub Actions on 2026-10-30. No CT-image/ROI/RNA-expression matrices downloaded; no imaging-qualified paired sample size or model training yet.

## Data / literature
WAW-TACE: https://doi.org/10.1148/ryai.240296 ; https://zenodo.org/records/12741586
HCC-TACE-Seg: https://www.cancerimagingarchive.net/collection/hcc-tace-seg/
TCGA-LIHC: https://www.cancerimagingarchive.net/collection/tcga-lihc/
GDC fields: https://docs.gdc.cancer.gov/API/Users_Guide/Appendix_A_Available_Fields/

## Actual TCIA-GDC CI audit results — 2026-10-30
- GitHub Actions run: https://github.com/kimtk94/Codex/actions/runs/41053179022 ; both offline-tests and metadata-audit passed.
- TCIA TCGA-LIHC: **75 distinct CT patients**, 777 CT series; source collection has mixed modalities, so published 97 is not CT case count.
- GDC TCGA-LIHC: **371 candidate patients** with at least one Primary Tumor case-level association and STAR - Counts metadata.
- CT × RNA case-barcode overlap: **73 patients** (758 CT series across these patients). This is **not a file-to-tumor-aliquot matched count**.
- CT series text and ImageCount prescreen of the 73: **25** patients with explicit portal venous labels, **13** with generic venous-only labels, **35** without either label in eligible-length/axial-looking series; none is an imaging-verified cohort or final excluded patient.
- **Final eligible CT/segmentation/RNA patients: not yet assessed**. The next mandatory gates are CT imaging review, same-patient tumor mask availability, pretreatment timing, GDC file-to-aliquot and sample-code verification, and scanner/phase stability.
- Artifacts: tcga_rna_overlap_candidates.csv, tcga_ct_phase_patient_prescreen.csv, tcga_ct_phase_series_prescreen.csv and JSON summaries, available in the linked run (retention 30 days).
- The portal venous filter is a conservative **triage heuristic**, not a deterministic clinical exclusion. Image count >=30 plus SeriesDescription is insufficient to establish diagnostic axial phase or tumor ROI.

## Follow-up: actual GDC file lineage and IDC anatomy audit (2026-10-30)
- Validated live CI run: https://github.com/kimtk94/Codex/actions/runs/41054539216
- All 73 TCGA-LIHC CT-RNA case-barcode matched candidates have one STAR-Counts RNA file whose GDC file-specific associated entity barcode includes TCGA code **01 (primary solid tumor)**. This establishes *public metadata file-to-tumor barcode evidence*, NOT RNA quality, tumor purity, tissue image registration, expression download or eligible CT.
- IDC SEG audit: 254 SEG series on 71 of the 73 CT-RNA candidates. Their coded segment labels consist of **112 Liver segmentation series** and **142 Tumor infiltration by lymphocytes present annotations**. The TIL annotations refer to digital pathology and **must never be mistaken for CT tumor ROIs**.
- Of 112 liver SEG series, **95** directly reference source TCIA CT SeriesInstanceUID, spanning **36 patients**.
- **0 source-CT-linked tumor-lesion ROI candidates identified in current IDC SEG metadata**. Absence in this subset does not prove no alternative/public/paper-specific tumor annotations exist.
- Image-only liver masks cannot substitute for tumor lesion segmentations; annotate tumor lesions by a documented image-review workflow if needed.
- TCIA warns that DICOM study dates are de-identified with collection/site-dependent offsets. GDC times use relative clinical days; **do not join absolute imaging and tissue calendar dates** without an approved harmonized method. Source https://www.cancerimagingarchive.net/collection/tcga-lihc/
- BAMF AIMI source liver organ mask repository (not tumor ROI): https://github.com/bamf-health/aimi-liver-ct
- IDC segmentation anatomy index documentation: https://github.com/ImagingDataCommons/IDC-REST-MCP/blob/main/docs/user-guide.md

### CT review prioritization
- Automated sorted review queue of 73 candidates: P1=20, P2=5, P3=10, P4=3, P5=6, P6=29.
- P1 is the 20 patients with explicit PV series-text evidence **and** a CT-matched liver-only mask; this is review priority, NOT diagnosis/eligibility.
- Review queue artifact: tcga_hcc_radiogenomics_review_queue.csv
- Next: select actual CT series per patient, visually confirm CT contrast phase and tumor presence, obtain lesion ROI with documented protocol/rater assessment, then freeze true paired eligible n. Clinical stage and covariate availability before feature modeling.
- Preserve all 73 as metadata candidates; avoid excluding patients merely for uninformative SeriesDescription.
