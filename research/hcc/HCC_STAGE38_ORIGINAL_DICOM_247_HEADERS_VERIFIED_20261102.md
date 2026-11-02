# HCC Stage 38 original DICOM series source audit

Verified actual GitHub Actions run: https://github.com/kimtk94/Codex/actions/runs/41383511403

- Five jobs succeeded (four sharded plus aggregate).
- Frozen MRI candidate patients: 14/14.
- 247 original DICOM source directories examined; 247 representative MR DICOM headers passed; 0 directory groups omitted by the 24-per-case cap; no header errors.
- 6 venous-like textual candidates in four patients (TCGA-DD-A4NH: 2; TCGA-DD-A4NJ: 2; TCGA-G3-A25T: 1; TCGA-G3-A3CJ: 1).
- Ten additional patients had no explicit venous wording in SeriesDescription/ProtocolName. Absence of wording is NOT absence of a venous series.
- Original DICOM source folder labels, patient ID and Study/Series/SOP UIDs are verified for sampled files. Actual selected portal-venous NIfTI-to-series source identity is NOT verified (0/14).
- MRI chronology relative to HCC treatment: NOT ASSESSED; same index lesion as GDC RNA specimen: NOT ASSESSED; independent radiologist: NOT ASSESSED.
- No biological MRI-RNA tests were run (0/12); claim ceiling S0.
- The full original archive MD5 was not verified. CRC was verified for sampled member files.

Aggregate artifact ID: 13114183240; artifact ZIP SHA256: 7788226e8296cef08e1bfa395edbd153cd73c021ef174b580fd867566be9e329.

Next: compare original pv.nii.gz header dimensions, pixel spacing and volume axis counts against original DICOM source series candidate geometry, without asserting identity from labels alone.
