#!/usr/bin/env python3
"""HCC Stage 33: original OpenSwissHCC v2 paired reader-mask technical QC.

Evaluate only the *three* frozen size-selected index HCC lesions out of 59
independent patients that have a second manual venous mask (8/90 is a
different lesion-level denominator). One original source-image is used for
both masks. No MRI-RNA, segmentation clinical diagnosis, reader consensus,
ICC extrapolation, radiomics feature or re-selection is performed.
"""
import argparse
import csv
import hashlib
import io
import json
import math
import tempfile
import zipfile
from pathlib import Path

REC = "https://zenodo.org/records/21992461"
MASK_URL = REC + "/files/derivatives.zip?download=1"
IMAGE_URLS = (
    (44, REC + "/files/sub-001-sub-044.zip?download=1"),
    (88, REC + "/files/sub-044-sub-088.zip?download=1"),
    (132, REC + "/files/sub-088-sub-132.zip?download=1"),
)
PRIMARY_EXPECTED = {
    "openswisshcc_v2_all_90_venous_HCC_lesion_size_and_primary_flags.csv":
        "a8291b4de55fdec75a59378218c017aedfa4bcb950ac4bde9813780c8b43fc42",
    "openswisshcc_v2_primary_1_HCC_venous_lesion_per_subject.csv":
        "4e1882540f9d165a279bd5afab1b5983f5570e1e94bdebbb2fdb798c41f61432",
    "openswisshcc_v2_primary_selection_summary.json":
        "31590e93813c0be862050a26865688b9ed8313185c366962875a7566d50e1a11",
}
SOURCE90_EXPECTED = {
    "openswisshcc_v2_external_hcc_venous_access_preflight.json":
        "c928c2dcd23df70dca80ab560fba78657ea0867eb79d7a162e1d8980f4a08693",
    "openswisshcc_v2_venous_hcc_mask_candidate_manifest.csv":
        "2ab07d78df1c01b35de17218356d9423d384e503409187f9de0227a433536622",
}
PROFILE_MEMBER = "external_venous_59_primary_patient_source_profiles.csv"
PROFILE_SHA256 = "50de8bbaa897f99aa8b2bc9b7a0cd7d972b820e5cfaa9af4399adee4b964dba6"
EXPECTED_PRIMARY = 59
EXPECTED_SECOND = 3
N_CONSIDERED = 90
OUTPUT_CSV = "stage33_external_primary_3_reader_pairs.csv"
OUTPUT_HOLD = "stage33_source_pair_HOLD.csv"
OUTPUT_JSON = "stage33_reader_mask_technical_qc.json"


def check(ok, reason):
    if not ok:
        raise ValueError(reason)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def csv_bytes(data):
    return list(csv.DictReader(io.StringIO(data.decode("utf-8-sig"))))


def read_pinned(archive, expected):
    with zipfile.ZipFile(archive) as z:
        check(set(z.namelist()) == set(expected), "PINNED_SOURCE_ARCHIVE_MEMBERS_CHANGED")
        data = {name: z.read(name) for name in expected}
    for name, digest in expected.items():
        check(sha256(data[name]) == digest, "ORIGINAL_SOURCE_MEMBER_SHA_DRIFT:" + name)
    return data


def original_roster(primary_zip, source90_zip, profiles_zip):
    p = read_pinned(primary_zip, PRIMARY_EXPECTED)
    ninety = read_pinned(source90_zip, SOURCE90_EXPECTED)
    with zipfile.ZipFile(profiles_zip) as z:
        profile_bytes = z.read(PROFILE_MEMBER)
    check(sha256(profile_bytes) == PROFILE_SHA256, "ORIGINAL_59_SOURCE_PROFILES_SHA_DRIFT")
    roster = csv_bytes(p["openswisshcc_v2_primary_1_HCC_venous_lesion_per_subject.csv"])
    all_mask_rows = csv_bytes(
        ninety["openswisshcc_v2_venous_hcc_mask_candidate_manifest.csv"])
    profiles = csv_bytes(profile_bytes)
    primary_info = json.loads(p["openswisshcc_v2_primary_selection_summary.json"])
    source_info = json.loads(ninety["openswisshcc_v2_external_hcc_venous_access_preflight.json"])
    check(len(roster) == EXPECTED_PRIMARY and len(profiles) == EXPECTED_PRIMARY,
          "ORIGINAL_59_SOURCE_ROSTER_NOT_REPRODUCIBLE")
    check(len(all_mask_rows) == N_CONSIDERED, "ORIGINAL_90_SOURCE_ROSTER_DRIFT")
    check(len({r["subject"] for r in roster}) == EXPECTED_PRIMARY, "DUPLICATE_PRIMARY_SUBJECT")
    check(len({r["patient_id"] for r in profiles}) == EXPECTED_PRIMARY, "DUPLICATE_SOURCE_PROFILE")
    check(len({(r["subject"], r["lesion"]) for r in all_mask_rows}) == N_CONSIDERED,
          "DUPLICATE_SOURCE_LESION")
    check(primary_info["second_reader_primary_subset"] == EXPECTED_SECOND
          and source_info["HCC_venous_second_reader_masks_found"] == 8
          and primary_info["claim_ceiling"] == source_info["claim_ceiling"] == "S0",
          "SECOND_READER_SOURCE_DENOMINATOR_CHANGED")
    perlesion = {(r["subject"], r["lesion"]): r for r in all_mask_rows}
    perpatient = {r["patient_id"]: r for r in profiles}
    selected = []
    for r in roster:
        key = (r["subject"], r["selected_lesion"])
        check(key in perlesion, "SELECTED_INDEX_NOT_IN_ORIGINAL_SOURCE")
        l = perlesion[key]
        original_present = r["second_reader_mask_present"] == "YES"
        second_path = l["venous_lesion_second_mask_path"]
        check(original_present == bool(second_path), "SECOND_READER_ROSTER_CONFLICT")
        check(r["source_mask_path"] == l["venous_lesion_first_mask_path"],
              "FIRST_READER_ROSTER_CONFLICT")
        if not original_present:
            continue
        q = perpatient[r["subject"]]
        check(q["selected_lesion"] == r["selected_lesion"]
              and q["source_mask_sha256"] and q["source_venous_image_sha256"],
              "SOURCE_59_CASE_IDENTITY_NOT_VERIFIED")
        selected.append((r, l, q))
    check(len(selected) == EXPECTED_SECOND, "EXACT_THREE_PRIMARY_READER_PAIRS_REQUIRED")
    return sorted(selected, key=lambda x: x[0]["subject"])


def image_group(pid):
    n = int(pid.split("-")[1])
    for upper, url in IMAGE_URLS:
        if n <= upper:
            return url
    raise ValueError("IMAGE_PATIENT_NOT_IN_OFFICIAL_OPEN_SWISS_ARCHIVES")


def image_member(archive, pid):
    suffix = "/" + pid + "/dyn/" + pid + "_acq-water_phase-venous_T1w.nii.gz"
    found = [n for n in archive.namelist() if ("/" + n).endswith(suffix)]
    check(len(found) == 1, "UNIQUE_ORIGINAL_VENOUS_IMAGE_REQUIRED:" + pid)
    return found[0]


def ranges_member(archive, url, path):
    from fast_zip_member_range import get_member_with_ranges
    info = archive.getinfo(path)
    check(352 < info.file_size < 96*1024*1024, "SOURCE_NIFTI_MEMBER_SIZE_INVALID")
    data = get_member_with_ranges(url, info, archive.fp.total)
    check(len(data) == info.file_size, "INCOMPLETE_ORIGINAL_ZENODO_SOURCE_NIFTI")
    return data


def corners_mm(a, b, dims):
    import numpy as np
    coords = [[i, j, k, 1.0] for i in (0, dims[0]-1)
                             for j in (0, dims[1]-1)
                             for k in (0, dims[2]-1)]
    xyz = np.array(coords, dtype=float).T
    return float(np.linalg.norm(((a @ xyz) - (b @ xyz))[:3, :], axis=0).max())


def masks_and_images(image_bytes, one_bytes, two_bytes):
    import nibabel as nib
    import numpy as np
    with tempfile.TemporaryDirectory(prefix="hcc_stage33_source_") as folder:
        paths = [Path(folder)/n for n in ("image.nii.gz", "first.nii.gz", "second.nii.gz")]
        for path, blob in zip(paths, (image_bytes, one_bytes, two_bytes)):
            path.write_bytes(blob)
        img, first, second = [nib.load(str(p)) for p in paths]
        check(img.ndim == first.ndim == second.ndim == 3, "NOT_3D_NATIVE_NIFTI")
        check(img.shape == first.shape == second.shape, "ORIGINAL_SOURCE_SHAPES_DIFFER")
        offsets = (corners_mm(img.affine, first.affine, img.shape),
                   corners_mm(img.affine, second.affine, img.shape),
                   corners_mm(first.affine, second.affine, img.shape))
        check(all(math.isfinite(d) and d <= 0.5 for d in offsets),
              "FIRST_SECOND_MASK_SOURCE_IMAGE_AFFINE_MISMATCH")
        raw1 = np.asanyarray(first.dataobj)
        raw2 = np.asanyarray(second.dataobj)
        check(np.isfinite(raw1).all() and np.isfinite(raw2).all(),
              "NONFINITE_SOURCE_READER_MASK")
        check(np.array_equal(np.unique(raw1), np.intersect1d(np.unique(raw1), [0,1]))
              and np.array_equal(np.unique(raw2), np.intersect1d(np.unique(raw2), [0,1])),
              "READER_MASK_NOT_EXACT_BINARY_LABEL_1")
        mask1, mask2 = raw1 == 1, raw2 == 1
        check(50 <= int(mask1.sum()) < mask1.size
              and 50 <= int(mask2.sum()) < mask2.size,
              "EMPTY_TOO_SMALL_OR_FULL_READER_MASK")
        arr = np.asarray(img.dataobj, dtype=np.float32)
        check(np.isfinite(arr[mask1 | mask2]).all(), "NONFINITE_IMAGE_IN_TWO_READER_ROIS")
        return (arr, mask1, mask2, np.asarray(img.affine),
                tuple(float(z) for z in img.header.get_zooms()[:3]), offsets)


def calculate_metrics(mask1, mask2, affine, spacing):
    import numpy as np
    from scipy.ndimage import binary_erosion
    from scipy.spatial import cKDTree
    a, b = int(mask1.sum()), int(mask2.sum())
    both = int(np.logical_and(mask1, mask2).sum())
    union = a + b - both
    dice = 2 * both / (a+b)
    jac = both / union
    det = abs(float(np.linalg.det(affine[:3, :3])))
    check(det > 0 and math.isfinite(det), "INVALID_REAL_VOXEL_VOLUME")
    # Connected boundary points of each 3D mask in true physical world coordinates,
    # not distances between array indices or a resampled 3mm mask.
    surf1 = mask1 & ~binary_erosion(mask1)
    surf2 = mask2 & ~binary_erosion(mask2)
    p1 = np.argwhere(surf1)
    p2 = np.argwhere(surf2)
    check(len(p1) and len(p2), "EMPTY_NATIVE_READER_MASK_SURFACE")
    world1 = p1 @ affine[:3,:3].T + affine[:3,3]
    world2 = p2 @ affine[:3,:3].T + affine[:3,3]
    d12 = cKDTree(world2).query(world1, k=1)[0]
    d21 = cKDTree(world1).query(world2, k=1)[0]
    combined = np.concatenate([d12,d21])
    return {
        "first_mask_voxels": a, "second_mask_voxels": b,
        "first_mask_volume_ml": round(a*det/1000, 6),
        "second_mask_volume_ml": round(b*det/1000, 6),
        "intersection_voxels": both,
        "dice": round(float(dice), 6),
        "jaccard": round(float(jac), 6),
        "symmetric_hd95_world_mm": round(float(np.percentile(combined,95)), 6),
        "symmetric_mean_surface_distance_world_mm": round(float(combined.mean()), 6),
        "symmetric_max_surface_distance_world_mm": round(float(combined.max()), 6),
        "relative_volume_difference_pct": round(100*(b-a)/a,6),
        "world_voxel_volume_mm3": round(det,6),
        "source_voxel_spacing_xyz_mm": "|".join(str(round(x,6)) for x in spacing),
    }


def create_panels(arr, mask1, mask2, pid, lesion, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    center = np.rint(np.argwhere(mask1 | mask2).mean(axis=0)).astype(int)
    fig, axs = plt.subplots(1,3, figsize=(12,4))
    slices = (arr[center[0], :, :], arr[:, center[1], :], arr[:,:,center[2]])
    m1 = (mask1[center[0],:,:], mask1[:,center[1],:], mask1[:,:,center[2]])
    m2 = (mask2[center[0],:,:], mask2[:,center[1],:], mask2[:,:,center[2]])
    for i,ax in enumerate(axs):
        view = np.rot90(slices[i])
        v1, v2 = np.rot90(m1[i]), np.rot90(m2[i])
        q = np.percentile(view[np.isfinite(view)], [2,98])
        if q[1] <= q[0]:
            q = [float(view.min()), float(view.max())+1]
        ax.imshow(view, cmap="gray", vmin=q[0], vmax=q[1], interpolation="nearest")
        for m,c in ((v1,"#ffb347"),(v2,"#00ced1")):
            if m.any() and (~m).any():
                ax.contour(m.astype(float), levels=[0.5], colors=[c], linewidths=1.2)
        ax.set_title(("voxel axis 0", "voxel axis 1", "voxel axis 2")[i])
        ax.axis("off")
    fig.suptitle(f"{pid}/{lesion}: reader 1 orange · reader 2 cyan | SOURCE axis views only")
    fig.tight_layout()
    fig.savefig(path,dpi=150,bbox_inches="tight")
    plt.close(fig)


def inspect_pair(row, lesion, profile, archive, image_archive, img_url, out):
    pid = row["subject"]
    imagepath = image_member(image_archive, pid)
    original_one = row["source_mask_path"]
    original_two = lesion["venous_lesion_second_mask_path"]
    check(original_one != original_two, "SAME_SOURCE_READER_FILE_REUSED")
    image_bytes = ranges_member(image_archive, img_url, imagepath)
    one_bytes = ranges_member(archive, MASK_URL, original_one)
    two_bytes = ranges_member(archive, MASK_URL, original_two)
    check(sha256(image_bytes) == profile["source_venous_image_sha256"],
          "STAGE33_VENOUS_IMAGE_NOT_IDENTICAL_TO_VERIFIED_59_SOURCE")
    check(sha256(one_bytes) == profile["source_mask_sha256"],
          "STAGE33_FIRST_MASK_NOT_IDENTICAL_TO_VERIFIED_59_SOURCE")
    arr, mask1, mask2, affine, spacing, offsets = masks_and_images(
        image_bytes, one_bytes, two_bytes)
    origvox = int(profile["mask_voxels"])
    check(origvox == int(mask1.sum()), "STAGE33_FIRST_MASK_VOXEL_COUNT_DRIFT")
    metrics = calculate_metrics(mask1, mask2, affine, spacing)
    panel = "stage33_" + pid + "_" + row["selected_lesion"] + "_reader_overlay.png"
    create_panels(arr, mask1, mask2, pid, row["selected_lesion"], out/panel)
    return {
        "subject": pid, "source_selected_lesion": row["selected_lesion"],
        "first_reader_original_mask": original_one,
        "second_reader_original_mask": original_two,
        "source_original_image": imagepath,
        "original_image_sha256": sha256(image_bytes),
        "first_mask_sha256": sha256(one_bytes),
        "second_mask_sha256": sha256(two_bytes),
        "image_first_affine_corner_mm": round(offsets[0],6),
        "image_second_affine_corner_mm": round(offsets[1],6),
        "first_second_affine_corner_mm": round(offsets[2],6),
        **metrics, "overlay_panel": panel,
        "analysis_status": "PASS_SOURCE_PAIRED_MASK_TECHNICAL_GEOMETRY_ONLY",
        "independent_radiologist_anatomy_qualification": "NOT_ASSESSED",
        "generalizable_two_reader_ICC": "NOT_ASSESSED",
        "MRI_RNA_tests": 0,
        "claim_ceiling": "S0",
    }


def write_csv(path, rows, fallback):
    with path.open("w", newline="",encoding="utf8") as f:
        cols = list(rows[0]) if rows else fallback
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)


def offline():
    import numpy as np
    a=np.zeros((15,15,15),dtype=bool)
    b=np.zeros_like(a)
    a[3:10,3:10,3:10]=True
    b[3:10,3:10,3:10]=True
    m=calculate_metrics(a,b,np.eye(4),(1,1,1))
    check(m["dice"]==1 and m["jaccard"]==1 and m["symmetric_hd95_world_mm"]==0,
          "OFFLINE_IDENTICAL_MASK_METRIC_FAILED")
    b[:]=False
    b[4:11,3:10,3:10]=True
    s=calculate_metrics(a,b,np.diag([2.,1.,1.,1.]),(2,1,1))
    check(0 < s["dice"] < 1 and s["symmetric_hd95_world_mm"]>0,
          "OFFLINE_SHIFT_IN_PHYSICAL_MM_FAILED")
    check(corners_mm(np.eye(4),np.eye(4),a.shape)==0,"OFFLINE_AFFINE_CORNERS_FAILED")
    check(corners_mm(np.eye(4),np.diag([1.,1.,1.,1.]),a.shape)==0,
          "OFFLINE_AFFINE_IDENTITY_FAILED")
    print("HCC_STAGE33_READER_MASK_PHYSICAL_SPACE_NEGATIVE_AND_IDENTICAL_FIXTURES_PASS")


def run(args):
    from mri_mask_voxel_audit import HTTPRangeFile
    selected = original_roster(args.primary_source_zip, args.source90_zip, args.profile_source_zip)
    out = args.out_dir
    out.mkdir(parents=True,exist_ok=True)
    passed, held = [], []
    with zipfile.ZipFile(HTTPRangeFile(MASK_URL)) as masks:
        currenturl = None
        image_archive = None
        try:
            for row,lesion,profile in selected:
                pid = row["subject"]
                try:
                    url = image_group(pid)
                    if url != currenturl:
                        if image_archive: image_archive.close()
                        image_archive = zipfile.ZipFile(HTTPRangeFile(url))
                        currenturl = url
                    result = inspect_pair(row,lesion,profile,masks,image_archive,url,out)
                    passed.append(result)
                    print("HCC_STAGE33_ORIGINAL_TWO_READER_SOURCE_PASS",
                          pid,row["selected_lesion"],result["dice"],result["symmetric_hd95_world_mm"],
                          flush=True)
                except Exception as exc:
                    held.append({"subject":pid,"source_selected_lesion":row["selected_lesion"],
                                 "error_type":type(exc).__name__, "error_reason":str(exc)[:400],
                                 "source_mask_overlap": "NOT_ESTIMATED",
                                 "clinical_qualification":"NOT_ASSESSED","claim_ceiling":"S0"})
                    print("HCC_STAGE33_SOURCE_PAIR_HOLD",pid,type(exc).__name__,str(exc)[:160],flush=True)
        finally:
            if image_archive:image_archive.close()
    summary = {
        "stage":"HCC_STAGE33_ORIGINAL_VENOUS_TWO_READER_PRIMARY_INDEX_ROI_QC",
        "source_original_59_extraction_run":41221356861,
        "selected_independent_external_patients":59,
        "original_HCC_venous_lesion_candidates":90,
        "original_venous_HCC_lesions_with_second_reader":8,
        "frozen_index_primary_lesions_with_second_reader":3,
        "index_pair_success_n":len(passed),
        "index_pair_hold_n":len(held),
        "technical_valid_pairs":len(passed),
        "paired_mask_dice":{r["subject"]:r["dice"] for r in passed},
        "paired_mask_symmetric_hd95_world_mm":{
            r["subject"]:r["symmetric_hd95_world_mm"] for r in passed},
        "dataset_wide_reviewer_reproducibility":"NOT_ESTABLISHED_ONLY_THREE_INDEX_LESIONS",
        "clinical_anatomic_independent_expert_review":"NOT_ASSESSED",
        "MRI_RNA_biological_tests":0,
        "diagnostic_predictive_utility":"NOT_ESTABLISHED",
        "claim_ceiling":"S0",
        "status":"PASS_LIMITED_DESCRIPTIVE_TWO_READER_QC" if len(passed)==3 and not held
                 else "HOLD_INCOMPLETE_ORIGINAL_TWO_READER_PAIRS"
    }
    write_csv(out/OUTPUT_CSV,passed,["subject","source_selected_lesion","dice","jaccard",
                                    "symmetric_hd95_world_mm","claim_ceiling"])
    write_csv(out/OUTPUT_HOLD,held,["subject","source_selected_lesion","error_type","error_reason",
                                     "source_mask_overlap","clinical_qualification","claim_ceiling"])
    (out/OUTPUT_JSON).write_text(json.dumps(summary,indent=2)+"\n",encoding="utf8")
    lines=[
        "# HCC Stage33 source-matched two-reader index lesion masks — external n=3 only",
        "",
        f"- Original source 59 patient indices; only **3** selected index lesions have reader-2 masks (8/90 all-lesion masks is not 8/59).",
        f"- Two original reader masks, original venous source NIfTI and frozen source SHA-256 verified for **{len(passed)}/3**; technical HOLD **{len(held)}/3**.",
        "- Volumetric Dice/Jaccard, symmetric HD95 and surface distance use source physical voxel-center world coordinates, no resampling.",
        "- No ICC extrapolation; no clinical anatomical qualification; no diagnosis, MRI-RNA or outcome model. **S0**.",
        "",
        "| Patient | ROI | Dice | Jaccard | HD95 (mm) | Signed R2 vs R1 volume difference (%) |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for x in passed:
        lines.append("| "+x["subject"]+" | "+x["source_selected_lesion"]+" | "+
                     f'{x["dice"]:.3f} | {x["jaccard"]:.3f} | {x["symmetric_hd95_world_mm"]:.3f} | '+
                     f'{x["relative_volume_difference_pct"]:+.1f} |')
    for h in held:
        lines.append("| "+h["subject"]+" | "+h["source_selected_lesion"]+" | HOLD | HOLD | HOLD | HOLD |")
    report="\n".join(lines)+"\n"
    (out/"stage33_source_pair_technical_report.md").write_text(report,encoding="utf8")
    import os
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"],"a") as f:f.write(report)
    check(len(passed)+len(held)==EXPECTED_SECOND, "THREE_READER_PAIR_ACCOUNTING_DRIFT")
    if held:
        raise ValueError("HCC_STAGE33_REAL_ORIGINAL_NIFTI_PAIRS_INCOMPLETE_HOLD")
    print("HCC_STAGE33_3_OF_3_ORIGINAL_SOURCE_READER_PAIR_TECHNICAL_PASS",
          json.dumps(summary,sort_keys=True),flush=True)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--offline-test",action="store_true")
    parser.add_argument("--primary-source-zip",type=Path)
    parser.add_argument("--source90-zip",type=Path)
    parser.add_argument("--profile-source-zip",type=Path)
    parser.add_argument("--out-dir",type=Path,default=Path("artifacts/hcc_stage33_reader_qc"))
    args=parser.parse_args()
    offline()
    if args.offline_test:
        return
    check(all((args.primary_source_zip,args.source90_zip,args.profile_source_zip)),
          "ORIGINAL_THREE_ARTIFACT_INPUTS_REQUIRED")
    run(args)


if __name__=="__main__":
    main()
