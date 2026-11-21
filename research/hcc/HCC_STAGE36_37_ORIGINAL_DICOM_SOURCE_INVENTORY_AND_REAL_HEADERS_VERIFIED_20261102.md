# HCC Stages 36–37 — official original LiverHccSeg DICOM source verification, real CI evidence

**Evidence date:** 2026-11-02 KST. Source is [LiverHccSeg v1.1 Zenodo 8179129](https://zenodo.org/records/8179129), `dicoms.zip` original source DICOM archive. This analysis is **not** a clinical radiogenomics source-pair qualification.

## Stage 36: source ZIP directory without multi-GB full download

- [Actual GitHub Actions #41324933919](https://github.com/kimtk94/Codex/actions/runs/41324933919), **SUCCESS**. Original archive **37,115 central-directory entries**, **36,795 nondirectory members**.
- **14/14** frozen TCGA-LIHC MRI candidate IDs occur in original `dicoms.zip` paths, and **14/14** have DICOM-like source members (original patient/date/sequence organization). **0/14** have a filename path that matches a literal `PV`/`venous`/`portal` naming hint.
- Source ZIP was read by **bounded HTTP byte ranges**, not downloaded in full. The original archive **publisher-declared** MD5 `1ff9f35e77d2892909dd2c67eea196b3` has **not been independently recomputed** in this workflow.
- Artifact **13090992355**, ZIP SHA256 digest `c90fcaf4a22ab35922b88513e5342c2ee5e126ccc7071a0b29f8319d930fc905`.
- Source script `ci/mri14_stage36_original_dicom_source_directory.py`; Actions workflow `.github/workflows/hcc-stage36-original-14-dicom-archive-directory.yml`.

## Stage 37: real original DICOM header read and source UID validation

- [Actual GitHub Actions #41325316550](https://github.com/kimtk94/Codex/actions/runs/41325316550), **SUCCESS** after correcting output CSV `Modality` case-sensitive header name. The earlier #41325144663 had **14/14 valid original DICOM header reads but failed when writing the CSV** due to one output schema mismatch; no false image-processing success was claimed until the new run finished.
- **14/14** original DICOM members successfully downloaded individually by bounded ZIP member reads, with original source ZIP member CRC enforced; DICOM `PatientID` matched the frozen TCGA case, `Modality=MR`, and the sampled `StudyInstanceUID`, `SeriesInstanceUID`, `SOPInstanceUID` all passed original header structure validity checks. **0/14 original DICOM header HOLD**.
- Each case used **exactly one reproducibly selected source DICOM image** chosen without RNA/feature/clinical outcome screening. The sampled series is **NOT necessarily the frozen selected portal-venous MRI** or the largest MRI index lesion.
- Source ZIP **whole-file MD5 remains unverified**. Per-member ZIP CRC and individual SHA256 are reported in artifact, and per-case original DICOM header values / series description are preserved for subsequent source-series audit. This does not certify entire archive integrity or exact NIfTI-to-DICOM source conversion.
- Artifact **13090869031**, ZIP SHA256 digest `169fda910bffe31209767589391fcbbbb4eecaacf6285c46b19eeecf872f8baf`; contains `stage37_original14_one_DICOM_header_sample.csv`, `stage37_original14_DICOM_header_HOLD.csv` and report/summary files.
- Source script `ci/mri14_stage37_original_dicom_source_header_probe.py`; workflow `.github/workflows/hcc-stage37-original-dicom-source-header.yml`.

## Scientific gate decisions (do not conflate evidence levels)

| Question | Evidence | Decision |
|---|---|---|
| Original source archive public accessibility for all 14 TCGA-LIHC MRI candidates | 14/14 path and 14/14 real DICOM header | **TECHNICAL GO** |
| At least one original MR DICOM Study/Series UID per candidate | 14/14 source header + exact patient ID | **SOURCE TECHNICAL GO** (sampled source series only) |
| Original DICOM series is the selected portal-venous source NIfTI and frozen index lesion | **0/14 source-series matches validated** | **HOLD** |
| Image acquisition before all index-lesion-relevant HCC treatment | **0/14 case-level chronology established** | **HOLD** |
| MRI index lesion tissue matches the GDC STAR Primary Tumor RNA aliquot / portion | **0/14 exact lesion chain established** | **HOLD** |
| Independent abdominal radiologist assessment of original anatomy and phase | **0/14 new independent adjudications** | **HOLD** |
| Frozen 12 MRI–RNA pathway tests | **0/12 executed** | **STOP**, no clinical/biological effect claims |

**Important:** the figures `0/14` for clinical evidence refer to **source-proven cases**, not proof zero true matched cases or clinical exclusions. Qualified eligible n remains `NOT_ASSESSED`; publication/biology claim ceiling remains **S0**.

**Next Stage38:** inspect distinct original DICOM series headers for selected subjects (without whole archive transfer) to identify credible venous-phase series **candidates** by original `SeriesDescription`/`ProtocolName` and source imaging parameters, then independently compare their source image geometry/content to frozen native/registered phase NIfTI. A filename/SeriesDescription match alone cannot authorize clinical same-lesion pretreatment claims.
