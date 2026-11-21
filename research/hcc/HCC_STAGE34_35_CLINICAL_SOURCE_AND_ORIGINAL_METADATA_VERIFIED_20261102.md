# HCC Stage 34 and Stage 35 — verified original clinical-source and official metadata decisions (2026-11-02)

## Execution source of truth

- [Stage34 actual successful Actions #41255479989](https://github.com/kimtk94/Codex/actions/runs/41255479989): **3/3 jobs SUCCESS**, including 5 negative source fixtures, frozen 14-case clinical-source reconciliation, artifact restore and final fail-closed clinical claim gate. Artifact **13063830926**, ZIP digest SHA256 **149b06b46ca505208e6ad279a95a0426615f43dd9c033315a6eab6d357574dd1**.
- [Stage35 official LiverHccSeg Excel source Actions #41255480020](https://github.com/kimtk94/Codex/actions/runs/41255480020): **SUCCESS**, original [Zenodo v1.1 record 8179129](https://zenodo.org/records/8179129), `LiverHccSeg_MetaData.xlsx` **MD5 37806f09955aa198ab8e50e0e2929da7 verified**. Artifact **13062990996**, digest SHA256 **c23a3bb5865ad6a160009d47dd5c21f136191dbe079e3d749aef7cd141f19d26**.
- Scripts and Actions workflows: `ci/mri14_stage34_clinical_source_gate.py`, `ci/mri14_stage35_official_dicom_metadata_source_preflight.py`, `.github/workflows/hcc-mri14-stage34-clinical-source-gate.yml` and `.github/workflows/hcc-mri14-stage35-official-source-uid.yml`.

## Frozen 14-person patient and source status

| Gate | Actual result | Meaning |
|---|---:|---|
| Original 14 selected index tumors and GDC STAR Primary Tumor RNA case/sample barcodes | 14/14 PASS | Technical *same case*, NOT proof RNA comes from specific MRI tumor lesion |
| Stage34 original pre-specimen dated Yes treatment records | 10 | 9 in 4 patients with **HCC diagnosis context**, 1 in different organ (Cecum/Appendix; `TCGA-BC-A5W4`) |
| Source evidence review P0 / P1 / P2 | 4 / 5 / 5 | Priority not eligibility or exclusion |
| Original official Excel MD5 | PASS | Exact original 12.9 kB source metadata obtained |
| Frozen 14 TCGA IDs literally found in original Excel | 14/14 | Original spreadsheet patient row presence only |
| Both explicit original metadata `StudyInstanceUID` and `SeriesInstanceUID` columns | **0/14** | **Neither UID header exists in original spreadsheet** |
| Study/Series UIDs independently matched to original selected source DICOM | **0/14** | Need source original DICOM / official TCIA series metadata |
| MRI scan-to-HCC treatment temporal evidence | **0/14 verified** | Not zero true cases; none yet clinically proven |
| Exact imaged index tumor to GDC RNA specimen/portion evidence | **0/14 verified** | Not zero biologically matched cases; unassessed |
| Independent expert original MRI lesion/registration clinical acceptance | **0/14 verified** | Not automatically inferred from manual source masks |
| Clinically eligible or excluded denominator | **NOT_ASSESSED** | Clinical unknown, not 0 eligible or 14 excluded |
| Frozen Hallmark biological association tests | **0/12** | STOP pending clinical gate |
| Publication clinical/biological claim ceiling | **S0** | Methods-only claims can be evaluated separately |

**CAUTION:** The original public source description says `dicoms.zip` (~1.7GB) contains original DICOM images organized by patient/date/sequence. Its archive **MD5 on the Zenodo record is 1ff9f35e77d2892909dd2c67eea196b3**. Stage35 validated the Excel MD5, **not** this large ZIP MD5 or a DICOM UID. Do not confuse archive-declared MD5 with verified download checksum.

## Technical conclusions and next stages

Stage34 verifies exactly 14 source candidates, 4 HCC-context pre-specimen treatment review flags, one other-organ event, no source-based verified pretreatment scan or precise lesion-to-tissue chain. Clinical eligibility still HOLD.

Stage35 proves the published Excel metadata alone is insufficient to yield a **source-authenticated Study/Series UID**: explicit UID-header count is empty, candidates **0/14**. This is an evidence limitation, not a software parsing failure. The next rational attempt is **bounded HTTP Range inventory of original source `dicoms.zip` central directory**, followed, *only if correct original series is uniquely identified*, by bounded original DICOM member read and per-patient UID / acquisition parameter checks. The source ZIP file may not be assumed to have been fully checksummed if only its directory is retrieved.

Unchanged gates: external MRI source technical methods **GO**, independent abdominal radiologist anatomy **HOLD**, MRI–RNA same-tumor pretreatment patient evidence **HOLD**, biological tests **STOP 0/12**. Public source metadata alone cannot certify patient-level treatment chronology due to TCIA date shifting relative to GDC day offsets.
