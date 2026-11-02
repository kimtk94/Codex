# HCC Stage39 — verified native PV NIfTI to DICOM source geometry

Verified GitHub Actions: https://github.com/kimtk94/Codex/actions/runs/41384565388

Actual original LiverHccSeg v1.1 source evidence:
- 14/14 original PV NIfTI headers verified via bounded source ZIP reads.
- 247 original DICOM per-directory headers cross-compared.
- In-plane image matrix compatible: 99 source directories.
- Matrix + pixel spacing compatible: 97 source directories.
- Matrix + spacing + source slice-count compatible: **83 source directories**.
- All **14/14 patients have multiple** three-way geometry-compatible series candidates; 4–10 candidates per person.
- Original selected PV DICOM-to-NIfTI source pixel identity is **NOT VERIFIED** (0/14 proven).
- Scan-before-HCC-treatment and imaged-lesion-to-GDC-RNA-aliquot chain: NOT VERIFIED.
- Clinical eligible n NOT_ASSESSED; biological association tests 0/12; claim ceiling S0.
- One DICOM sample per source folder; a folder does not prove a distinct source UID or unique selected PV.
- Original large ZIP full-file MD5 not independently verified; selected ZIP member CRC checked.

Permanent source code: research/hcc/ci/mri14_stage39_original_pv_nifti_dicom_geometry.py.
Workflow: .github/workflows/hcc-stage39-native-pv-nifti-dicom-geometry.yml.
Artifact ID **13115115792**; SHA256 e9be3021f794e68ad19eb654da875b483db35720c93ffe56f37c699c83cf4ced.

Next Stage40: pixel-level source series correlation / orientation verification against native PV NIfTI for the remaining ambiguous candidate series; expert radiology and clinical sample linkage remain separate HOLD gates.
