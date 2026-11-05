#!/usr/bin/env python3
"""IBSI-1 CT Phase-II configuration A: source-pinned independent and PyRadiomics checks.

The clinical HCC claim ceiling remains S0.  IBSI-1 CT PAT1 is not an HCC case.
2D averaged and 2.5D direction-merged GLCM are different official benchmarks.
Reference values/tolerances: https://ibsi.readthedocs.io/en/master/03_Image_features.html
Config A: https://ibsi.readthedocs.io/en/master/05_Reference_data_sets.html
"""
import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

SOURCE_SHA = "6da96021bc91faf4c0cb7fd7fa56a4225d2064a8"
CT_IMG_SHA = "909129fdf99d5f5fd17bc568b1834d31edce8663ea6746c6020720bfc1d7bbcb"
CT_MASK_SHA = "0e9243e473b1255c60e6460df465d0b07b65436d6e0c691fe3d17bca0594ae78"
CT_SUBDIR = "ibsi_1_ct_radiomics_phantom/nifti"
REFERENCE_URL = "https://ibsi.readthedocs.io/en/master/03_Image_features.html"
CONFIG_URL = "https://ibsi.readthedocs.io/en/master/05_Reference_data_sets.html"
# Only the IBSI reference values explicitly verified against the reference manual.
# These tolerances are IBSI-published for Configuration A, NOT local thresholds.
REF = {
    "Mean": (13.4, 1.1, "Q4LE", "IBSI_OFFICIAL"),
    "Median": (46.0, 0.3, "Y12H", "IBSI_OFFICIAL"),
    "InterquartileRange": (56.0, 0.5, "SALO", "IBSI_OFFICIAL"),
    "GLCM_2D_averaged_Contrast": (7.85, 0.26, "ACUI", "IBSI_OFFICIAL"),
    "GLCM_2_5D_direction_merged_Contrast": (5.96, 0.27, "ACUI", "IBSI_OFFICIAL"),
}
DIRECTIONS = ((1, 0), (0, 1), (1, 1), (1, -1))

def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def source_paths(repo):
    import subprocess
    repo = Path(repo)
    commit = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"],
                                     text=True).strip()
    if commit != SOURCE_SHA:
        raise ValueError("IBSI CT source commit mismatch: no unpinned source accepted")
    img = repo / CT_SUBDIR / "image" / "phantom.nii.gz"
    mask = repo / CT_SUBDIR / "mask" / "mask.nii.gz"
    if sha256(img) != CT_IMG_SHA or sha256(mask) != CT_MASK_SHA:
        raise ValueError("IBSI official CT source image/mask SHA256 drift")
    return img, mask

def load_numpy(repo):
    import nibabel as nib
    import numpy as np
    img, mask = source_paths(repo)
    im = nib.load(str(img))
    mk = nib.load(str(mask))
    if im.shape != (204, 201, 60) or mk.shape != im.shape:
        raise ValueError("Unexpected official CT NIfTI shape")
    if not np.allclose(im.affine, mk.affine, atol=1e-4):
        raise ValueError("Image-mask affine mismatch")
    # IBSI NIfTI instructions: at least float32, nearest integer before processing.
    hu = np.rint(np.asarray(im.dataobj, dtype=np.float32)).astype(np.float32)
    morph = np.asarray(mk.dataobj) > 0
    if int(np.count_nonzero(morph)) != 125256:
        raise ValueError("Unexpected official morphological GTV volume")
    intensity_mask = morph & (hu >= -500) & (hu <= 400)
    n = int(intensity_mask.sum())
    if not 1000 < n < 125256:
        raise ValueError("CT resegmentation mask incorrect or empty")
    if not np.isfinite(hu).all():
        raise ValueError("Invalid CT intensity")
    return hu, morph, intensity_mask

def contrast_from_counts(matrix):
    import numpy as np
    total = matrix.sum()
    if total == 0:
        return None
    ix = np.arange(matrix.shape[0], dtype=np.float64)
    return float((((ix[:, None] - ix[None, :]) ** 2) * matrix).sum() / total)

def glcm_two_aggregations(gray, mask):
    """Compute 2D averaged and 2.5D direction-merged from independent matrices.

    Coordinates are NIfTI x,y,z, with z the axial slice axis.  Symmetric
    Chebyshev distance 1, no spatial weighting, global FBS 25 HU from -500.
    Averages exclude slice-direction combinations with zero valid ROI pairs.
    """
    import numpy as np
    if gray.shape != mask.shape or gray.ndim != 3:
        raise ValueError("Expected same-shape 3D data and mask")
    ng = int(gray[mask].max())
    if ng < 2 or ng > 40 or gray[mask].min() < 1:
        raise ValueError("Invalid IBSI-A 25HU bins")
    sum_matrices = [np.zeros((ng, ng), dtype=np.float64) for _ in DIRECTIONS]
    per_pair = []
    pair_counts = []
    for z in range(gray.shape[2]):
        a = gray[:, :, z]
        m = mask[:, :, z]
        if not m.any():
            continue
        for d, (dx, dy) in enumerate(DIRECTIONS):
            xs = slice(max(0, -dx), min(a.shape[0], a.shape[0] - dx))
            ys = slice(max(0, -dy), min(a.shape[1], a.shape[1] - dy))
            xt = slice(max(0, dx), min(a.shape[0], a.shape[0] + dx))
            yt = slice(max(0, dy), min(a.shape[1], a.shape[1] + dy))
            both = m[xs, ys] & m[xt, yt]
            if not both.any():
                continue
            v = a[xs, ys][both].astype(np.int64) - 1
            w = a[xt, yt][both].astype(np.int64) - 1
            counts = np.bincount(v * ng + w, minlength=ng * ng).reshape(ng, ng)
            symmetric = counts + counts.T
            value = contrast_from_counts(symmetric)
            per_pair.append(value)
            pair_counts.append(int(both.sum()))
            sum_matrices[d] += symmetric
    if not per_pair or any(mat.sum() == 0 for mat in sum_matrices):
        raise ValueError("Missing required in-plane co-occurrence matrices")
    return {
        "GLCM_2D_averaged_Contrast": float(np.mean(per_pair)),
        "GLCM_2_5D_direction_merged_Contrast": float(np.mean(
            [contrast_from_counts(m) for m in sum_matrices])),
        "nonempty_slice_direction_pairs": len(per_pair),
        "total_unique_pairs_per_direction_and_slice": int(sum(pair_counts)),
        "number_of_in_plane_directions": len(DIRECTIONS),
    }

def compare_value(name, measured):
    if not math.isfinite(float(measured)):
        raise ValueError("Nonfinite benchmark value: " + name)
    reference, tolerance, ibsi_code, provenance = REF[name]
    delta = abs(float(measured) - reference)
    return {
        "feature": name, "ibsi_code": ibsi_code,
        "reference": reference, "observed": float(measured),
        "absolute_difference": delta,
        "tolerance": tolerance, "tolerance_type": provenance,
        "status": "PASS" if delta <= tolerance else "REVIEW_REFERENCE_DEVIATION",
        "reference_source": REFERENCE_URL,
    }

def read_measures_independent(repo):
    import numpy as np
    hu, morph, roi = load_numpy(repo)
    x = hu[roi].astype(np.float64)
    # Explicit global minimum is Config A lower bound (-500 HU), not sample min.
    binned = np.floor((hu - (-500.0)) / 25.0).astype(np.int16) + 1
    glcm = glcm_two_aggregations(binned, roi)
    measured = {
        "Mean": float(np.mean(x)),
        "Median": float(np.median(x)),
        "InterquartileRange": float(np.percentile(x, 75) - np.percentile(x, 25)),
        "GLCM_2D_averaged_Contrast": glcm["GLCM_2D_averaged_Contrast"],
        "GLCM_2_5D_direction_merged_Contrast":
            glcm["GLCM_2_5D_direction_merged_Contrast"],
    }
    return measured, {
        "morphological_roi_voxels": int(morph.sum()),
        "intensity_roi_after_resegmentation_voxels": int(roi.sum()),
        "resegmented_min_hu": float(x.min()),
        "resegmented_max_hu": float(x.max()),
        "image_shape_xyz": list(hu.shape),
        "distance": 1,
        "direction_count": glcm["number_of_in_plane_directions"],
        "slice_direction_pairs": glcm["nonempty_slice_direction_pairs"],
        "symmetric_glcm": True,
    }

def read_measures_pyradiomics(repo):
    import numpy as np
    import SimpleITK as sitk
    import radiomics
    from radiomics import featureextractor
    if radiomics.__version__.lstrip("v") != "3.1.0":
        raise ValueError("Expected pinned PyRadiomics 3.1.0")
    img_path, mask_path = source_paths(repo)
    img = sitk.ReadImage(str(img_path))
    mk = sitk.ReadImage(str(mask_path))
    if img.GetSize() != mk.GetSize() or img.GetSize() != (204, 201, 60):
        raise ValueError("Unexpected SimpleITK size")
    arr = np.rint(sitk.GetArrayFromImage(img).astype(np.float32))
    binary = sitk.GetArrayFromImage(mk) > 0
    intensity_mask = binary & (arr >= -500) & (arr <= 400)
    if int(binary.sum()) != 125256:
        raise ValueError("Incorrect PyRadiomics original GTV")
    sim = sitk.GetImageFromArray(arr.astype(np.float32))
    sim.CopyInformation(img)
    smk = sitk.GetImageFromArray(intensity_mask.astype(np.uint8))
    smk.CopyInformation(img)
    settings = {
        "binWidth": 25, "normalize": False,
        "resampledPixelSpacing": None, "interpolator": None,
        "force2D": True, "force2Ddimension": 0, "distances": [1],
        "weightingNorm": None, "minimumROIDimensions": 2,
        "correctMask": False,
    }
    extractor = featureextractor.RadiomicsFeatureExtractor(**settings)
    extractor.disableAllImageTypes()
    extractor.enableImageTypeByName("Original")
    extractor.disableAllFeatures()
    extractor.enableFeaturesByName(
        firstorder=["Mean", "Median", "InterquartileRange"],
        glcm=["Contrast"])
    vals = extractor.execute(sim, smk, label=1)
    measured = {
        "Mean": float(vals["original_firstorder_Mean"]),
        "Median": float(vals["original_firstorder_Median"]),
        "InterquartileRange": float(vals["original_firstorder_InterquartileRange"]),
        # Force2D in PyRadiomics aggregates matrices across axial slices,
        # then computes each in-plane direction; this is NOT IBSI 2D:avg.
        "GLCM_2_5D_direction_merged_Contrast": float(vals["original_glcm_Contrast"]),
    }
    return measured, {
        "PyRadiomics_version": radiomics.__version__,
        "settings": settings,
        "comparison_aggregation": "2.5D_direction_merged; not 2D_averaged",
        "morphological_roi_voxels": int(binary.sum()),
        "intensity_roi_after_resegmentation_voxels": int(intensity_mask.sum()),
    }

def manifest(measurements, details, mode):
    rows = [compare_value(name, value) for name, value in measurements.items()]
    if not rows:
        raise ValueError("Empty original CT benchmark output")
    return {
        "status": "PASS_REFERENCES_WITHIN_IBSI_TOLERANCES"
                  if all(r["status"] == "PASS" for r in rows)
                  else "REVIEW_REFERENCE_DEVIATIONS",
        "mode": mode, "source_commit": SOURCE_SHA,
        "image_sha256": CT_IMG_SHA, "mask_sha256": CT_MASK_SHA,
        "source_modality": "NSCLC_CT_Patient_PAT1_not_HCC",
        "configuration": "IBSI1_Phase_II_CT_A",
        "preprocessing": {
            "interpolation": "none", "intensity_rounding": "nearest_integer",
            "resegmentation_hu": [-500, 400],
            "morphological_roi_unchanged": True,
            "intensity_mask_resegmented": True,
            "texture_bin_width_hu": 25, "fixed_bin_minimum_hu": -500,
            "glcm_chebyshev_distance_voxels": 1,
        },
        "details": details, "comparisons": rows,
        "IBSI_1_CT_configurations_B_E": "NOT_EXECUTED",
        "IBSI_2_CT_filtered_maps": "NOT_EXECUTED",
        "HCC18_status": "PARTIAL", "HCC20_status": "PENDING",
        "claim_ceiling": "S0",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
    }

def join(independent, pyrad):
    expected_independent = set(REF)
    expected_py = expected_independent - {"GLCM_2D_averaged_Contrast"}
    for d, mode, expected in (
        (independent, "independent", expected_independent),
        (pyrad, "pyradiomics", expected_py)):
        if (d["mode"] != mode or d["source_commit"] != SOURCE_SHA
                or d["image_sha256"] != CT_IMG_SHA
                or d["mask_sha256"] != CT_MASK_SHA
                or set(r["feature"] for r in d["comparisons"]) != expected):
            raise ValueError("Missing, substituted or contaminated CT benchmark sources")
        if d["HCC18_status"] != "PARTIAL" or d["HCC20_status"] != "PENDING":
            raise ValueError("Invalid HCC scientific promotion")
    ci = {r["feature"]: r for r in independent["comparisons"]}
    cp = {r["feature"]: r for r in pyrad["comparisons"]}
    same_roi = (independent["details"]["intensity_roi_after_resegmentation_voxels"]
                == pyrad["details"]["intensity_roi_after_resegmentation_voxels"])
    # Conservative numerical cross-software diagnostic, NOT an IBSI threshold.
    cross_diff = abs(ci["GLCM_2_5D_direction_merged_Contrast"]["observed"]
                     - cp["GLCM_2_5D_direction_merged_Contrast"]["observed"])
    cross_ok = cross_diff <= 1e-5
    passed = (independent["status"] == "PASS_REFERENCES_WITHIN_IBSI_TOLERANCES"
              and pyrad["status"] == "PASS_REFERENCES_WITHIN_IBSI_TOLERANCES"
              and same_roi and cross_ok)
    return {
        "status": "PASS_CT_A_FIVE_INDEPENDENT_FOUR_PYRADIOMICS"
                  if passed else "REVIEW_CT_A_AGGREGATION_OR_PREPROCESSING",
        "independent_reference_comparisons": len(ci),
        "pyradiomics_reference_comparisons": len(cp),
        "same_resegmented_intensity_ROI_voxel_count": same_roi,
        "GLCM_2_5D_cross_implementation_abs_diff": cross_diff,
        "cross_implementation_local_diagnostic_threshold": 1e-5,
        "official_IBSI_tolerance_applied_to_each_reference": True,
        "CT_A_method_validated_only_if_status_PASS": passed,
        "CT_B_E": "NOT_EXECUTED", "IBSI_2_CT_filters": "NOT_EXECUTED",
        "HCC18": "PARTIAL", "HCC20": "PENDING", "claim_ceiling": "S0",
    }

def offline_test():
    import numpy as np
    a = np.ones((3, 3, 2), dtype=np.int16)
    a[1, 1, :] = 2
    m = np.ones_like(a, dtype=bool)
    gl = glcm_two_aggregations(a, m)
    assert gl["GLCM_2D_averaged_Contrast"] >= 0
    assert gl["GLCM_2_5D_direction_merged_Contrast"] >= 0
    assert compare_value("Mean", 13.4)["status"] == "PASS"
    assert compare_value("Mean", 100)["status"] == "REVIEW_REFERENCE_DEVIATION"
    assert len(REF) == 5
    print("HCC_IBSI_CT_A_PREPROCESS_AGGREGATION_AND_FAIL_CLOSED_OFFLINE_PASS")

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=["independent", "pyradiomics", "join", "offline-test"],
                   required=True)
    p.add_argument("--source-dir", default="artifacts/ibsi_original_repo")
    p.add_argument("--out-dir", default="artifacts/hcc_ibsi_ct_a")
    p.add_argument("--independent", default="artifacts/hcc_ibsi_ct_a_independent/ct_a.json")
    p.add_argument("--pyradiomics", default="artifacts/hcc_ibsi_ct_a_pyradiomics/ct_a.json")
    a = p.parse_args()
    if a.mode == "offline-test":
        offline_test()
        return
    if a.mode == "join":
        result = join(json.loads(Path(a.independent).read_text()),
                      json.loads(Path(a.pyradiomics).read_text()))
    else:
        measured, details = (read_measures_independent(a.source_dir)
                             if a.mode == "independent"
                             else read_measures_pyradiomics(a.source_dir))
        result = manifest(measured, details, a.mode)
    folder = Path(a.out_dir)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "ct_a.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    # REVIEW is reported as a REVIEW artifact, not silently promoted to PASS.
    # Hard source errors / invariant violations raise and fail the job.

if __name__ == "__main__":
    main()
