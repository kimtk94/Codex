# HCC G3 — MRI source-phase and tumor-mask geometry review

Baseline 2026-10-30 KST. **Gate HCC-12 = PARTIAL, not qualified patient count.**

## Verified technical findings

Source: https://zenodo.org/records/8179129
GitHub live audit: https://github.com/kimtk94/Codex/actions/runs/41061027979

- 14 of 14 MRI HCC tumor masks: ZIP CRC, valid NIfTI and nonempty voxel checks.
- 70 source NIfTI headers queried with bounded HTTP Range access, without downloading complete MRI volumes.
- PV: 14/14 source-mask header-compatible; ART: 14/14.
- ART_PV: 0/14 compatible, 14/14 affine mismatches. Never substitute this image for PV/ART using an untransformed tumor mask.
- PRE: 13/14 compatible; DEL: 13/14. Both mismatches are in TCGA-BC-A10Y.
- The initial audit used an affine-element screen; its successor uses maximum FOV corner displacement in **millimetres** with threshold 0.5 mm. Confirm latest CI before promoting any geometry status.
- Expert overlay accepted: 0/14. Treatment-before-imaging relationship verified: 0/14. Fully eligible MRI–tumor RNA patient n: NOT ASSESSED.
- Matching shape/affine supports technical image-mask geometry but does **not** prove that the contour depicts the intended HCC lesion, treatment timing, ROI reproducibility or clinical eligibility.

## Phase lock proposal (must freeze before RNA association)

- Primary MRI phase: portal venous (PV), only after expert overlay/image quality review.
- Arterial (ART): separately declared sensitivity analysis, not mixed with PV as independent subjects.
- ART_PV: blocked until explicit geometric transformation plus review (currently mismatched 14/14).
- PRE/DEL: exploratory only, and exclude TCGA-BC-A10Y pairings pending registration.
- Patient-level unit is one distinct TCGA person. The selected mask is rater1_tumor1; additional tumors and raters must be inventoried and analysis rules frozen.
- Never select phase, reader or feature by smallest RNA-seq association p-value.

## Expert manual review checklist for each candidate

1. Record exact source image path, tumor mask path, mask reader, imaging phase and hash, with study-patient identity confirmed.
2. Check full 3D source-mask geometry including dimensionality, qform/sform, orientation, affine and physical-space overlay in axial/coronal/sagittal planes.
3. Confirm the tumor contour is anatomically within liver and follows the suspected HCC lesion, rather than background, liver-only tissue, neighboring structures or scan artifact.
4. Assess mask validity, volume plausibility, multiple lesions and rater disagreement (and document reviewer qualifications).
5. Verify pretreatment acquisition, tumor clinical chronology and eligibility through clinical source metadata; do not compare TCIA shifted DICOM dates to GDC absolute dates.
6. Record quality as VERIFIED_BY_REVIEWER / PENDING_REVIEW / EXCLUDED_WITH_REASON with reviewer/date and reason, without inferring that a negative result is simply a missing scan.
7. Only combine with expression once RNA file-level sample ID, counts, tumor purity proxies and normalization QC are verified.
8. Archive per-case decisions and full exclusion counts; no full MRI or RNA raw data should be committed into public Git.

## Claim discipline

- MRI header-compatible cases remain S0 manuscript evidence (technical feasibility).
- Before S1: source MRI voxels and overlays, clinical timing, RNA counts and sample QC, and full eligibility flow must be confirmed.
- Independent RNA association and any significance statement requires pre-registered feature/pathway family, BH FDR and robustness.
- If registration is not proved, suspend radiomics association rather than silently fixing phase differences.

## Machine evidence

Artifacts: tcga_liverhccseg_mri_image_mask_header_qc.csv, tcga_liverhccseg_mri_image_mask_header_summary.json.
Manual review roster: HCC_G3_PATIENT_IMAGE_REVIEW_QUEUE.csv.
Canonical standard: HCC_VERIFICATION_AND_PUBLICATION_FRAMEWORK.md and HCC_VERIFICATION_LEDGER.csv.


## Next gate: real MRI PV signal and clinical ROI overlay

The initial 2026-10-30 source-mask check validated only NIfTI headers: PV/ART 14/14 with compatible affine. That is necessary but **not sufficient** to consider a tumor mask anatomically correct.

1. Run `mri_pv_pixel_overlay_audit.py` with two pilot MRI patients first, using the exact publicly versioned LiverHccSeg ZIP and the previous tumor-mask QC manifest. Its strict pixel checks include 3D shape, full FOV physical corner offset ≤0.5 mm, nonempty mask, MRI signal finite inside tumor, tumor volume and 3-plane PNG overlay.
2. Reviewers must inspect the actual axial/coronal/sagittal tumor overlays and document clinical/anatomical correctness and preprocessing suitability; automated PNG creation **does not mean pass**.
3. A separate GDC RNA manifest records file IDs, MD5 and file-specific tumor sample barcodes. Same-patient multi-aliquot RNA files must be resolved before choosing expression inputs.
4. Only after source pixel QC, qualified reviewer approval, clinical pretreatment status and counts-level RNA QC may `HCC-12` progress beyond PARTIAL and claims exceed S0 if all other gates pass.

`HCC MRI PV Pixel Overlay Pilot` is an opt-in workflow with inputs `source_run_id` and `max_cases`, artifact outputs of patient PNGs and qc CSV/JSON. GitHub requires a workflow file on the **default branch** to enable its manual trigger in the Actions UI; the new file is currently on open PR #228, so do not claim a live pixel audit has already run or manual dispatch is available. Prior source workflow artifact retention is 30 days.
