#!/usr/bin/env python3
"""One real OpenSwissHCC v2 HCC venous MRI/mask source feasibility pilot.

Read only two bounded NIfTI archive members (one public original HCC venous
image + one expert HCC venous lesion L1 mask) by ZIP HTTP range, not download
the 5 GB subject archive. Keep patient ID, original source hashes, strict
physical image-mask geometry, and original 2×3 PyRadiomics settings.
No patient selection based on feature results. One case cannot be external
replication, diagnosis, ROI expert approval or radiogenomics evidence.
"""
import argparse,csv,hashlib,json,math,tempfile
from pathlib import Path
from zipfile import ZipFile
from mri_mask_voxel_audit import HTTPRangeFile
from fast_zip_member_range import get_member_with_ranges
from mri_pv_pixel_overlay_audit import corner_offset_mm
from mri_pv_glcm_binwidth_spacing_factorial import make_extractor,FEATURE_KEYS

REC="https://zenodo.org/records/21992461"
IMG_ZIP=REC+"/files/sub-001-sub-044.zip?download=1"
MASK_ZIP=REC+"/files/derivatives.zip?download=1"
PATIENT="sub-003"
LESION="L1"
EXPECTED_MASK="derivatives/manual_lesion_annotations/sub-003/dyn/sub-003_acq-water_phase-venous_T1w-L1_seg.nii.gz"
FIELDS=("external_source","patient_id","index_lesion","original_source_image_member",
 "original_image_sha256","original_lesion_mask_member","original_mask_sha256",
 "source_image_shape","source_mask_shape","image_voxel_spacing_mm",
 "expert_mask_nonzero_voxels","physical_affine_corner_offset_mm",
 "source_phase","grid","binWidth","image_interpolation","mask_interpolation",
 "pyradiomics_version","MRI_RNA_eligible","clinical_approval","source_qualified_external_replication",
 "claim_ceiling")+FEATURE_KEYS

def matching(names):
    found=[n for n in names if PATIENT+"/" in n and
           "acq-water" in n.lower() and "phase-venous" in n.lower() and
           n.lower().endswith("_t1w.nii.gz")]
    if len(found)!=1:
        raise ValueError("UNIQUE_PATIENT_VENOUS_WATER_IMAGE_NOT_FOUND:"+str(len(found)))
    return found[0]

def member(url,path):
    with ZipFile(HTTPRangeFile(url)) as z:
        if path is None:path=matching(z.namelist())
        inf=z.getinfo(path)
        if inf.file_size<=352 or inf.file_size>96*1024*1024:
            raise ValueError("SOURCE_NIFTI_MEMBER_TOO_LARGE_OR_EMPTY")
        blob=get_member_with_ranges(url,inf,z.fp.total)
        if len(blob)!=inf.file_size:raise ValueError("SOURCE_OR_MASK_INCOMPLETE")
    return path,blob

def execute(image_blob,mask_blob,image_name,out):
    import nibabel as nib
    import numpy as np
    import importlib.metadata as im
    if im.version("pyradiomics")!="3.1.0":raise ValueError("PINNED_RADIOMICS_VERSION_DRIFT")
    with tempfile.TemporaryDirectory(prefix="hcc_external_openswiss_venous_") as tmp:
        ip=Path(tmp)/"image.nii.gz";mp=Path(tmp)/"mask.nii.gz"
        ip.write_bytes(image_blob);mp.write_bytes(mask_blob)
        image=nib.load(str(ip));mask=nib.load(str(mp))
        original_sha=hashlib.sha256(image_blob).hexdigest()
        mask_sha=hashlib.sha256(mask_blob).hexdigest()
        if image.ndim!=3 or mask.ndim!=3 or image.shape!=mask.shape:
            raise ValueError("OFFICIAL_MASK_SOURCE_NOT_SAME_NATIVE_IMAGE_SHAPE")
        geometry=corner_offset_mm(image.affine,mask.affine,mask.shape)
        if geometry>0.5:
            raise ValueError("EXTERNAL_VENOUS_IMAGE_MASK_GEOMETRY_NOT_VERIFIED")
        a=np.asarray(image.dataobj,dtype=np.float32)
        b=np.asarray(mask.dataobj)
        vox=int(np.count_nonzero(b))
        if vox<50 or vox>=a.size or not np.isfinite(a[b!=0]).all():
            raise ValueError("EMPTY_OR_NONFINITE_EXTERNAL_HCC_ROI")
        rows=[]
        for grid in ("native","3mm"):
            for bw in (12.5,25.,50.):
                ex=make_extractor(grid,bw)
                ex.settings["geometryTolerance"]=0.5
                stats=ex.execute(str(ip),str(mp),label=1)
                feat={k:float(stats[k]) for k in FEATURE_KEYS}
                if not all(math.isfinite(v) for v in feat.values()):
                    raise ValueError("NONFINITE_PILOT_RADIOMIC_FEATURE")
                rows.append({
                    "external_source":"OpenSwissHCC_v2", "patient_id":PATIENT,
                    "index_lesion":LESION,
                    "original_source_image_member":image_name,
                    "original_image_sha256":original_sha,
                    "original_lesion_mask_member":EXPECTED_MASK,
                    "original_mask_sha256":mask_sha,
                    "source_image_shape":"x".join(map(str,image.shape)),
                    "source_mask_shape":"x".join(map(str,mask.shape)),
                    "image_voxel_spacing_mm":";".join(str(round(float(z),6)) for z in image.header.get_zooms()[:3]),
                    "expert_mask_nonzero_voxels":vox,
                    "physical_affine_corner_offset_mm":round(float(geometry),6),
                    "source_phase":"native_venous_water_not_author_registered_pv",
                    "grid":grid,"binWidth":bw,
                    "image_interpolation":"NONE" if grid=="native" else "sitkBSpline",
                    "mask_interpolation":"NONE" if grid=="native" else "NEAREST_NEIGHBOR",
                    "pyradiomics_version":"3.1.0",
                    "MRI_RNA_eligible":"NOT_ASSESSED",
                    "clinical_approval":"NOT_ASSESSED",
                    "source_qualified_external_replication":"NO_SINGLE_CASE_PILOT",
                    "claim_ceiling":"S0",
                    **{k:round(v,9) for k,v in feat.items()}})
        return rows

def offline():
    # Do not accept duplicate MRI image filename or absent venous portal phase.
    assert matching(["sub-003/dyn/sub-003_acq-water_phase-venous_T1w.nii.gz"])=="sub-003/dyn/sub-003_acq-water_phase-venous_T1w.nii.gz"
    try:matching(["sub-003/dyn/sub-003_acq-water_phase-arterial_T1w.nii.gz"])
    except ValueError:pass
    else:raise AssertionError("ARTERIAL_WRONGLY_USED_AS_VENOUS")
    assert len(FEATURE_KEYS)==4
    print("OPENSWISS_V2_ONE_SUBJECT_SOURCE_VENOUS_MASK_MATCH_OFFLINE_PASS")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--offline-test",action="store_true")
    p.add_argument("--out-dir",type=Path,default=Path("artifacts/hcc_switzerland_hcc_pilot"))
    args=p.parse_args()
    if args.offline_test:return offline()
    imagename,im=member(IMG_ZIP,None)
    maskname,ma=member(MASK_ZIP,EXPECTED_MASK)
    if maskname!=EXPECTED_MASK:raise ValueError("VENOUS_LESION_MASK_PROVENANCE_CHANGED")
    rows=execute(im,ma,imagename,args.out_dir)
    out=args.out_dir;out.mkdir(parents=True,exist_ok=True)
    with (out/"openswiss_v2_one_HCC_subject_venous_2x3_feature_pilot.csv").open(
          "w",encoding="utf8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS)
        w.writeheader();w.writerows(rows)
    contrast={str(r["grid"])+"/"+str(r["binWidth"]):r["original_glcm_Contrast"] for r in rows}
    ref=contrast["native/25.0"]
    pct=(contrast["3mm/25.0"]-ref)/abs(ref)*100
    info={
      "status":"PASS_SINGLE_HCC_VENOUS_IMAGE_MASK_TECHNICAL_PILOT_NOT_EXTERNAL_REPLICATION",
      "source_zenodo":REC,"source_subject":PATIENT,"source_HCC_lesion":LESION,
      "source_image_member":imagename,
      "original_image_sha256":hashlib.sha256(im).hexdigest(),
      "source_lesion_mask_member":maskname,
      "original_mask_sha256":hashlib.sha256(ma).hexdigest(),
      "n_independent_source_subjects":1,"n_glcm_feature_conditions":6,
      "n_raw_source_MRI_archives_entirely_downloaded":0,
      "n_expert_mask_image_geometries_verified":1,
      "glcm_contrast_signed_pct_3mm25_vs_native25":round(pct,6),
      "original_liverhccseg_patient_overlap":0,
      "RNA_data_used":False,"MRI_RNA_12_tests":"NOT_EXECUTED",
      "external_replication_confirmed":False,
      "clinical_qualified_eligible_n":"NOT_ASSESSED","claim_ceiling":"S0"}
    (out/"openswiss_v2_single_subject_venous_pilot_summary.json").write_text(
        json.dumps(info,indent=2)+"\n")
    print("OPENSWISSHCC_V2_ONE_REAL_HCC_VENOUS_MASK_SAME_IMAGE_6_FEATURE_SETTINGS_PASS",json.dumps(info),flush=True)

if __name__=="__main__":main()
