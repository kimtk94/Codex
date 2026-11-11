#!/usr/bin/env python3
"""HCC P0 official source-space orientation audit of all 14 selected tumor masks.

Reads only the first 352 *uncompressed header bytes* of official NIfTI members
in the ZIP (bounded remote requests); no MRI pixels, registration, clinical
dates, expression arrays or radiomic features. This is geometry hypothesis
triage, NOT an independent qualified anatomical segmentation review.
"""
import argparse
import csv
import json
import math
from collections import Counter
from pathlib import Path

from mri_phase_mask_source_gate import frozen, inventory_member, SOURCE_PHASE_RULE
from mri_image_mask_alignment_audit import header_only
from mri_mask_voxel_audit import HTTPRangeFile
from zenodo_nifti_zip_inventory import ARCHIVE
from zipfile import ZipFile

PHASES=("art","pv","art_pv")
FIELDS=("patient_id","selected_tumor","source_phase","source_member",
        "mask_member","source_axis_codes","mask_axis_codes",
        "source_shape_xyz","mask_shape_xyz","header_before_mm",
        "header_after_axis_reorientation_mm","axis_flip_count",
        "axis_permutation","header_alignment_class",
        "source_documented_phase","anatomical_registration_review",
        "pretreatment_verified","sequenced_tumor_same_lesion",
        "eligible_patient")

def geometric_displacement(a,b,shape):
    import numpy as np
    if a is None or b is None:
        return None
    from mri_pv_pixel_overlay_audit import corner_offset_mm
    x=float(corner_offset_mm(a,b,shape))
    if not math.isfinite(x):
        raise ValueError("Nonfinite affine")
    return round(x,5)

def audit_header_pair(source,mask,phase):
    import numpy as np
    from nibabel.orientations import io_orientation, ornt_transform, inv_ornt_aff, aff2axcodes
    a=source["affine"];b=mask["affine"]
    size=source["shape"];masksize=mask["shape"]
    if a is None or b is None:
        return {"source_axis_codes":"UNAVAILABLE","mask_axis_codes":"UNAVAILABLE",
                "source_shape_xyz":"x".join(map(str,size)),
                "mask_shape_xyz":"x".join(map(str,masksize)),
                "header_before_mm":None,"header_after_axis_reorientation_mm":None,
                "axis_flip_count":None,"axis_permutation":"",
                "header_alignment_class":"REVIEW_MISSING_TRANSFORM"}
    so=io_orientation(a);mo=io_orientation(b)
    if np.any(np.isnan(so)) or np.any(np.isnan(mo)):
        raise ValueError("Unknown orientations")
    x=ornt_transform(so,mo)
    transformed_shape=tuple(size[int(v)] for v in x[:,0])
    before=geometric_displacement(a,b,masksize) if size==masksize else None
    after=geometric_displacement(a @ inv_ornt_aff(x,size),b,masksize) if transformed_shape==masksize else None
    cls=("MATCH_BEFORE_AND_AFTER_HEADER_ONLY" if before is not None and before<=0.5
         else "MATCH_AFTER_AXIS_ONLY_HEADER_ONLY" if after is not None and after<=0.5
         else "REVIEW_NOT_MATCHED_AFTER_AXIS")
    return {"source_axis_codes":"".join(aff2axcodes(a)),
            "mask_axis_codes":"".join(aff2axcodes(b)),
            "source_shape_xyz":"x".join(map(str,size)),
            "mask_shape_xyz":"x".join(map(str,masksize)),
            "header_before_mm":before,"header_after_axis_reorientation_mm":after,
            "axis_flip_count":int(sum(v<0 for v in x[:,1])),
            "axis_permutation":";".join(str(int(v)) for v in x[:,0]),
            "header_alignment_class":cls}

def analyze():
    cases=frozen()
    result=[]
    with ZipFile(HTTPRangeFile(ARCHIVE)) as archive:
        index=archive.NameToInfo
        for pid in sorted(cases):
            tumor=cases[pid]
            maskname=inventory_member(index,pid,f"rater1_tumor{tumor}.nii.gz")
            mask=header_only(archive,index[maskname])
            for phase in PHASES:
                srcname=inventory_member(index,pid,phase+".nii.gz")
                src=header_only(archive,index[srcname])
                m=audit_header_pair(src,mask,phase)
                result.append({
                    "patient_id":pid,"selected_tumor":tumor,
                    "source_phase":phase,"source_member":srcname,
                    "mask_member":maskname,**m,
                    "source_documented_phase":SOURCE_PHASE_RULE[phase],
                    "anatomical_registration_review":"NOT_ASSESSED",
                    "pretreatment_verified":"NOT_ASSESSED",
                    "sequenced_tumor_same_lesion":"NOT_ASSESSED",
                    "eligible_patient":"NOT_ASSESSED"})
    validate(result)
    return result

def validate(rows):
    patients=frozen()
    if len(rows)!=42 or len({r["patient_id"] for r in rows})!=14:
        raise ValueError("Must keep all 14 distinct MRI candidates x three source phases")
    if {(r["patient_id"],r["source_phase"]) for r in rows} != {(pid,phase) for pid in patients for phase in PHASES}:
        raise ValueError("One unique source phase per case required")
    if any(r["eligible_patient"]!="NOT_ASSESSED" or
           r["anatomical_registration_review"]!="NOT_ASSESSED" or
           r["pretreatment_verified"]!="NOT_ASSESSED" or
           r["sequenced_tumor_same_lesion"]!="NOT_ASSESSED" for r in rows):
        raise ValueError("Header is not biological eligibility")
    if any(int(r["selected_tumor"])!=patients[r["patient_id"]] for r in rows):
        raise ValueError("Index tumor drift")
    for pid,baseline in (("TCGA-BC-A10Y",284.25781),("TCGA-DD-A4NH",498.90627)):
        row=next(r for r in rows if r["patient_id"]==pid and r["source_phase"]=="art_pv")
        if row["header_before_mm"] is None or abs(row["header_before_mm"]-baseline)>0.01:
            raise ValueError("Pinned original true qform mismatch no longer reproducible")

def summarize(rows):
    return {"status":"HEADER_ONLY_GEOMETRY_COMPLETE_ANATOMY_CLINICAL_HOLD",
            "official_source":"https://zenodo.org/records/8179129",
            "official_version":"v1.1",
            "source_data_type":"NIFTI_HEADER_ONLY_352_BYTES_NOT_IMAGE_PIXELS",
            "unique_patients":len({r["patient_id"] for r in rows}),
            "patient_phase_rows":len(rows),
            "orientation_results":{phase:dict(Counter(r["header_alignment_class"] for r in rows if r["source_phase"]==phase))
                                   for phase in PHASES},
            "axis_flip_results":{phase:dict(Counter(str(r["axis_flip_count"]) for r in rows if r["source_phase"]==phase))
                                 for phase in PHASES},
            "source_phase_affine_alignment_not_anatomical_proof":True,
            "qualified_roi_expert_reviews":0,
            "treatment_temporal_verified":0,
            "same_RNA_lesion_verified":0,
            "final_eligible_n":"NOT_ASSESSED",
            "MRI_RNA_primary_12_tests":"NOT_EXECUTED",
            "HCC12":"PARTIAL","HCC13":"PARTIAL","HCC14":"PARTIAL",
            "HCC17":"PENDING","HCC20":"PENDING",
            "claim_ceiling":"S0"}

def offline_test():
    import numpy as np
    a=np.eye(4);b=np.eye(4)
    src={"shape":(8,9,10),"affine":a}
    mask={"shape":(8,9,10),"affine":b}
    z=audit_header_pair(src,mask,"art")
    assert z["header_alignment_class"]=="MATCH_BEFORE_AND_AFTER_HEADER_ONLY"
    a=np.eye(4);a[1,1]=-1;a[1,3]=8
    z=audit_header_pair({"shape":(8,9,10),"affine":a},mask,"art_pv")
    assert z["header_before_mm"]>5
    assert z["header_after_axis_reorientation_mm"]<=0.5
    assert z["axis_flip_count"]==1
    assert z["header_alignment_class"]=="MATCH_AFTER_AXIS_ONLY_HEADER_ONLY"
    a=np.eye(4);a[2,3]=10
    z=audit_header_pair({"shape":(8,9,10),"affine":a},mask,"art_pv")
    assert z["header_alignment_class"]=="REVIEW_NOT_MATCHED_AFTER_AXIS"
    assert frozen()["TCGA-BC-A10Y"]==3
    print("HCC_MRI14_AXIS_REORIENTATION_HEADER_ONLY_NEGATIVE_CASES_PASS")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--offline-test",action="store_true")
    p.add_argument("--out-dir",default="artifacts/hcc_mri14_axis_orientation")
    a=p.parse_args()
    if a.offline_test:
        offline_test();return
    rows=analyze()
    report=summarize(rows)
    out=Path(a.out_dir);out.mkdir(parents=True,exist_ok=True)
    with (out/"hcc_mri14_art_pv_orientation_geometry.csv").open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS)
        w.writeheader();w.writerows(rows)
    (out/"hcc_mri14_source_orientation_summary.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report))

if __name__=="__main__":
    main()
