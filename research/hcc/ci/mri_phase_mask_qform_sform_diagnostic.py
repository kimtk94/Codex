#!/usr/bin/env python3
"""Diagnose qform/sform/world-space ambiguity of official LiverHccSeg ART_PV.

This is an evidence-only follow-up to HCC P0 source-space run #41187537805.
Do not edit NIfTI transforms or claim anatomical/clinical registration from
header agreement alone. Download only two case/phase members, transiently.
"""
import argparse, json, math, tempfile
from pathlib import Path
from zipfile import ZipFile

from mri_phase_mask_source_gate import frozen, PILOT_IDS, inventory_member, sha
from mri_mask_voxel_audit import HTTPRangeFile
from fast_zip_member_range import get_member_with_ranges
from zenodo_nifti_zip_inventory import ARCHIVE

FROZEN_REPORT=Path("research/hcc/HCC_MRI_P0_2CASE_ACTUAL_SOURCE_SPACE_20261031.json")
PHASES=("art","pv","art_pv")
ACTUAL_SOURCE="https://zenodo.org/records/8179129"

def max_displacement(a,b,shape):
    import numpy as np
    if a is None or b is None or shape is None:
        return None
    from mri_pv_pixel_overlay_audit import corner_offset_mm
    x=float(corner_offset_mm(a,b,shape))
    if not math.isfinite(x):
        raise ValueError("Nonfinite affine displacement")
    return round(x,5)

def shape3(x):
    return len(x.shape)==3 and all(v>1 for v in x.shape)

def transforms(img):
    import numpy as np
    q,qcode=img.get_qform(coded=True)
    s,scode=img.get_sform(coded=True)
    def entry(a,c):
        if a is None or int(c)==0:
            return {"code":int(c),"defined":False}
        v=np.asarray(a,dtype=float)
        if v.shape!=(4,4) or not np.isfinite(v).all():
            raise ValueError("Broken spatial transform")
        from nibabel.orientations import aff2axcodes
        return {"code":int(c),"defined":True,
                "origin_xyz_mm":[round(float(z),5) for z in v[:3,3]],
                "axis_codes":"".join(aff2axcodes(v)),
                "basis_lengths_mm":[round(float(z),5) for z in np.linalg.norm(v[:3,:3],axis=0)]}
    return q,s,entry(q,qcode),entry(s,scode)

def orientation_alignment(img, mask):
    """Only test signed voxel-axis permutations; never interpolate/alter source files.

    nibabel.orientation inv_ornt_aff maps output indices back into the exact
    unchanged source array. Alignment of header geometry is NOT proof of
    anatomical registration or correct biological tumor content.
    """
    import numpy as np
    from nibabel.orientations import io_orientation, ornt_transform, inv_ornt_aff, aff2axcodes
    source_axes=io_orientation(img.affine)
    target_axes=io_orientation(mask.affine)
    if np.any(np.isnan(source_axes)) or np.any(np.isnan(target_axes)):
        raise ValueError("Unable to determine source orientation")
    xform=ornt_transform(source_axes,target_axes)
    after_affine=img.affine @ inv_ornt_aff(xform,img.shape)
    out_shape=[int(img.shape[int(axis)]) for axis in xform[:,0]]
    offset=max_displacement(after_affine,mask.affine,mask.shape) if out_shape==list(mask.shape) else None
    correction=[{"target_axis":int(k),"source_axis":int(a),"sign":int(f)}
                for k,(a,f) in enumerate(xform)]
    return {"source_axis_codes":"".join(aff2axcodes(img.affine)),
            "mask_axis_codes":"".join(aff2axcodes(mask.affine)),
            "reoriented_shape_xyz":out_shape,
            "axis_transform":correction,
            "axis_flip_count":sum(a["sign"]<0 for a in correction),
            "axis_permutation_only":sorted(a["source_axis"] for a in correction)==[0,1,2],
            "max_corner_offset_after_axis_reorientation_mm":offset,
            "affine_agrees_after_axis_reorientation_only":offset is not None and offset<=0.5,
            "source_voxels_actually_reoriented":False,
            "source_voxels_and_anatomy_expert_verified":False}

def inspect_pair(img,mask,phase):
    import numpy as np
    if not shape3(img) or not shape3(mask):
        raise ValueError("Not 3D MRI")
    aq,as_,qmeta,smeta=transforms(img)
    mq,ms,mqmeta,msmeta=transforms(mask)
    offset=max_displacement(img.affine,mask.affine,mask.shape) if img.shape==mask.shape else None
    result={
        "phase":phase,
        "source_shape_xyz":list(img.shape),
        "mask_shape_xyz":list(mask.shape),
        "source_qform":qmeta,"source_sform":smeta,
        "mask_qform":mqmeta,"mask_sform":msmeta,
        "source_best_vs_mask_best_mm":offset,
        "source_qform_vs_mask_best_mm":max_displacement(aq,mask.affine,mask.shape) if img.shape==mask.shape else None,
        "source_sform_vs_mask_best_mm":max_displacement(as_,mask.affine,mask.shape) if img.shape==mask.shape else None,
        "source_qform_vs_mask_qform_mm":max_displacement(aq,mq,mask.shape) if img.shape==mask.shape else None,
        "source_sform_vs_mask_sform_mm":max_displacement(as_,ms,mask.shape) if img.shape==mask.shape else None,
        "image_voxel_array_coordinates_match_anatomy":"NOT_ASSESSED",
        "independent_qualified_anatomical_review":"NOT_ASSESSED",
        "clinical_eligibility":"NOT_ASSESSED",
    }
    alignment=orientation_alignment(img,mask)
    result.update(alignment)
    if offset is not None and offset>0.5 and alignment["affine_agrees_after_axis_reorientation_only"]:
        result["header_diagnostic"]="AFFINE_MATCH_AFTER_AXIS_REORIENTATION_ONLY"
    elif offset is not None and offset<=0.5:
        result["header_diagnostic"]="BEST_AFFINE_MATCH_ONLY"
    elif any(v is not None and v<=0.5 for k,v in result.items()
             if k in ("source_qform_vs_mask_best_mm","source_sform_vs_mask_best_mm")):
        result["header_diagnostic"]="REVIEW_CONFLICTING_QFORM_SFORM_POSSIBLE"
    else:
        result["header_diagnostic"]="REVIEW_SOURCE_SPATIAL_TRANSFORM"
    return result

def run():
    import nibabel as nib
    frozen_cases=frozen()
    baseline=json.loads(FROZEN_REPORT.read_text(encoding="utf-8"))
    if baseline["snapshot"]!="HCC_MRI_P0_SOURCE_SPACE_TWO_CASE_ACTUAL_v1":
        raise ValueError("Missing original source-space pilot baseline")
    source={x["patient_id"]:x for x in baseline["pilots"]}
    if set(source)!=set(PILOT_IDS):
        raise ValueError("Unexpected fixed pilot case ID")
    records=[]
    with ZipFile(HTTPRangeFile(ARCHIVE)) as zipfile:
        for pid in PILOT_IDS:
            selected=frozen_cases[pid]
            if selected!=source[pid]["index_tumor"]:
                raise ValueError("Index-lesion selection drift")
            expected={x["phase"]:x for x in source[pid]["measurements"]}
            members={"mask":inventory_member(zipfile.NameToInfo,pid,f"rater1_tumor{selected}.nii.gz")}
            for phase in PHASES:
                members[phase]=inventory_member(zipfile.NameToInfo,pid,phase+".nii.gz")
            with tempfile.TemporaryDirectory(prefix="hcc_p0_qform_") as td:
                imgs={}
                for phase,member in members.items():
                    info=zipfile.getinfo(member)
                    compressed=get_member_with_ranges(ARCHIVE,info,zipfile.fp.total)
                    digest=sha(compressed)
                    valid=source[pid]["mask_sha256"] if phase=="mask" else expected[phase]["sha256"]
                    if digest!=valid:
                        raise ValueError("Official NIfTI source archive member SHA drift: "+pid+" "+phase)
                    output=Path(td)/(phase+".nii.gz")
                    output.write_bytes(compressed)
                    imgs[phase]=nib.load(str(output))
                for phase in PHASES:
                    row=inspect_pair(imgs[phase],imgs["mask"],phase)
                    if phase in ("art","pv") and abs(row["source_best_vs_mask_best_mm"]-expected[phase]["max_corner_offset_mm"])>1e-4:
                        raise ValueError("Prior actual source-space geometry changed")
                    if phase=="art_pv" and (abs(row["source_best_vs_mask_best_mm"]-expected[phase]["max_corner_offset_mm"])>1e-3):
                        raise ValueError("Previously verified registered PV mismatch changed")
                    records.append({"patient_id":pid,"selected_index_tumor":selected,
                                    "source_member_sha256":expected[phase]["sha256"],
                                    **row})
    result={"status":"REVIEW_NIFTI_QFORM_SFORM_AND_ANATOMICAL_REGISTRATION",
            "source":ACTUAL_SOURCE,"source_version":"1.1",
            "input_run":"https://github.com/kimtk94/Codex/actions/runs/41187537805",
            "source_validation":"PER_MEMBER_SHA256_FROZEN_AND_VERIFIED",
            "n_cases":2,"n_phase_rows":len(records),"results":records,
            "header_ambiguity_explained_biologically":False,
            "raw_PV_radiomics_clinically_approved":False,
            "qualified_eligible_n":"NOT_ASSESSED",
            "HCC12":"PARTIAL","HCC13":"PARTIAL","HCC14":"PARTIAL",
            "HCC20":"PENDING","claim_ceiling":"S0"}
    if len(records)!=6:raise ValueError("Missing phase headers")
    return result

def offline():
    import numpy as np
    import nibabel as nib
    mask=nib.Nifti1Image(np.ones((8,9,10),dtype=np.uint8),np.eye(4))
    mask.set_qform(np.eye(4),code=1); mask.set_sform(np.eye(4),code=1)
    img=nib.Nifti1Image(np.ones((8,9,10),dtype=np.float32),np.eye(4))
    img.set_qform(np.eye(4),code=1)
    shifted=np.eye(4);shifted[0,3]=300
    img.set_sform(shifted,code=1)
    a=inspect_pair(img,mask,"art_pv")
    assert a["source_best_vs_mask_best_mm"]>200
    assert a["source_qform_vs_mask_best_mm"]<=0.5
    assert a["header_diagnostic"]=="AFFINE_MATCH_AFTER_AXIS_REORIENTATION_ONLY"
    assert a["affine_agrees_after_axis_reorientation_only"]
    assert a["axis_flip_count"]==0  # qform already aligned; sform picked by nibabel
    flipped=np.eye(4)
    flipped[0,0]=-1
    flipped[0,3]=7
    flipped_image=nib.Nifti1Image(np.ones((8,9,10),dtype=np.float32),flipped)
    flipped_test=inspect_pair(flipped_image,mask,"art_pv")
    assert flipped_test["source_best_vs_mask_best_mm"]>5
    assert flipped_test["max_corner_offset_after_axis_reorientation_mm"]<=0.5
    assert flipped_test["axis_flip_count"]==1
    assert flipped_test["header_diagnostic"]=="AFFINE_MATCH_AFTER_AXIS_REORIENTATION_ONLY"
    translated=np.eye(4);translated[0,3]=5
    translated_img=nib.Nifti1Image(np.ones((8,9,10),dtype=np.float32),translated)
    bad=inspect_pair(translated_img,mask,"art_pv")
    assert bad["header_diagnostic"]=="REVIEW_SOURCE_SPATIAL_TRANSFORM"
    assert not bad["affine_agrees_after_axis_reorientation_only"]
    assert a["clinical_eligibility"]=="NOT_ASSESSED"
    b=inspect_pair(mask,mask,"art")
    assert b["header_diagnostic"]=="BEST_AFFINE_MATCH_ONLY"
    print("HCC_P0_NIFTI_QFORM_SFORM_INDEPENDENT_DIAGNOSTIC_OFFLINE_PASS")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--mode",choices=["offline","live"],required=True)
    p.add_argument("--out-dir",default="artifacts/hcc_mri_qform_sform")
    a=p.parse_args()
    if a.mode=="offline":
        offline();return
    x=run()
    dest=Path(a.out_dir);dest.mkdir(parents=True,exist_ok=True)
    (dest/"hcc_p0_source_qform_sform_diagnostics.json").write_text(
        json.dumps(x,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"status":x["status"],
                     "diagnostics":[{"patient_id":y["patient_id"],"phase":y["phase"],
                     "best_vs_mask_mm":y["source_best_vs_mask_best_mm"],
                     "qform_vs_mask_mm":y["source_qform_vs_mask_best_mm"],
                     "sform_vs_mask_mm":y["source_sform_vs_mask_best_mm"],
                     "classification":y["header_diagnostic"],
                     "axis_flip_count":y["axis_flip_count"],
                     "axes":y["source_axis_codes"]+"->"+y["mask_axis_codes"],
                     "offset_after_voxel_axis_reorientation_mm":y["max_corner_offset_after_axis_reorientation_mm"],
                     "anatomical_registration_review":"NOT_ASSESSED"} for y in x["results"]],
                     "HCC12":"PARTIAL","HCC20":"PENDING","claim_ceiling":"S0"},ensure_ascii=False))

if __name__=="__main__":
    main()
