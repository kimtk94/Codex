# HCC Stage 40 — original DICOM/PV NIfTI pixel pattern pilot (verified)

Actual successful GitHub Actions: https://github.com/kimtk94/Codex/actions/runs/41389903430

Official original source: LiverHccSeg v1.1 Zenodo 8179129. Pilot cases TCGA-BC-A3KG and TCGA-BC-A69I were preselected based exclusively on having four Stage39 source geometry-compatible series each.

## Verified actual source results

- Original PV NIfTI voxel volumes: 2/2 CRC-fetched and read.
- Original source DICOM geometry-compatible series: 8/8 tested (4 each patient).
- Independent source DICOM pixel samples: 24/24 CRC checked, PatientID/SeriesInstanceUID checked and matched to PV NIfTI by an explicitly restricted pixel-pattern procedure; 0 technical sample HOLD.
- One strong descriptive source series candidate per patient, **2/8 in total**. In each strong candidate, three original DICOM slices had highest absolute Pearson approximately **0.999998–1.000000**, with distinct corresponding NIfTI z indices (70,43,17) and consistent in-plane orientation transform required by the code's conservative strong-pattern rule.
- Competing geometry-compatible series had substantially weaker observed pixel correlations in this 24-sample pilot (not interpreted as actual different lesions without more evidence).
- The comparisons optimize 2D source-pixel Pearson over 8 transpose/reflection transformations and all native NIfTI z-slices using a fixed 48x48 sample grid. Therefore they **do not** establish full 3D image equality, original acquisition orientation and affine consistency, uniqueness among all possible series, same imaged lesion as RNA tissue, or pretreatment clinical status.

## Audit lineage

- Source script: research/hcc/ci/mri14_stage40_source_dicom_pv_pixel_pattern_pilot.py
- Workflow: .github/workflows/hcc-stage40-original-pv-dicom-pixel-pilot.yml
- Pinned Stage39 14-case 247-row and 83-nonunique-geometry candidate artifact from run #41384565388
- Successful Stage40 run #41389903430, result artifact ID **13117005705**, artifact ZIP SHA-256 **96741d95a0c70da738827f5239adc447f3bbe3720f47ade43592341fc06b2037**.
- The initial Stage40 run #41389701833 completed all 24 pixel computations but failed when serializing integer PV slice indices and had float32 Pearson rounding slightly above 1. The corrected run clipped numerical Pearson within [-1,1], serialized the slice IDs, and passed independent source/claim gate and artifact upload.

## Frozen clinical gates

Exact complete PV NIfTI-to-original DICOM source series 3D pixel and orientation identity: NOT ASSESSED. Authoritative MRI scan-before-HCC therapy chronology: NOT ASSESSED. Exact MRI imaged tumor lesion-to-GDC STAR RNA specimen/portion origin: NOT ASSESSED. Independent qualified abdominal radiologist original MRI anatomy acceptance: NOT ASSESSED. Clinical eligible patient n: **NOT_ASSESSED**, NOT 0 eligible. MRI–RNA biological tests **0/12**, claim ceiling **S0**.

**Next Stage41:** full actual original DICOM source slice stack for the 2 strong candidates, original native PV NIfTI pixel-value comparison accounting for DICOM image orientation, sorted slice positions, z-order, DICOM rescale scaling, and affine. Require consistent whole-volume pixel/physical source evidence before marking *technical* selected PV source identity. Clinical patient eligibility is independent of image source identity and stays HOLD.
