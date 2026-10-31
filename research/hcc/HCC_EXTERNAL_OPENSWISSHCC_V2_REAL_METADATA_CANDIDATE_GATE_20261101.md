# HCC independent MRI-only source replication — OpenSwissHCC v2 P0/P1 gate

**Evidence checkpoint 2026-11-01 KST, actual live GitHub Actions [#41217646089](https://github.com/kimtk94/Codex/actions/runs/41217646089).** The metadata-only job PASS; the ~113.8 MB derivative/mask archive job is a separate access/structure gate and must NOT be marked PASS before its conclusion. The 14-person original LiverHccSeg methods effects remain the discovery cohort; OpenSwissHCC is a **geographically and institutionally independent** external image-only dataset, with different original processing and reference-frame practices.

## Why OpenSwissHCC v2, not more LiverHccSeg resampling?

Official [OpenSwissHCC v2 Zenodo record 21992461](https://zenodo.org/records/21992461) (published 2026, author Cazzagon et al., Scientific Data DOI [10.1038/s41597-026-08506-3](https://doi.org/10.1038/s41597-026-08506-3)) includes multiphasic `native`, `arterial`, `venous`, `delayed` T1, manually segmented tumor/lesions per phase when visible, and official interphase Elastix transforms. No TCGA cases. Study reports 132 patients, 63 HCC-positive, 69 HCC-negative, 140 lesions, 97 confirmed HCC lesions.

Version v2 (not older Zenodo v1) was **essential**: `annotation_status.tsv` tracks mask status on each phase/lesion, and `manual_lesion_annotations_second_reader/` is supplied for 5 subjects (source claims 10 portal-venous second-reader lesions). Do NOT assume all 97 HCC lesions have a venous mask or that two raters cover the whole cohort.

### Original file access and provenance — actually checked

In [live GitHub Actions #41217646089](https://github.com/kimtk94/Codex/actions/runs/41217646089) the initial **four small official files were downloaded, MD5 checked, and parsed**:
- `participants.tsv`, MD5 `e3df2cc4a825828d0fafdd09155a97c9`;
- `annotation_status.tsv`, MD5 `9fceca660e4d6a74b25ccf172ac380dd`;
- `data_description.txt`, MD5 `7cf6cb8fe20c0b8012c9666bb4dfbfbe`;
- `README.md`, MD5 `1161d2370e3d3bb0f5217daa0a171173`.

The official `participants.tsv` has **69 no-lesion HCC-negative control subjects with blank lesion IDs**. These must be retained in the 132-person count but **not** fabricated as lesion masks. The first CI failed because a strict parser expected every subject row to have a lesion ID; this was corrected and the second metadata-only CI job **SUCCESS**. Actual validated observations:
- **132 unique subjects**, including **69 no-lesion controls**;
- **140 unique lesion metadata records**, **97 HCC-labeled lesions in 63 subjects**;
- **980** original sequence-level annotation-status records on **140** lesion pairs;
- Venous status (all 140 lesions): **114 annotated**, **3 reassessed_after_delineation with mask**, **23 not_visible**;
- HCC-positive venous mask **metadata candidates: 90 lesions in 59 independent patients**. This is **not** yet a validated image/mask NIfTI pair count or the external radiomics analysis n.

Original metadata result: Actions artifact `hcc-openswiss-v2-official-metadata-only-hcc-venous-candidate-manifest`, ID **13049030017**, includes the 90-lesion candidate manifest and the exact provenance JSON.

The versioned `derivatives.zip` is **113.8 MB** with official MD5 `45975a7018834c4ab1b827efff0b41ac` and holds manual masks and transform files; derivative file listing and MD5 is a separate CI job. Full MRI images are in three separate **~4–5 GB** patient ZIPs, combined ~14.5 GB. **Do not download all three** merely to read metadata.

## External validation protocol — source-locked, outcome-blind

**First-pass external eligibility must require all of:** original `participants.tsv` HCC=1, `annotation_status.tsv` Venous `annotated` or `reassessed_after_delineation`, actual unique manual venous lesion mask filename in the v2 derivative archive, matching actual original **venous phase/acq-water** NIfTI, identical lesion index and compatible affine/voxel space, nonempty ROI, reproducible source checksums. Any missing condition = HOLD (not clinical diagnosis or silent exclusion). Never equate author-assigned HCC labels and image/mask file presence with a clinically qualified RNA-matched case.

Freeze **one lesion per independent subject** for the primary external MRI-only descriptive replication to avoid 90 lesions being treated as 90 independent people. Deterministic metadata-only selection: of the HCC-positive lesions with a verified venous mask/image, choose largest source **Lesion size** in mm; ties resolved by smallest lesion index. Do not select lesion by radiomics change, visible voxel histogram, patient outcomes, or direction of the effect. Report all-lesion secondary analysis only with subject-clustered uncertainty.

Reproduce **within the same venous image** `native spacing × binWidth25` (baseline), `3mm isotropic × binWidth25`, `native × binWidth12.5`, `native × binWidth50`. For `3mm`, image BSpline interpolation and mask nearest-neighbor, exactly specify PyRadiomics v3.1.0 settings from the 14-case study. Contrast `median absolute within-patient source-processing change`, `patient rank Spearman`, subject-level bootstrap CI and source-independent description; only compute reader ICC within the **actually validated v2 second-reader subset**, not 59 supposed 2-reader masks.

**Essential lack of modality equivalence:** Swiss sources were already reoriented RAS and bias-field-corrected, with venous-reference Elastix registration, whereas LiverHccSeg uses arterial-reference official `art_pv`. Thus an external 3mm/bw25 shift replicates **image spatial/discretization sensitivity**, but **does not independently reproduce the raw-PV versus original author-registered-PV 22.08% contrast**. Do not claim equivalent data or use Swiss MR as the missing 14-person TCGA RNA tumor identity evidence. All MRI–RNA planned 12 associations remain 0/12, clinical claim ceiling S0.

## Other independent option: ATLAS MRI

[ATLAS challenge dataset](https://atlas-challenge.u-bourgogne.fr/dataset): HCC liver/tumor MRI segmentation with 60 train and 30 test cases; **official download restricted to registered users**, though website gives dataset provenance and scanner information. Images are selected across arterial, portal-venous or delayed phases, **not necessarily consistently portal venous**. Thus ATLAS is **HOLD pending legitimate user registration and actual phase/mask metadata inspection**; do not bypass login or label the 90 cases as all venous portal images. The Duke Liver MRI dataset has liver-organ masks but not the required per-tumor HCC venous masks, so it is not interchangeable with either external lesion cohort.

## GO/HOLD/STOP

- **GO:** OpenSwissHCC v2 four tiny original official metadata files, verified MD5 and actual **90 HCC venous lesion candidates in 59 people**.
- **HOLD until inspected:** 113.8 MB derivative ZIP mask path/MD5, selected original venous images / NIfTI affine matching and independent patient/lesion MRI extraction. A dataset size alone is never validation.
- **STOP:** HCC biological radiogenomics tests, pretending the 90 lesions are 90 independent patients, repeating the 14-case discovery analysis until a desired p-value, joining TCGA clinical events to Swiss cohort, and phase/registration equivalence claims unsupported by independent data.
