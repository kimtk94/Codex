#!/usr/bin/env python3
"""Audit original registered ART_PV NIfTI voxel header spacings for 14 HCC cases.

Read official LiverHccSeg v1.1 source bytes with ZIP CRC, SHA256 and fixed
tumor1/tumor3 mask orientation. Never substitute historical raw-PV pixel
spacing as a registered-PV measurement. Source geometry only, no biology.
"""
import argparse,csv,hashlib,json,math,tempfile
from pathlib import Path
from zipfile import ZipFile

from fast_zip_member_range import get_member_with_ranges
from mri_mask_voxel_audit import HTTPRangeFile
from mri_phase_mask_source_gate import frozen,inventory_member
from mri_p0_raw_vs_registered_pv_radiomics_pilot import orient_to_mask
from mri_pv_pixel_overlay_audit import corner_offset_mm
from zenodo_nifti_zip_inventory import ARCHIVE

FIELDS=("patient_id","selected_tumor","official_image_phase","source_member",
        "registered_art_pv_sha256","reader1_mask_sha256","original_nifti_shape",
        "registered_reference_nifti_shape","registered_voxel_spacing_x_mm",
        "registered_voxel_spacing_y_mm","registered_voxel_spacing_z_mm",
        "registered_inplane_mean_mm","registered_z_inplane_anisotropy_ratio",
        "registered_z_minus_target_3mm_abs_mm","registered_inplane_minus_target_3mm_abs_mm",
        "axis_permutation","axis_signs","max_corner_affine_offset_mm",
        "qualified_anatomical_review","pretreatment_MRI","same_index_RNA_tissue",
        "clinical_eligible_n","claim_ceiling")

def measured_spacing(registered):
    import numpy as np
    axes=np.asarray(registered.affine[:3,:3],dtype=float)
    vox=np.linalg.norm(axes,axis=0)
    if (not np.isfinite(vox).all() or np.min(vox)<=0 or np.max(vox)>15):
        raise ValueError("INVALID_OFFICIAL_REGISTERED_NIFTI_SPACING")
    return [float(x) for x in vox]

def case(archive,pid,tumor):
    import nibabel as nib
    im_name=inventory_member(archive.NameToInfo,pid,"art_pv.nii.gz")
    mask_name=inventory_member(archive.NameToInfo,pid,f"rater1_tumor{tumor}.nii.gz")
    blobs={};meta={}
    for key,name in (("im",im_name),("mask",mask_name)):
        info=archive.getinfo(name)
        if not (100<info.file_size<96*1024*1024) or info.compress_size>96*1024*1024:
            raise ValueError("UNEXPECTED_OFFICIAL_SOURCE_SIZE")
        blob=get_member_with_ranges(ARCHIVE,info,archive.fp.total)
        blobs[key]=blob
        meta[key]=hashlib.sha256(blob).hexdigest()
    with tempfile.TemporaryDirectory(prefix="hcc-reg-pv-header-") as tmp:
        paths={}
        for k,v in blobs.items():
            p=Path(tmp)/(k+".nii.gz")
            p.write_bytes(v)
            paths[k]=nib.load(str(p))
        mask=paths["mask"]
        im=paths["im"]
        reg,order,sign=orient_to_mask(im,mask)
        off=corner_offset_mm(reg.affine,mask.affine,mask.shape)
        if off>0.5 or order!=[0,1,2] or sign not in ([-1,-1,1],[1,-1,1]):
            raise ValueError("REGISTERED_PV_SOURCE_MASK_ALIGNMENT_OR_ORIENTATION_FAILED")
        sx,sy,sz=measured_spacing(reg)
        inplane=(sx+sy)/2
        if inplane<=0:raise ValueError("INVALID_MEASURED_REGISTERED_SPACING")
        row={
            "patient_id":pid,"selected_tumor":tumor,
            "official_image_phase":"reoriented_art_pv",
            "source_member":im_name,"registered_art_pv_sha256":meta["im"],
            "reader1_mask_sha256":meta["mask"],
            "original_nifti_shape":"x".join(map(str,im.shape)),
            "registered_reference_nifti_shape":"x".join(map(str,reg.shape)),
            "registered_voxel_spacing_x_mm":round(sx,6),
            "registered_voxel_spacing_y_mm":round(sy,6),
            "registered_voxel_spacing_z_mm":round(sz,6),
            "registered_inplane_mean_mm":round(inplane,6),
            "registered_z_inplane_anisotropy_ratio":round(sz/inplane,6),
            "registered_z_minus_target_3mm_abs_mm":round(abs(sz-3),6),
            "registered_inplane_minus_target_3mm_abs_mm":round(abs(inplane-3),6),
            "axis_permutation":";".join(map(str,order)),
            "axis_signs":";".join(map(str,sign)),
            "max_corner_affine_offset_mm":round(float(off),6),
            "qualified_anatomical_review":"NOT_ASSESSED",
            "pretreatment_MRI":"NOT_ASSESSED",
            "same_index_RNA_tissue":"NOT_ASSESSED",
            "clinical_eligible_n":"NOT_ASSESSED","claim_ceiling":"S0"}
        print("HCC_REGISTERED_PV_EXACT_HEADER_SOURCE_SPACING",pid,sx,sy,sz,flush=True)
        return row

def verify(rows,shard):
    ids=sorted(frozen())[shard*2:shard*2+2]
    if len(ids)!=2 or len(rows)!=2 or {r["patient_id"] for r in rows}!=set(ids):
        raise ValueError("EXACT_TWO_FROZEN_SOURCE_PATIENTS_REQUIRED")
    for r in rows:
        if (int(r["selected_tumor"])!=frozen()[r["patient_id"]] or
            r["official_image_phase"]!="reoriented_art_pv" or
            r["qualified_anatomical_review"]!="NOT_ASSESSED" or
            r["pretreatment_MRI"]!="NOT_ASSESSED" or
            r["same_index_RNA_tissue"]!="NOT_ASSESSED" or
            r["clinical_eligible_n"]!="NOT_ASSESSED" or r["claim_ceiling"]!="S0"):
            raise ValueError("UNAUTHORIZED_CLINICAL_COHORT_PROMOTION")
        if float(r["max_corner_affine_offset_mm"])>0.5:
            raise ValueError("SOURCE_AFFINE_GEOMETRY_DRIFT")
        if len(r["registered_art_pv_sha256"])!=64 or len(r["reader1_mask_sha256"])!=64:
            raise ValueError("SOURCE_SHA256_MISSING")
    return ids

def offline():
    import numpy as np,nibabel as nib
    cases=frozen()
    assert len(cases)==14 and cases["TCGA-BC-A10Y"]==3
    shape=(10,11,6)
    aff=np.diag([1.2,1.5,4.7,1.])
    im=nib.Nifti1Image(np.zeros(shape,dtype=np.float32),aff)
    got=measured_spacing(im)
    assert all(abs(a-b)<1e-7 for a,b in zip(got,[1.2,1.5,4.7]))
    assert round(got[2]/((got[0]+got[1])/2),3)==3.481
    print("HCC_REGISTERED_PV_HEADER_EXACT_SPACING_SYNTHETIC_PASS")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--offline-test",action="store_true")
    ap.add_argument("--shard",type=int)
    ap.add_argument("--out-dir",default="artifacts/hcc_registered_header")
    a=ap.parse_args()
    if a.offline_test:return offline()
    if a.shard is None or not 0<=a.shard<7:
        raise ValueError("SEVEN_2_PATIENT_SHARDS_REQUIRED")
    cohort=frozen();ids=sorted(cohort)[a.shard*2:a.shard*2+2]
    with ZipFile(HTTPRangeFile(ARCHIVE)) as archive:
        rows=[case(archive,pid,cohort[pid]) for pid in ids]
    verify(rows,a.shard)
    out=Path(a.out_dir);out.mkdir(parents=True,exist_ok=True)
    with (out/f"hcc_registered_header_shard_{a.shard}.csv").open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();w.writerows(rows)
    (out/f"hcc_registered_header_shard_{a.shard}.json").write_text(json.dumps({
        "shard":a.shard,"patients":ids,"source":"zenodo:8179129 v1.1 art_pv",
        "source_phase":"reoriented_art_pv","n_cases":2,"claim_ceiling":"S0",
        "clinical_eligibility":"NOT_ASSESSED"},indent=2)+"\n")
    print("HCC_EXACT_REG_PV_SPACING_2_PATIENT_SOURCE_PASS",a.shard,flush=True)
if __name__=="__main__":main()
