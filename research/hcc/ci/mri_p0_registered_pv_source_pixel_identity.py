#!/usr/bin/env python3
"""No-outcome source-voxel identity audit for apparently identical AAV7 radiomics.

Check registered ART_PV after exact voxel orientation versus original PV for
frozen G3-AAV7 and A10Y control, in selected tumor, liver and full finite FOV.
Image source ZIP CRC and frozen source-member SHA where available. This is not
a substitute for expert anatomy/clinical tumor-RNA matching.
"""
import argparse,json,hashlib,math,tempfile
from pathlib import Path
from zipfile import ZipFile
import numpy as np
from mri_mask_voxel_audit import HTTPRangeFile
from mri_phase_mask_source_gate import inventory_member,frozen
from mri_p0_raw_vs_registered_pv_radiomics_pilot import orient_to_mask
from fast_zip_member_range import get_member_with_ranges
from zenodo_nifti_zip_inventory import ARCHIVE

IDS=("TCGA-BC-A10Y","TCGA-G3-AAV7")
ARTIFACT_SHA_BASELINE=Path("research/hcc/HCC_MRI_P0_2CASE_ACTUAL_SOURCE_SPACE_20261031.json")

def compare_arrays(a,b,region):
    if a.shape!=b.shape or a.shape!=region.shape:
        raise ValueError("SOURCE_SOURCE_MASK_SHAPE_DIFFERENT")
    mask=(region>0)&np.isfinite(a)&np.isfinite(b)
    count=int(mask.sum())
    if count<50:raise ValueError("TOO_FEW_FINITE_COMPARABLE_VOXELS")
    # Registration can legitimately change intensities, so this is purely a
    # numerical identity diagnostic; exact equality does not prove anatomy.
    delta=np.asarray(a[mask],dtype=np.float64)-np.asarray(b[mask],dtype=np.float64)
    return {"voxel_count":count,
        "exact_equal_fraction":round(float(np.mean(delta==0)),8),
        "within_1e_minus_5_fraction":round(float(np.mean(np.abs(delta)<=1e-5)),8),
        "mean_abs_signal_difference":round(float(np.abs(delta).mean()),7),
        "root_mean_square_signal_difference":round(float(np.sqrt(np.mean(delta**2))),7),
        "max_abs_signal_difference":round(float(np.max(np.abs(delta))),7),
        "same_all_region_voxels_exact":bool(np.all(delta==0))}

def offline():
    a=np.arange(400,dtype=float).reshape(10,10,4)
    region=np.ones_like(a)
    same=compare_arrays(a,a.copy(),region)
    assert same["same_all_region_voxels_exact"]
    b=a.copy();b[0,0,0]+=1
    res=compare_arrays(a,b,region)
    assert not res["same_all_region_voxels_exact"]
    assert res["voxel_count"]==400 and res["exact_equal_fraction"]<1
    assert frozen()["TCGA-BC-A10Y"]==3 and frozen()["TCGA-G3-AAV7"]==1
    print("HCC_MRI_P0_SOURCE_IMAGE_EXACT_PIXEL_IDENTITY_NEGATIVE_QC_PASS")

def execute_case(archive,pid,index,sha_checks):
    import nibabel as nib
    from mri_pv_pixel_overlay_audit import corner_offset_mm
    names=("pv","art_pv","rater1_liver",
           f"rater1_tumor{index}",f"rater2_tumor{index}")
    with tempfile.TemporaryDirectory(prefix="hcc_voxel_identity_") as td:
        imgs={};hashes={}
        for name in names:
            member=inventory_member(archive.NameToInfo,pid,name+".nii.gz")
            data=get_member_with_ranges(ARCHIVE,archive.getinfo(member),archive.fp.total)
            digest=hashlib.sha256(data).hexdigest()
            if name in sha_checks and digest!=sha_checks[name]:
                raise ValueError("FROZEN_IMAGE_OR_MASK_SOURCE_SHA_MISMATCH")
            dest=Path(td)/(name+".nii.gz");dest.write_bytes(data)
            imgs[name]=nib.load(str(dest));hashes[name]=digest
        roi=imgs[f"rater1_tumor{index}"]
        registered,axes,flips=orient_to_mask(imgs["art_pv"],roi)
        raw=imgs["pv"]
        if corner_offset_mm(raw.affine,roi.affine,roi.shape)>0.5:
            raise ValueError("UNREGISTERED_SOURCE_GEOMETRY_CHANGED")
        a=np.asarray(raw.dataobj,dtype=np.float32)
        b=np.asarray(registered.dataobj,dtype=np.float32)
        if a.shape!=b.shape or a.shape!=roi.shape:
            raise ValueError("IMAGE_SOURCE_SHAPE_CHANGED")
        regions={}
        for label,mask in (
            ("index_tumor_rater1",np.asarray(roi.dataobj)),
            ("index_tumor_rater2",np.asarray(imgs[f"rater2_tumor{index}"].dataobj)),
            ("liver_rater1",np.asarray(imgs["rater1_liver"].dataobj)),
            ("finite_field_of_view",np.ones(a.shape,dtype=np.uint8))):
            regions[label]=compare_arrays(a,b,mask)
        return {"patient_id":pid,"fixed_index_tumor":index,
             "source_sha256_raw_pv":hashes["pv"],
             "source_sha256_registered_art_pv":hashes["art_pv"],
             "selected_mask_sha256":hashes[f"rater1_tumor{index}"],
             "source_orientation_axis_order":axes,
             "source_orientation_axis_signs":flips,
             "registered_source_header_offset_mm":round(float(
                  corner_offset_mm(registered.affine,roi.affine,roi.shape)),6),
             "regions":regions,
             "source_pixel_identity_is_not_anatomical_registration":True,
             "expert_qualified_roi_review":"NOT_ASSESSED",
             "MRI_before_treatment":"NOT_ASSESSED",
             "RNA_from_same_index_tumor":"NOT_ASSESSED",
             "clinical_eligible":"NOT_ASSESSED"}

def run():
    frozen_cases=frozen()
    baseline=json.loads(ARTIFACT_SHA_BASELINE.read_text(encoding="utf-8"))
    cases={x["patient_id"]:x for x in baseline["pilots"]}
    checks={}
    for pid in IDS:
        if pid in cases:
            case=cases[pid];checks[pid]={r["phase"]:r["sha256"] for r in case["measurements"]}
            checks[pid][f"rater1_tumor{frozen_cases[pid]}"]=case["mask_sha256"]
        else:checks[pid]={}
    with ZipFile(HTTPRangeFile(ARCHIVE)) as archive:
        rows=[execute_case(archive,pid,frozen_cases[pid],checks[pid]) for pid in IDS]
    if len(rows)!=2 or any(x["clinical_eligible"]!="NOT_ASSESSED" for x in rows):
        raise ValueError("SOURCE_ONLY_STUDY_MUST_NOT_PROMOTE_CLINICAL_ELIGIBILITY")
    return {"status":"SOURCE_IMAGE_VOXEL_IDENTITY_DIAGNOSTIC_ONLY",
            "n_cases":2,"source":"https://zenodo.org/records/8179129",
            "cases":rows,"association_results":0,"eligible_n":"NOT_ASSESSED",
            "claim_ceiling":"S0","HCC12":"PARTIAL","HCC20":"PENDING"}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--offline-test",action="store_true")
    p.add_argument("--out-dir",default="artifacts/hcc_p0_pixel_identity")
    args=p.parse_args()
    if args.offline_test:offline();return
    r=run();out=Path(args.out_dir);out.mkdir(parents=True,exist_ok=True)
    (out/"hcc_aav7_vs_a10y_source_pixel_identity.json").write_text(
        json.dumps(r,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"status":r["status"],"cases":[{
        "patient_id":x["patient_id"],
        "tumor_r1":x["regions"]["index_tumor_rater1"],
        "tumor_r2":x["regions"]["index_tumor_rater2"],
        "liver":x["regions"]["liver_rater1"]}for x in r["cases"]],
        "claim_ceiling":"S0"},ensure_ascii=False))

if __name__=="__main__":main()
