# HCC External MRI replication P1 — Real OpenSwissHCC v2 mask + one original venous MRI pilot

**Evidence as of 2026-11-01 KST.** Two actual independent GitHub Actions completed:
- [OpenSwissHCC v2 original metadata/derivative source preflight #41217646089](https://github.com/kimtk94/Codex/actions/runs/41217646089): **2/2 SUCCESS**;
- [Original HCC venous MRI image/lesion mask + 2×3 PyRadiomics pilot #41218183515](https://github.com/kimtk94/Codex/actions/runs/41218183515): **2/2 SUCCESS**.

These are **public-source engineering feasibility milestones**, not a validated external *cohort* response estimate, not a clinical biomarker or MRI–RNA association. Original LiverHccSeg discovery source n=14 / registered-PV 3mm-bw25 GLCM median absolute source change 86.59% remains independent and unchanged.

## 1. Actual 132/140/97 original Swiss metadata and real 90/90 manual masks

Published [OpenSwissHCC v2 Zenodo 21992461](https://zenodo.org/records/21992461), data descriptor [Cazzagon et al., Scientific Data 2026](https://doi.org/10.1038/s41597-026-08506-3).

Original verified metadata four MD5 checks: `participants.tsv` e3df2cc4a825828d0fafdd09155a97c9, `annotation_status.tsv` 9fceca660e4d6a74b25ccf172ac380dd, `data_description.txt` 7cf6cb8fe20c0b8012c9666bb4dfbfbe, `README.md` 1161d2370e3d3bb0f5217daa0a171173. Actual mask archive `derivatives.zip` MD5 45975a7018834c4ab1b827efff0b41ac. **2,832** archive paths inspected.

Source dataset accounting (real parsed values):

| Original source evidence type | Verified count |
|---|---:|
| Distinct source patients | **132** |
| HCC-positive source patients (at least one HCC lesion labeled) | **63** |
| HCC-negative subjects with blank lesion index | **69** |
| Unique annotated lesion records | **140** |
| HCC-labeled lesion records | **97** |
| Original phase-specific status rows | **980** |
| HCC lesion pairs reported as having a portal-venous mask | **90 lesions across 59 subjects** |
| HCC venous lesion first-reader mask paths actually present in derivative archive | **90/90** |
| HCC venous independent second-reader masks | **8 lesions in only 3 independent HCC subjects** |

The official source describes a second-reader study across five people and up to ten venous lesions. **Only eight HCC-labeled venous lesion masks in three subjects** link to the 90 qualifying HCC venous candidates. Do not claim 59×2 independent reader measurements, and do not estimate inter-reader generalizability from three people without explicitly labeling it exploratory.

The official publication has pre-existing bias correction and RAS orientation and phases registered to venous using Elastix, unlike the previous LiverHccSeg arterial-reference `art_pv` source. Mask file availability alone is not proof of image/mask spatial alignment or independent clinical diagnosis.

## 2. Actual independently acquired original image-mask evidence

Prelocked demonstration case **Swiss `sub-003`, HCC lesion `L1`** (chosen by original source manifest, not MRI feature value or RNA). Actual official venous water image was obtained via **bounded HTTP ZIP Range requests into the remote ~4.9GB `sub-001-sub-044.zip` archive**, without downloading the entire patient archive. Independent expert mask was separately retrieved by ZIP range from original `derivatives.zip`.

Provenance of downloaded NIfTI compressed bytes:
- Original image member: `sub-001-sub-044/sub-003/dyn/sub-003_acq-water_phase-venous_T1w.nii.gz`
- Image SHA-256: `af04138045a8c96cba88bd854c88c0f36ca2d5ded98ded7161d100b45dbd9d22`
- Original HCC lesion mask member: `derivatives/manual_lesion_annotations/sub-003/dyn/sub-003_acq-water_phase-venous_T1w-L1_seg.nii.gz`
- Mask SHA-256: `27dcf98a8c785eb544a8714872612387dab68068a3f6555019259959a184e5e9`.

**Image-mask native voxel geometry and ROI finiteness PASS, n=1 patient.** Extraction used pinned PyRadiomics v3.1.0 with the previous [LiverHccSeg binWidth/3mm parameter code](ci/mri_pv_glcm_binwidth_spacing_factorial.py), actual venous source data, **not a fabricated contrast histogram**.

| Official Swiss venous source | Native GLCM Contrast | 3mm isotropic GLCM Contrast |
|---|---:|---:|
| binWidth12.5 | 7.085259892 | 13.546183819 |
| binWidth25 (locked baseline) | **1.957960009** | **3.048320433** |
| binWidth50 | 0.671637459 | 0.962751175 |

Registered source reference caution: this is **native venous water** (not the authors' arterial-registered `art_pv` reference) and **one distinct Swiss subject**, not a confirmatory between-dataset effect estimate. Observed `3mm/bw25 vs native/bw25` source feature signed relative shift is **+55.688595%** (only one sample, zero interval inference).

Actual two-Job source script [`mri_external_openswisshcc_v2_image_mask_pilot.py`](ci/mri_external_openswisshcc_v2_image_mask_pilot.py), [CI YAML](../../.github/workflows/hcc-openswisshcc-v2-one-venous-image-pilot.yml). GitHub Actions artifact ID **13049235746**, `hcc-openswiss-v2-one-subject-original-venous-2x3-pyradiomics-pilot`, contains **6 actual case-condition feature rows** plus sha-pinned JSON. No medical images or masks are checked into GitHub, and no 5GB ZIP is mirrored.

## 3. Why this matters — and what remains

**Real result:** an independently sourced HCC venous MRI with a genuine manually annotated tumor mask can be retrieved programmatically and all six locked 2×3 pre-processing conditions can be extracted without local/Colab/server storage. This strongly supports CI-only scaling feasibility, avoiding raw-image redistribution.

**Not established:** external *effect distribution* replication, original n=14 confidence interval agreement, HCC predictive utility, patient clinical pretreatment chronology, concordance of the two segmentation sources' registration reference, any biopsy RNA specimen match, or MRI–RNA pathway effect. All biological associations remain **0/12**, clinical patient eligible n **NOT_ASSESSED**, claim ceiling **S0**.

### Next exact CI milestone for independent replication

Proceed to the **59 qualified metadata-candidate patients** (90 HCC venous masks) only through bounded ZIP range reads and exact source bytes/CRC/affine checks; freeze the one lesion per patient before feature extraction. Primary selection may use the largest source-provided lesion diameter in mm with stable index tie-break, not feature/p-value effects. For each natively image-aligned eligible subject, extract original venous `native / binWidth25`, `3mm / binWidth25`, `native / binWidth12.5`, `native / binWidth50`, and optional all-six for factorial external comparability. Never use 90 lesions as 90 independent people. Report failures and missing image/mask geometry without silent exclusions; run no MRI–RNA scores. Cluster paired bootstrap by subject; provide medians, distributions, patient rank stability, calibration of extraction versions, ICC only within true second-reader people, and qualitative source-vendor site heterogeneity. The source n=59 is **a ceiling of metadata candidates**, not yet the verified physical/extractable patient count.

Secondary option [ATLAS challenge](https://atlas-challenge.u-bourgogne.fr/dataset) is officially gated to registered users, and the dataset's selected image phase can be arterial, venous or delayed; therefore **not automatic interchangeable portal-venous replication**. Do not bypass registration.
