#!/usr/bin/env python3
"""HCC LiverHccSeg MRI source PV x tumor NIfTI pixel and image-overlay audit.

Two modes:
  --offline-test: synthetic MRI + tumor NIfTI, no network, asserts pass/mismatch/empty.
  --live: consume previous MRI voxel/header audits, fetch ONLY selected PV MRI + mask
          members by HTTP Range from the official Zenodo ZIP, write reviewer-contact
          sheet PNG and patient-level QC report. Default max-cases=2 to limit HTTP 429.

Geometry and signal integrity are automated. EXPERT ROI REVIEW and pretreatment
chronology remain NOT_ASSESSED. Never promote patient eligibility from this test.
No DICOM/NIfTI image or expression data are uploaded to GitHub history.
"""
import argparse
import csv
import gzip
import json
import math
import os
import re
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZipFile

import numpy as np
from mri_mask_voxel_audit import HTTPRangeFile
from zenodo_nifti_zip_inventory import ARCHIVE, is_apple_sidecar

FILE_LIMIT = 200 * 1024 * 1024  # uncompressed per source image or mask
MAX_COMPRESSED = 96 * 1024 * 1024
MAX_CASES = 14
FIELDS = (
    "patient_id","source_phase","source_path","mask_path","qc_status",
    "source_shape","mask_shape","max_corner_offset_mm","tumor_voxels",
    "tumor_volume_ml","tumor_centroid_voxel_ijk","tumor_finite_voxel_fraction",
    "tumor_nonzero_signal_fraction","tumor_signal_median",
    "image_signal_iqr","overlay_png","expert_roi_review",
    "pretreatment_status","molecular_rna_qc","eligible_patient",
    "failure_reason"
)


def corner_offset_mm(a, b, shape):
    """max physical displacement of eight 3D FOV corners under two affines."""
    ends = [0, shape[0] - 1], [0, shape[1] - 1], [0, shape[2] - 1]
    corners = np.array([[x,y,z,1] for x in ends[0]
                        for y in ends[1] for z in ends[2]], dtype=np.float64).T
    delta = (np.asarray(a, dtype=float) - np.asarray(b, dtype=float)) @ corners
    return float(np.linalg.norm(delta[:3], axis=0).max())


def analyze_arrays(img, mask, image_affine, mask_affine, geometry_tol_mm=0.5):
    """Pixel-level QC; no diagnoses or expert ROI assertions."""
    img = np.asarray(img)
    mask = np.asarray(mask)
    if img.ndim != 3 or mask.ndim != 3 or img.shape != mask.shape:
        raise ValueError("SHAPE_MISMATCH")
    if not all(s > 1 for s in img.shape):
        raise ValueError("NON_3D_IMAGE")
    if not np.isfinite(image_affine).all() or not np.isfinite(mask_affine).all():
        raise ValueError("INVALID_AFFINE")
    offset = corner_offset_mm(image_affine, mask_affine, img.shape)
    if offset > geometry_tol_mm:
        raise ValueError(f"AFFINE_MISMATCH_{offset:.3f}_mm")
    tumor = np.isfinite(mask) & (mask > 0)
    count = int(np.count_nonzero(tumor))
    if not count:
        raise ValueError("EMPTY_TUMOR_MASK")
    if not np.isfinite(mask).all():
        raise ValueError("NONFINITE_TUMOR_MASK")
    present = np.asarray(img[tumor], dtype=np.float64)
    finite = np.isfinite(present)
    finite_fraction = float(np.mean(finite))
    if finite_fraction < 0.995:
        raise ValueError(f"TUMOR_SOURCE_NONFINITE_{finite_fraction:.4f}")
    clean = present[finite]
    global_values = np.asarray(img[np.isfinite(img)], dtype=np.float64)
    if not len(global_values):
        raise ValueError("NO_FINITE_SOURCE_PIXELS")
    p25, p75 = np.percentile(global_values, [25, 75])
    voxel_ml = abs(float(np.linalg.det(image_affine[:3, :3]))) / 1000.
    coords = np.argwhere(tumor)
    centroid = np.rint(coords.mean(axis=0)).astype(int)
    return {
        "qc_status": "PASS_IMAGE_PIXELS_WITH_MASK_HEADER_MATCH",
        "source_shape": "x".join(map(str, img.shape)),
        "mask_shape": "x".join(map(str, mask.shape)),
        "max_corner_offset_mm": round(offset, 5),
        "tumor_voxels": count,
        "tumor_volume_ml": round(voxel_ml * count, 4),
        "tumor_centroid_voxel_ijk": ",".join(map(str, centroid.tolist())),
        "tumor_finite_voxel_fraction": round(finite_fraction, 6),
        "tumor_nonzero_signal_fraction": round(float(np.mean(clean != 0)), 6),
        "tumor_signal_median": round(float(np.median(clean)), 6),
        "image_signal_iqr": round(float(p75-p25), 6),
        "_tumor_array": tumor,
        "_centroid": centroid,
    }


def create_overlay(img, qc, path, patient_id, phase):
    """Three orthogonal mask overlays. REVIEW IMAGE ONLY, no expert conclusion."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap
    x, y, z = map(int, qc["_centroid"])
    tumor = qc["_tumor_array"]
    slices = [
        (np.asarray(img[:,:,z]).T, tumor[:,:,z].T, "Axial (voxel k)"),
        (np.asarray(img[:,y,:]).T, tumor[:,y,:].T, "Coronal (voxel j)"),
        (np.asarray(img[x,:,:]).T, tumor[x,:,:].T, "Sagittal (voxel i)"),
    ]
    fig, axes = plt.subplots(1, 3, figsize=(12,4), constrained_layout=True)
    finite = np.asarray(img)[np.isfinite(img)]
    low, high = np.percentile(finite, [1, 99]) if len(finite) else (0.,1.)
    if not np.isfinite(low) or not np.isfinite(high) or low == high:
        low, high = 0.,1.
    for ax,(pixels,mask,axis) in zip(axes,slices):
        ax.imshow(pixels, cmap="gray", origin="lower", vmin=low, vmax=high)
        ax.contour(mask.astype(float), levels=[0.5], colors=["#e93b3b"], linewidths=1.2)
        ax.set_title(axis, fontsize=9)
        ax.axis("off")
    fig.suptitle(f"{patient_id} | {phase} | AUTOMATED QC: reviewer verification REQUIRED",
                 fontsize=10)
    fig.savefig(path, dpi=110, bbox_inches="tight")
    plt.close(fig)


def bounded_archive_member(archive, path, outdir):
    """Extract only approved ZIP member; hard cap compressed/uncompressed bytes.
    The local temporary NIfTI is deleted when context exits. ZIP CRC checked.
    """
    if path not in archive.namelist() or is_apple_sidecar(path):
        raise ValueError("ARCHIVE_MEMBER_NOT_FOUND")
    info=archive.getinfo(path)
    if info.is_dir() or info.file_size > MAX_COMPRESSED:
        raise ValueError("ZIP_MEMBER_LIMIT_EXCEEDED")
    safe_name="source.nii" if Path(path).name.lower()=="pv.nii.gz" else "mask.nii"
    output=Path(outdir)/safe_name
    total=0
    with archive.open(info) as source:
        with gzip.GzipFile(fileobj=source) as stream:
            with output.open("wb") as sink:
                while True:
                    buf=stream.read(1024*1024)
                    if not buf:
                        break
                    total+=len(buf)
                    if total > FILE_LIMIT:
                        raise ValueError("NIFTI_UNCOMPRESSED_LIMIT_EXCEEDED")
                    sink.write(buf)
    if total < 352:
        raise ValueError("NIFTI_TOO_SHORT")
    return output


def analyze_case(archive, patient, mask_path, output_dir):
    import nibabel as nib
    if not re.fullmatch(r"TCGA-[A-Z0-9]{2}-[A-Z0-9]{4}",patient):
        raise ValueError("MALFORMED_CASE_ID")
    if patient not in mask_path or "/" not in mask_path:
        raise ValueError("MASK_PATIENT_MISMATCH")
    parent=mask_path.rsplit("/",1)[0]+"/"
    pv=parent+"pv.nii.gz"
    result={"patient_id":patient,"source_phase":"PV","source_path":pv,
            "mask_path":mask_path,"expert_roi_review":"NOT_ASSESSED",
            "pretreatment_status":"NOT_ASSESSED","molecular_rna_qc":"NOT_ASSESSED",
            "eligible_patient":"NOT_ASSESSED","overlay_png":"","failure_reason":""}
    try:
        with tempfile.TemporaryDirectory(prefix="hcc_mri_nifti_") as td:
            mask_file=bounded_archive_member(archive,mask_path,td)
            source_file=bounded_archive_member(archive,pv,td)
            mask=nib.load(str(mask_file))
            source=nib.load(str(source_file))
            if len(source.shape)!=3 or len(mask.shape)!=3:
                raise ValueError("IMAGE_NOT_3D")
            mask_voxels=np.asanyarray(mask.dataobj)
            source_voxels=np.asanyarray(source.dataobj)
            qc=analyze_arrays(source_voxels,mask_voxels,source.affine,mask.affine)
            basename=patient+"_PV_mask_overlay.png"
            create_overlay(source_voxels,qc,Path(output_dir)/basename,patient,"PV")
            result.update({k:v for k,v in qc.items() if not k.startswith("_")})
            result["overlay_png"]=basename
    except Exception as exc:
        result.update(qc_status="FAIL_IMAGE_PIXEL_QC",
                      failure_reason=type(exc).__name__+": "+str(exc)[:160])
    return result


def offline_test():
    import nibabel as nib
    import numpy as np
    with tempfile.TemporaryDirectory() as td:
        affine=np.diag([1.1,1.1,2.5,1.])
        data=np.indices((20,24,12))[0].astype(np.float32)+25.
        mask=np.zeros((20,24,12), dtype=np.uint8)
        mask[7:13,9:15,4:8]=1
        image=nib.Nifti1Image(data,affine)
        roi=nib.Nifti1Image(mask,affine)
        nib.save(image,str(Path(td)/"source.nii.gz"))
        nib.save(roi,str(Path(td)/"mask.nii.gz"))
        i=nib.load(str(Path(td)/"source.nii.gz"))
        m=nib.load(str(Path(td)/"mask.nii.gz"))
        q=analyze_arrays(i.get_fdata(dtype=np.float32),np.asanyarray(m.dataobj),i.affine,m.affine)
        assert q["tumor_voxels"]==6*6*4
        assert q["tumor_volume_ml"] > 0
        assert q["qc_status"]=="PASS_IMAGE_PIXELS_WITH_MASK_HEADER_MATCH"
        output=Path(td)/"montage.png"
        create_overlay(np.asanyarray(i.dataobj),q,output,"TCGA-AA-0001","PV")
        assert output.exists() and output.stat().st_size > 1000
        def must_fail(img, roi, a, b, reason):
            try: analyze_arrays(img,roi,a,b)
            except ValueError as exc:
                assert reason in str(exc),str(exc)
            else: raise AssertionError("Expected "+reason)
        must_fail(data,mask[:,:,:-1],affine,affine,"SHAPE_MISMATCH")
        must_fail(data,mask,affine,affine+np.array([[0,0,0,5],[0,0,0,0],[0,0,0,0],[0,0,0,0]]),
                  "AFFINE_MISMATCH")
        must_fail(data,np.zeros_like(mask),affine,affine,"EMPTY_TUMOR_MASK")
        bad=data.copy()
        bad[9,10,5]=np.nan
        must_fail(bad,mask,affine,affine,"TUMOR_SOURCE_NONFINITE")
    print("HCC_MRI_PV_PIXEL_OVERLAY_OFFLINE_TEST_PASS")


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--offline-test",action="store_true")
    ap.add_argument("--input-dir",default="artifacts/hcc_mri")
    ap.add_argument("--out-dir",default="artifacts/hcc_mri_pv_overlay")
    ap.add_argument("--max-cases",type=int,default=2)
    ap.add_argument("--patients",nargs="*",default=[])
    args=ap.parse_args()
    if args.offline_test:
        offline_test()
        return
    if not (1<=args.max_cases<=MAX_CASES):
        raise ValueError("--max-cases must be between 1 and 14")
    with (Path(args.input_dir)/"tcga_liverhccseg_mri_mask_voxel_qc.csv").open(
            encoding="utf-8",newline="") as handle:
        candidates=list(csv.DictReader(handle))
    selected=[r for r in candidates
              if r["nifti_mask_voxel_status"]=="PASS_NONEMPTY_NIFTI_MASK"
              and (not args.patients or r["patient_id"] in args.patients)]
    selected=sorted(selected,key=lambda r:r["patient_id"])
    if not selected:
        raise ValueError("No previously verified MRI mask candidates")
    selected=selected[:args.max_cases]
    output=Path(args.out_dir)
    output.mkdir(parents=True,exist_ok=True)
    with ZipFile(HTTPRangeFile(ARCHIVE)) as zf:
        rows=[analyze_case(zf,c["patient_id"],c["nifti_member_path"],output)
              for c in selected]
    with (output/"mri_pv_image_mask_pixel_qc.csv").open(
            "w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS,extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    counts=Counter(r["qc_status"] for r in rows)
    summary={
        "status":"PASS_PILOT_PIXEL_QC" if counts.get("FAIL_IMAGE_PIXEL_QC",0)==0
                  else "PARTIAL_PILOT_PIXEL_QC",
        "generated_utc":datetime.now(timezone.utc).isoformat(),
        "requested_max_cases":args.max_cases,
        "examined_patients":len(rows),
        "passed_patients":counts.get("PASS_IMAGE_PIXELS_WITH_MASK_HEADER_MATCH",0),
        "failed_patients":counts.get("FAIL_IMAGE_PIXEL_QC",0),
        "all_14_patient_qc_completed":len(rows)==14 and not counts.get("FAIL_IMAGE_PIXEL_QC",0),
        "expert_roi_review_verified":0,
        "pretreatment_verified":0,
        "eligible_mri_rna_patients":"NOT_ASSESSED",
        "note":"Contact sheet images are automated reviewer aids, NOT reviewer approval."
    }
    (output/"mri_pv_image_mask_pixel_qc_summary.json").write_text(
        json.dumps(summary,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps(summary,ensure_ascii=False))
    if summary["failed_patients"]:
        raise SystemExit(1)


if __name__=="__main__":
    main()
