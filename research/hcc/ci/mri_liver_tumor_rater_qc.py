#!/usr/bin/env python3
"""LiverHccSeg HCC lesion inventory, liver containment and two-rater Dice QC.

Fetches only public MRI segmentation NIfTI ZIP members with 2 HTTP ranges each.
No raw masks uploaded; CSV/JSON summary only. For each patient, enumerates
all rater1 tumor labels, selects largest by *volume*, compares matching rater2
tumor number and rater1 liver inclusion. Anatomic/tumor truth is NOT established.
"""
import argparse
import csv
import gzip
import io
import json
import re
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZipFile

import numpy as np
from fast_zip_member_range import get_member_with_ranges
from mri_mask_voxel_audit import HTTPRangeFile
from mri_pv_pixel_overlay_audit import corner_offset_mm
from zenodo_nifti_zip_inventory import ARCHIVE, is_apple_sidecar

MASK_LIMIT = 192 * 1024 * 1024
TUMOR = re.compile(r"rater1_tumor(\d+)\.nii\.gz$", re.I)
FIELDS = (
    "patient_id", "rater1_tumor_count", "representative_lesion_rule",
    "representative_tumor_number", "representative_volume_ml",
    "rater1_tumor_voxels", "rater1_tumor2_voxels_if_any",
    "rater2_same_lesion_voxels", "rater1_vs_rater2_dice",
    "rater1_tumor_inside_rater1_liver_fraction",
    "rater1_liver_voxels", "rater1_rater2_max_corner_mm",
    "rater1_liver_max_corner_mm", "segmentation_qc_status",
    "lesion_number_mapping_verified", "expert_roi_review",
    "pretreatment_verified", "qualified_patient", "error"
)


def load_seg_image(archive, path):
    import nibabel as nib
    if path not in archive.NameToInfo or is_apple_sidecar(path):
        raise ValueError("SEG_FILE_MISSING")
    info = archive.getinfo(path)
    zipped_member = get_member_with_ranges(ARCHIVE, info, archive.fp.total)
    with gzip.GzipFile(fileobj=io.BytesIO(zipped_member)) as gzip_file:
        raw = gzip_file.read(MASK_LIMIT+1)
    if len(raw)>MASK_LIMIT:
        raise ValueError("SEG_NIFTI_LIMIT_EXCEEDED")
    img = nib.Nifti1Image.from_bytes(raw)
    if len(img.shape)!=3 or not np.isfinite(img.affine).all():
        raise ValueError("SEG_MASK_GEOMETRY_INVALID")
    a = np.asanyarray(img.dataobj)
    if not np.isfinite(a).all():
        raise ValueError("SEG_MASK_NONFINITE")
    return np.asarray(a>0, dtype=bool), np.asarray(img.affine,dtype=float)


def compatible(a, b, aff_a, aff_b):
    if a.shape != b.shape:
        raise ValueError("SEG_SHAPE_MISMATCH")
    diff=corner_offset_mm(aff_a,aff_b,a.shape)
    if diff>0.5:
        raise ValueError("SEG_AFFINE_MISMATCH")
    return diff


def dice(a,b):
    n=int(a.sum())+int(b.sum())
    if n==0:
        raise ValueError("EMPTY_BOTH_SEG")
    return 2.*float(np.count_nonzero(a&b))/n


def metrics(r1_tumors, r2_tumors, liver):
    """Pure functions over (boolean 3D ndarray, 4x4 affine) inputs."""
    if not r1_tumors or liver is None:
        raise ValueError("MISSING_RATER1_LIVER_OR_TUMORS")
    liver_array,liver_aff=liver
    records=[]
    for lesion_id,(tum,aff) in sorted(r1_tumors.items()):
        count=int(np.count_nonzero(tum))
        if not count: raise ValueError("EMPTY_RATER1_TUMOR")
        diff_liver=compatible(tum,liver_array,aff,liver_aff)
        inside=float(np.count_nonzero(tum&liver_array))/count
        r2=r2_tumors.get(lesion_id)
        if r2 is None:
            n2=0;d=None;diff_r2=None
        else:
            ar2,afr2=r2
            diff_r2=compatible(tum,ar2,aff,afr2)
            n2=int(ar2.sum())
            if not n2:raise ValueError("EMPTY_RATER2_TUMOR")
            d=dice(tum,ar2)
        voxel_ml=abs(float(np.linalg.det(aff[:3,:3])))*count/1000.
        records.append(dict(
            lesion_id=lesion_id,r1_voxels=count,r2_voxels=n2,
            volume_ml=voxel_ml,dice=d,inside=inside,
            liver_voxels=int(liver_array.sum()),
            diff_liver=diff_liver,diff_r2=diff_r2))
    selected=max(records,key=lambda r:(r["volume_ml"],-int(r["lesion_id"])))
    return selected,records


def evaluate(archive,pid,root_mask_path):
    result={
        "patient_id":pid,
        "representative_lesion_rule":"LARGEST_RATER1_TUMOR_VOLUME_PREDEFINED",
        "lesion_number_mapping_verified":"NO",
        "expert_roi_review":"NOT_ASSESSED",
        "pretreatment_verified":"NO",
        "qualified_patient":"NOT_ASSESSED",
        "segmentation_qc_status":"NOT_VERIFIED","error":"",
    }
    try:
        prefix=root_mask_path.rsplit("/",1)[0]+"/"
        r1files={}
        for name in archive.namelist():
            if not name.startswith(prefix) or is_apple_sidecar(name):
                continue
            m=TUMOR.search(name.split("/")[-1])
            if m:
                r1files[int(m.group(1))]=name
        if not r1files:
            raise ValueError("NO_RATER1_TUMORS")
        first=next(iter(r1files.values()))
        liver_name=prefix+"rater1_liver.nii.gz"
        r1={}
        r2={}
        for n,path in sorted(r1files.items()):
            r1[n]=load_seg_image(archive,path)
            counterpart=prefix+f"rater2_tumor{n}.nii.gz"
            if counterpart in archive.NameToInfo:
                r2[n]=load_seg_image(archive,counterpart)
        liver=load_seg_image(archive,liver_name)
        selected,lesions=metrics(r1,r2,liver)
        result.update({
            "rater1_tumor_count":len(r1),
            "representative_tumor_number":selected["lesion_id"],
            "representative_volume_ml":round(selected["volume_ml"],5),
            "rater1_tumor_voxels":selected["r1_voxels"],
            "rater1_tumor2_voxels_if_any":r1.get(2,(None,None))[0].sum() if 2 in r1 else "",
            "rater2_same_lesion_voxels":selected["r2_voxels"],
            "rater1_vs_rater2_dice":round(selected["dice"],5)
                  if selected["dice"] is not None else "",
            "rater1_tumor_inside_rater1_liver_fraction":round(selected["inside"],6),
            "rater1_liver_voxels":selected["liver_voxels"],
            "rater1_rater2_max_corner_mm":round(selected["diff_r2"],5)
                  if selected["diff_r2"] is not None else "",
            "rater1_liver_max_corner_mm":round(selected["diff_liver"],5),
            "segmentation_qc_status":(
                "PASS_GEOMETRY_WITH_REVIEW_FLAGS"
                if selected["dice"] is not None
                else "PARTIAL_NO_RATER2_FOR_SELECTED_LESION"
            ),
        })
    except Exception as exc:
        result["segmentation_qc_status"]="FAILED_OR_UNVERIFIED"
        result["error"]=type(exc).__name__+": "+str(exc)[:120]
    return result


def offline_test():
    aff=np.diag([1.,1.,2.,1.])
    liver=np.zeros((20,20,10),bool);liver[2:18,2:18,1:9]=True
    a=np.zeros_like(liver);a[5:9,5:9,3:5]=True
    b=np.zeros_like(liver);b[8:16,8:16,2:6]=True
    ar2a=a.copy()
    ar2b=b.copy();ar2b[8,8,2]=False
    s,records=metrics({1:(a,aff),2:(b,aff)},
                      {1:(ar2a,aff),2:(ar2b,aff)},
                      (liver,aff))
    assert len(records)==2 and s["lesion_id"]==2
    assert 0.9<s["dice"]<1 and s["inside"]==1.
    assert abs(dice(a,a)-1)<1e-9
    # Lesion mapping remains a human/clinical gate even when Dice is high.
    try:
        incompatible=aff.copy();incompatible[0,3]=10.
        metrics({1:(a,aff)},{1:(a,incompatible)},(liver,aff))
    except ValueError as e:
        assert "AFFINE" in str(e)
    else: raise AssertionError("Mismatch did not fail")
    print("HCC_MRI_LESION_LIVER_RATER_OFFLINE_TEST_PASS")


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--offline-test",action="store_true")
    ap.add_argument("--source-csv",default="artifacts/hcc_mri/tcga_liverhccseg_mri_mask_voxel_qc.csv")
    ap.add_argument("--out-dir",default="artifacts/hcc_mri_rater_qc")
    ap.add_argument("--max-cases",type=int,default=2)
    args=ap.parse_args()
    if args.offline_test: return offline_test()
    if not 1<=args.max_cases<=14:raise ValueError("bad --max-cases")
    with open(args.source_csv,encoding="utf-8",newline="") as f:
        source=list(csv.DictReader(f))
    cases=sorted((x for x in source
                  if x["nifti_mask_voxel_status"]=="PASS_NONEMPTY_NIFTI_MASK"),
                 key=lambda x:x["patient_id"])[:args.max_cases]
    if not cases:raise ValueError("No prior mask-QC-passed cases")
    with ZipFile(HTTPRangeFile(ARCHIVE)) as archive:
        rows=[evaluate(archive,x["patient_id"],x["nifti_member_path"])
              for x in cases]
    dest=Path(args.out_dir);dest.mkdir(parents=True,exist_ok=True)
    with (dest/"mri_liver_tumor_interrater_qc.csv").open("w",newline="",encoding="utf-8") as f:
        writer=csv.DictWriter(f,fieldnames=FIELDS,extrasaction="ignore")
        writer.writeheader();writer.writerows(rows)
    states=Counter(x["segmentation_qc_status"] for x in rows)
    good=[r for r in rows if r["segmentation_qc_status"].startswith("PASS_")]
    summary={
        "status":"PASS_RATER_MASK_QC" if len(good)==len(rows) else "PARTIAL_RATER_MASK_QC",
        "generated_utc":datetime.now(timezone.utc).isoformat(),
        "checked_patients":len(rows),
        "patients_with_valid_liver_and_raters":len(good),
        "rater1_multiple_tumor_patients":sum(int(r.get("rater1_tumor_count") or 0)>1 for r in rows),
        "selected_lesion_not_tumor1_patients":sum(str(r.get("representative_tumor_number"))!="1"
           and r["segmentation_qc_status"].startswith("PASS_") for r in rows),
        "segmentation_status_counts":dict(states),
        "expert_image_review_verified":0,
        "qualified_mri_rna_patients":"NOT_ASSESSED",
        "note":"Largest rater1 volume and same-number rater2 Dice are automated heuristics, not tumor matching or clinical review."
    }
    (dest/"mri_liver_tumor_interrater_qc_summary.json").write_text(
        json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(summary,ensure_ascii=False))
    if not good:raise SystemExit("No QC passed")
if __name__=="__main__":main()
