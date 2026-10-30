#!/usr/bin/env python3
"""LiverHccSeg MRI tumor-mask ↔ source-phase NIfTI header geometry prescreen.

Reads at most 352 uncompressed bytes of each publicly available source image
and tumor mask using bounded ZIP HTTP-range access. Never returns image pixels.
A matching header affine/shape does NOT prove tumor location, acquisition
timing, segmentation quality, or expert image-overlay acceptance.
"""
import argparse
import csv
import gzip
import json
import math
import struct
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZipFile

import numpy as np
from mri_mask_voxel_audit import HTTPRangeFile
from zenodo_nifti_zip_inventory import ARCHIVE, is_apple_sidecar

PHASES = ("pv.nii.gz", "art.nii.gz", "art_pv.nii.gz", "pre.nii.gz", "del.nii.gz")
FIELDNAMES = (
    "patient_id", "mask_path", "source_phase", "source_path",
    "mask_shape", "source_shape", "mask_spacing", "source_spacing",
    "mask_xform", "source_xform", "max_affine_difference_mm",
    "geometry_status", "expert_overlay_status", "treatment_timing_status",
    "radiogenomics_eligibility"
)


def parse_header(data):
    if len(data) < 352 or struct.unpack_from("<I", data, 0)[0] != 348:
        raise ValueError("Not a valid little-endian NIfTI-1 header")
    if data[344:348] != b"n+1\x00":
        raise ValueError("Not NIfTI-1 single-file magic")
    dim = struct.unpack_from("<8h", data, 40)
    nd = dim[0]
    if nd not in (3, 4) or (nd == 4 and dim[4] != 1):
        raise ValueError("Not single-volume 3D NIfTI")
    shape = tuple(dim[1:4])
    if any(n < 1 or n > 4096 for n in shape):
        raise ValueError("Invalid spatial dimensions")
    pixdim = struct.unpack_from("<8f", data, 76)
    spacing = tuple(pixdim[1:4])
    if any(not math.isfinite(n) or n <= 0 for n in spacing):
        raise ValueError("Invalid voxel spacing")
    qcode, scode = struct.unpack_from("<2h", data, 252)
    if scode:
        affine = np.array([struct.unpack_from("<4f", data, 280 + i*16)
                           for i in range(3)] + [[0., 0., 0., 1.]], dtype=float)
        transform = "sform"
    elif qcode:
        b, c, d = struct.unpack_from("<3f", data, 256)
        norm = b*b + c*c + d*d
        if not all(math.isfinite(x) for x in (b, c, d)) or norm > 1.001:
            raise ValueError("Invalid quaternion")
        a = math.sqrt(max(0., 1. - norm))
        if norm > 1.:
            scale = math.sqrt(norm)
            b, c, d = b/scale, c/scale, d/scale
        rot = np.array([
            [a*a+b*b-c*c-d*d, 2*(b*c-a*d), 2*(b*d+a*c)],
            [2*(b*c+a*d), a*a+c*c-b*b-d*d, 2*(c*d-a*b)],
            [2*(b*d-a*c), 2*(c*d+a*b), a*a+d*d-c*c-b*b],
        ], dtype=float)
        qfac = -1. if pixdim[0] < 0 else 1.
        affine = np.eye(4)
        affine[:3, :3] = rot @ np.diag([*spacing[:2], spacing[2]*qfac])
        affine[:3, 3] = struct.unpack_from("<3f", data, 268)
        transform = "qform"
    else:
        affine = None
        transform = "none"
    if affine is not None:
        if not np.isfinite(affine).all() or abs(np.linalg.det(affine[:3,:3])) < 1.e-8:
            raise ValueError("Invalid or singular image affine")
    return {"shape": shape, "spacing": spacing,
            "transform": transform, "affine": affine}


def geometry(mask, source):
    if mask["shape"] != source["shape"]:
        return "SHAPE_MISMATCH", None
    if mask["affine"] is None or source["affine"] is None:
        return "NO_RELIABLE_SPATIAL_TRANSFORM", None
    # Voxel-to-world transforms must agree, including orientation/offset.
    # A 0.1mm matrix-element threshold avoids small float formatting changes.
    diff = float(np.max(np.abs(mask["affine"] - source["affine"])))
    if diff > 0.1:
        return "AFFINE_MISMATCH", diff
    return "PASS_HEADER_GEOMETRY_ONLY", diff


def header_only(archive, info):
    # Reading only the header makes no claim to CRC or valid image voxels.
    # A separate audit CRC-checks one tumor NIfTI for each patient.
    if info.file_size > 1024 * 1024 * 1024:
        raise ValueError("Suspiciously large archive member")
    with archive.open(info) as zipped:
        if info.filename.lower().endswith(".gz"):
            with gzip.GzipFile(fileobj=zipped) as nifti:
                data = nifti.read(352)
        else:
            data = zipped.read(352)
    return parse_header(data)


def run(cases, archive):
    index = {info.filename: info for info in archive.infolist()
             if not info.is_dir() and not is_apple_sidecar(info.filename)}
    rows = []
    for case in sorted(cases, key=lambda x: x["patient_id"]):
        pid = case["patient_id"]
        mask_path = case["nifti_member_path"]
        if case["nifti_mask_voxel_status"] != "PASS_NONEMPTY_NIFTI_MASK":
            raise ValueError("Unverified mask input for " + pid)
        if mask_path not in index or pid not in mask_path:
            raise ValueError("Archive mask missing/malformed for " + pid)
        parent = mask_path.rsplit("/", 1)[0] + "/"
        mask = header_only(archive, index[mask_path])
        candidates = [
            (phase, parent + phase) for phase in PHASES
            if parent + phase in index
        ]
        if not candidates:
            rows.append({
                "patient_id": pid, "mask_path": mask_path,
                "geometry_status": "NO_SOURCE_PHASE_FILES",
                "expert_overlay_status": "NOT_ASSESSED",
                "treatment_timing_status": "NOT_ASSESSED",
                "radiogenomics_eligibility": "NOT_ASSESSED",
            })
            continue
        for phase, source_path in candidates:
            item = {
                "patient_id": pid, "mask_path": mask_path,
                "source_phase": phase, "source_path": source_path,
                "mask_shape": "x".join(map(str, mask["shape"])),
                "mask_spacing": "x".join(f"{n:.6g}" for n in mask["spacing"]),
                "mask_xform": mask["transform"],
                "expert_overlay_status": "NOT_ASSESSED",
                "treatment_timing_status": "NOT_ASSESSED",
                "radiogenomics_eligibility": "NOT_ASSESSED",
            }
            try:
                source = header_only(archive, index[source_path])
                outcome, maxdiff = geometry(mask, source)
                item.update({
                    "source_shape": "x".join(map(str, source["shape"])),
                    "source_spacing": "x".join(f"{n:.6g}" for n in source["spacing"]),
                    "source_xform": source["transform"],
                    "max_affine_difference_mm": "" if maxdiff is None else f"{maxdiff:.5g}",
                    "geometry_status": outcome,
                })
            except Exception as exc:
                item["geometry_status"] = "SOURCE_HEADER_ERROR_" + type(exc).__name__
            rows.append(item)
    return rows


def summarize(rows, expected):
    by_patient = {}
    for row in rows:
        by_patient.setdefault(row["patient_id"], []).append(row["geometry_status"])
    if set(by_patient) != expected:
        raise ValueError("Missing case in geometry report")
    pass_ids = sorted(pid for pid, results in by_patient.items()
                      if "PASS_HEADER_GEOMETRY_ONLY" in results)
    summary = {
        "status": "PASS_HEADER_AUDIT_EXECUTED",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "tumor_mask_patient_candidates": len(expected),
        "source_phase_headers_examined": sum(
            bool(r.get("source_phase")) for r in rows),
        "patients_with_at_least_one_header_geometry_match": len(pass_ids),
        "patient_ids_with_header_geometry_match": pass_ids,
        "status_counts": dict(Counter(r["geometry_status"] for r in rows)),
        "expert_overlay_verified_patients": 0,
        "pretreatment_verified_patients": 0,
        "qualified_mri_rna_patients": "NOT_ASSESSED",
        "warnings": [
            "Header match is technical geometry compatibility, not expert visual overlay QC.",
            "Individual phase/mask files might share shape but not anatomical meaning.",
            "No original source MRI voxel values were read or validated.",
        ],
    }
    return summary


def offline_test():
    def create(shape=(2,3,4), offset=0., scode=1, pix=(1.,1.,2.)):
        b=bytearray(352)
        struct.pack_into("<I",b,0,348)
        struct.pack_into("<8h",b,40,3,*shape,1,1,1,1)
        struct.pack_into("<8f",b,76,1.,*pix,1.,1.,1.,1.)
        struct.pack_into("<2h",b,252,0,scode)
        struct.pack_into("<4f",b,280,pix[0],0.,0.,offset)
        struct.pack_into("<4f",b,296,0.,pix[1],0.,0.)
        struct.pack_into("<4f",b,312,0.,0.,pix[2],0.)
        b[344:348]=b"n+1\x00"
        return parse_header(bytes(b))
    assert geometry(create(),create())[0] == "PASS_HEADER_GEOMETRY_ONLY"
    assert geometry(create(),create(shape=(2,3,5)))[0] == "SHAPE_MISMATCH"
    assert geometry(create(),create(offset=2.))[0] == "AFFINE_MISMATCH"
    assert geometry(create(scode=0),create())[0] == "NO_RELIABLE_SPATIAL_TRANSFORM"
    print("HCC_MRI_IMAGE_MASK_HEADER_ALIGNMENT_OFFLINE_TEST_PASS")


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--output",default="artifacts/hcc_mri")
    ap.add_argument("--offline-test",action="store_true")
    args=ap.parse_args()
    if args.offline_test:
        offline_test()
        return
    root=Path(args.output)
    with (root/"tcga_liverhccseg_mri_mask_voxel_qc.csv").open(
            newline="",encoding="utf-8") as handle:
        cases=list(csv.DictReader(handle))
    if not cases:
        raise ValueError("No mask QC cases")
    with ZipFile(HTTPRangeFile(ARCHIVE)) as archive:
        rows=run(cases,archive)
    report=summarize(rows,{x["patient_id"] for x in cases})
    with (root/"tcga_liverhccseg_mri_image_mask_header_qc.csv").open(
            "w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=FIELDNAMES,extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    (root/"tcga_liverhccseg_mri_image_mask_header_summary.json").write_text(
        json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False))
    if (report["source_phase_headers_examined"] == 0 or
            report["patients_with_at_least_one_header_geometry_match"] == 0):
        raise SystemExit("No MRI source-phase geometry links verified; clinical gate stays PENDING")


if __name__=="__main__":
    main()
