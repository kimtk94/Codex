#!/usr/bin/env python3
"""HCC registered-PV MRI anatomical reviewer contact sheets, not clinical approval.

Exactly 14 frozen index tumors; render arterial and official registered portal
venous MRI with R1/R2 contours in matching mask coordinates. The original NIfTI
files are fetched from published Zenodo ZIP with CRC; no MRI–RNA associations.
"""
import argparse
import csv
import hashlib
import json
import tempfile
from pathlib import Path
from zipfile import ZipFile

import numpy as np
from fast_zip_member_range import get_member_with_ranges
from mri_mask_voxel_audit import HTTPRangeFile
from mri_phase_mask_source_gate import frozen, inventory_member
from mri_p0_raw_vs_registered_pv_radiomics_pilot import orient_to_mask
from mri_pv_pixel_overlay_audit import corner_offset_mm
from zenodo_nifti_zip_inventory import ARCHIVE

PHASES = ("art", "art_pv")
READER_MASKS = ("rater1", "rater2")
OUT_HEADER = ("patient_id", "tumor_index", "phase_art_sha256", "phase_art_pv_sha256",
              "mask_r1_sha256", "mask_r2_sha256", "r1_roi_voxels", "r2_roi_voxels",
              "mask_dice", "registered_pv_affine_max_corner_mm",
              "selected_voxel_x", "selected_voxel_y", "selected_voxel_z",
              "review_png", "qualified_anatomy_review",
              "MRI_before_therapy", "RNA_same_index_lesion", "clinical_eligibility")

def center_and_slice(mask):
    indices = np.where(mask)
    if len(indices[0]) < 50:
        raise ValueError("Empty or insufficient tumor ROI")
    # Select representative z-slice with the maximal number of R1 tumor voxels.
    layer_counts = np.bincount(indices[2], minlength=mask.shape[2])
    z = int(np.argmax(layer_counts))
    current = np.where(mask[:, :, z])
    return (int(round(float(np.mean(current[0])))),
            int(round(float(np.mean(current[1])))), z)

def take_plane(v, plane, indices):
    x, y, z = indices
    if plane == "axial":
        return v[:, :, z].T
    if plane == "coronal":
        return v[:, y, :].T
    if plane == "sagittal":
        return v[x, :, :].T
    raise ValueError("unknown diagnostic plane")

def window(arr, liver_mask):
    finite = np.isfinite(arr)
    within = finite & (liver_mask > 0)
    pixels = arr[within]
    if pixels.size < 200 or not np.isfinite(pixels).all():
        raise ValueError("Insufficient finite liver pixels")
    lo, hi = np.percentile(pixels, (1, 99))
    if not (hi > lo):
        raise ValueError("Constant liver signal window")
    return float(lo), float(hi)

def render(out_path, pid, tumor_index, images, masks, liver):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    r1, r2 = (np.asarray(masks[r].dataobj) > 0 for r in READER_MASKS)
    coords = center_and_slice(r1)
    liver_arr = np.asarray(liver.dataobj) > 0
    fig, axes = plt.subplots(2, 3, figsize=(13.8, 8.8), layout="constrained")
    for row, (phase, image) in enumerate(images.items()):
        arr = np.asarray(image.dataobj, dtype=np.float32)
        lo, hi = window(arr, liver_arr)
        for col, plane in enumerate(("axial", "coronal", "sagittal")):
            ax = axes[row, col]
            frame = take_plane(arr, plane, coords)
            if not np.isfinite(frame).all():
                frame = np.nan_to_num(frame, nan=lo, posinf=hi, neginf=lo)
            ax.imshow(frame, cmap="gray", origin="lower", vmin=lo, vmax=hi,
                      interpolation="nearest")
            for seg, color, tag in ((r1, "#f15bb5", "R1"), (r2, "#00e5ff", "R2")):
                cut = take_plane(seg.astype(np.uint8), plane, coords)
                if np.any(cut) and np.any(cut == 0):
                    ax.contour(cut, levels=[0.5], colors=[color], linewidths=1.1)
            ax.set_title(f"{phase.upper().replace('_',' ')} | {plane} | index {coords}")
            ax.set_xlabel("Voxel grid only; not a diagnostic orientation")
            ax.set_xticks([])
            ax.set_yticks([])
            # Preserve physical millimetre dimensions: thick native MRI z
            # slices must not make coronal/sagittal tumor shape appear flat.
            spacing = np.linalg.norm(image.affine[:3, :3], axis=0)
            aspect = {"axial": spacing[1] / spacing[0],
                      "coronal": spacing[2] / spacing[0],
                      "sagittal": spacing[2] / spacing[1]}[plane]
            if not np.isfinite(aspect) or aspect <= 0:
                raise ValueError("Invalid non-isotropic NIfTI voxel spacing")
            ax.set_aspect(float(aspect))
    fig.suptitle(f"Public LiverHccSeg v1.1 | {pid} | locked tumor {tumor_index}\n"
                 "R1 (magenta) / R2 (cyan) index tumor outlines | HUMAN ANATOMY REVIEW NOT DONE",
                 fontsize=13)
    fig.legend(handles=[
        Line2D([], [], color="#f15bb5", label="reader1 tumor"),
        Line2D([], [], color="#00e5ff", label="reader2 tumor")],
        loc="lower center", bbox_to_anchor=(0.5, -0.01), ncol=2)
    fig.savefig(out_path, dpi=115, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return coords

def fetch_case(archive, pid, index, out_dir):
    import nibabel as nib
    names = ("art", "art_pv", "rater1_liver",
             f"rater1_tumor{index}", f"rater2_tumor{index}")
    with tempfile.TemporaryDirectory(prefix="hcc_review_") as temp:
        images, sha = {}, {}
        for name in names:
            member = inventory_member(archive.NameToInfo, pid, name + ".nii.gz")
            info = archive.getinfo(member)
            if not (100 < info.file_size <= 96 * 1024 * 1024):
                raise ValueError("Abnormal public NIfTI source member")
            blob = get_member_with_ranges(ARCHIVE, info, archive.fp.total)
            sha[name] = hashlib.sha256(blob).hexdigest()
            path = Path(temp) / (name + ".nii.gz")
            path.write_bytes(blob)
            images[name] = nib.load(str(path))
        r1 = images[f"rater1_tumor{index}"]
        r2 = images[f"rater2_tumor{index}"]
        liver = images["rater1_liver"]
        registered, order, signs = orient_to_mask(images["art_pv"], r1)
        if order != [0, 1, 2] or signs not in ([-1,-1,1], [1,-1,1]):
            raise ValueError("Unexpected registered PV source orientation")
        for im in (images["art"], registered, r2, liver):
            if im.shape != r1.shape or corner_offset_mm(im.affine, r1.affine, r1.shape) > 0.5:
                raise ValueError("Reviewer display source space not aligned")
        a = np.asarray(r1.dataobj) > 0
        b = np.asarray(r2.dataobj) > 0
        na, nb, both = int(a.sum()), int(b.sum()), int(np.sum(a & b))
        if min(na, nb) < 50:
            raise ValueError("Mask missing selected frozen lesion")
        dice = 2 * both / (na + nb)
        if not 0 <= dice <= 1:
            raise ValueError("Invalid mask overlap")
        png = out_dir / f"{pid}_tumor{index}_ART_vs_registeredPV_rater_masks.png"
        coords = render(png, pid, index,
                        {"arterial":images["art"], "registered_PV":registered},
                        {"rater1":r1, "rater2":r2}, liver)
        row = dict(patient_id=pid, tumor_index=index,
                   phase_art_sha256=sha["art"], phase_art_pv_sha256=sha["art_pv"],
                   mask_r1_sha256=sha[f"rater1_tumor{index}"],
                   mask_r2_sha256=sha[f"rater2_tumor{index}"],
                   r1_roi_voxels=na, r2_roi_voxels=nb,
                   mask_dice=round(dice, 6),
                   registered_pv_affine_max_corner_mm=round(float(
                       corner_offset_mm(registered.affine, r1.affine, r1.shape)), 6),
                   selected_voxel_x=coords[0], selected_voxel_y=coords[1],
                   selected_voxel_z=coords[2], review_png=png.name,
                   qualified_anatomy_review="NOT_ASSESSED",
                   MRI_before_therapy="NOT_ASSESSED",
                   RNA_same_index_lesion="NOT_ASSESSED",
                   clinical_eligibility="NOT_ASSESSED")
        print("HCC_P0_MRI_REVIEW_PANEL_GENERATED", pid, "tumor", index,
              "rater_dice", row["mask_dice"], flush=True)
        return row

def offline_test():
    a = np.zeros((8, 9, 10), dtype=np.uint8)
    a[2:7, 3:7, 4:7] = 1
    assert center_and_slice(a) == (4, 4, 4)
    assert take_plane(a, "axial", (4, 4, 4)).shape == (9, 8)
    assert take_plane(a, "coronal", (4, 4, 4)).shape == (10, 8)
    assert take_plane(a, "sagittal", (4, 4, 4)).shape == (10, 9)
    assert frozen()["TCGA-BC-A10Y"] == 3
    print("HCC_P0_REAL_REVIEWER_MONTAGE_SYNTHETIC_CASE_PASS")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline-test", action="store_true")
    ap.add_argument("--shard-index", type=int)
    ap.add_argument("--out-dir", default="artifacts/hcc_mri_anatomy_review")
    args = ap.parse_args()
    if args.offline_test:
        offline_test()
        return
    if args.shard_index is None or not 0 <= args.shard_index < 7:
        raise ValueError("Seven frozen 2-case shards required")
    patients = frozen()
    ids = sorted(patients)[2 * args.shard_index:2 * args.shard_index + 2]
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    with ZipFile(HTTPRangeFile(ARCHIVE)) as archive:
        rows = [fetch_case(archive, pid, patients[pid], out) for pid in ids]
    if len(rows) != 2 or any(r["clinical_eligibility"] != "NOT_ASSESSED"
                            or r["qualified_anatomy_review"] != "NOT_ASSESSED" for r in rows):
        raise ValueError("Two public cases/clinical HOLD required")
    with (out / f"hcc_mri_anatomy_review_shard_{args.shard_index}.csv").open(
            "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OUT_HEADER)
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps({"status": "ART_REGISTERED_PV_REVIEW_IMAGES_ONLY",
                      "n_cases": 2, "shard": args.shard_index,
                      "qualified_reviewer_pass": 0, "MRI_RNA_tests_run": 0,
                      "claim_ceiling": "S0"}))

if __name__ == "__main__":
    main()
