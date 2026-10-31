#!/usr/bin/env python3
"""Official IBSI CT original source preflight and configuration coverage.

Distinguish:
 IBSI-1 Phase II: CT PAT1, ROI GTV-1, five configs A-E (IBSI1 processing).
 IBSI-2 Phase II: filtered-image CT response maps (not IBSI-1 A-E).
This audit does *not* pretend to reproduce either preprocessing pipeline.
Official CT images are CC BY-NC 3.0; do not upload raw image/ROI artifacts.
"""
import argparse,hashlib,json,math,subprocess
from datetime import datetime,timezone
from pathlib import Path

COMMIT="6da96021bc91faf4c0cb7fd7fa56a4225d2064a8"
ROOTS=("ibsi_1_ct_radiomics_phantom","ibsi_2_ct_radiomics_phantom")
DATA="nifti"
CONFIGS={
 "A":{"dimensions":"2D","interpolation":"NONE","intensity_resegmentation":"[-500,400] HU","texture_discretization":"FBS25HU","roi_mask_rule":"NATIVE","reference_complete":False},
 "B":{"dimensions":"2D","interpolation":"2x2mm bilinear","intensity_resegmentation":"[-500,400] HU","texture_discretization":"FBN32","roi_mask_rule":"BILINEAR_THRESHOLD_0.5","reference_complete":False},
 "C":{"dimensions":"3D","interpolation":"2x2x2mm trilinear","intensity_resegmentation":"[-1000,400] HU","texture_discretization":"FBS25HU","roi_mask_rule":"TRILINEAR_THRESHOLD_0.5","reference_complete":False},
 "D":{"dimensions":"3D","interpolation":"2x2x2mm trilinear","intensity_resegmentation":"3SIGMA_OUTLIER","texture_discretization":"FBN32","roi_mask_rule":"TRILINEAR_THRESHOLD_0.5","reference_complete":False},
 "E":{"dimensions":"3D","interpolation":"2x2x2mm tricubic","intensity_resegmentation":"[-1000,400]HU + 3SIGMA","texture_discretization":"FBN32","roi_mask_rule":"TRILINEAR_THRESHOLD_0.5","reference_complete":False},
}
def digest(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for x in iter(lambda:f.read(1048576),b""):h.update(x)
    return h.hexdigest()

def check(repo_dir):
    import nibabel as nib
    import numpy as np
    root=Path(repo_dir)
    commit=subprocess.check_output(["git","-C",str(root),"rev-parse","HEAD"],text=True).strip()
    if commit!=COMMIT:raise ValueError("Official upstream IBSI source commit changed")
    entries=[]
    for sub in ROOTS:
        img=root/sub/DATA/"image"/"phantom.nii.gz"
        mask=root/sub/DATA/"mask"/"mask.nii.gz"
        lic=root/sub/"README.md"
        if not img.exists() or not mask.exists() or not lic.exists():
            raise ValueError("Official CT image/mask/license missing for "+sub)
        license_readme=lic.read_text(encoding="utf-8")
        if "Attribution-NonCommercial 3.0" not in license_readme:
            raise ValueError("Expected official CT non-commercial licensing note")
        image=nib.load(str(img));seg=nib.load(str(mask))
        if image.shape!=seg.shape or len(image.shape)!=3:
            raise ValueError("Official CT image and mask dimensions mismatch")
        if not np.allclose(image.affine,seg.affine,atol=0.0001):
            raise ValueError("CT image/ROI exact native affine mismatch")
        roi=np.asarray(seg.dataobj)
        n=int(np.count_nonzero(roi>0))
        if n<100 or n>=int(np.prod(image.shape)):
            raise ValueError("CT tumor ROI invalid")
        vals=np.asarray(image.dataobj)
        if not np.isfinite(vals).all():raise ValueError("Nonfinite original CT source")
        entries.append({
            "collection":sub,"source_commit":commit,
            "nifti_image_path":str(img.relative_to(root)),
            "nifti_mask_path":str(mask.relative_to(root)),
            "image_sha256":digest(img),"mask_sha256":digest(mask),
            "shape":[int(x) for x in image.shape],
            "spacing_mm":[float(x) for x in image.header.get_zooms()[:3]],
            "voxel_roi_count":n,
            "original_intensity_min":float(vals.min()),
            "original_intensity_max":float(vals.max()),
            "license":"CC_BY_NC_3_0",
            "raw_patient_or_image_bytes_uploaded":False,
            "clinical_HCC_14_eligibility":"NOT_ASSESSED"
        })
    a,b=entries
    if (a["image_sha256"]!=b["image_sha256"] or a["mask_sha256"]!=b["mask_sha256"]):
        raise ValueError("IBSI1 CT and IBSI2 CT source are not identical: version review required")
    return {
      "status":"PASS_ORIGINAL_IBSI1_AND_IBSI2_CT_NIFTI_IDENTICAL_SOURCE",
      "source_commit_sha":commit,
      "n_ct_source_instances":len(entries),
      "original_ct_sources":entries,
      "IBSI_1_phase_II_5_configurations":CONFIGS,
      "IBSI_1_phase_II_preprocessing_reproduced":False,
      "IBSI_2_phase_II_filtered_feature_benchmark_reproduced":False,
      "official_source_read_only":True,
      "noncommercial_license_notice":"Do not redistribute CT phantom bytes; IBSI CT README states CC BY-NC 3.0.",
      "scan_data_used_for_clinical_HCC":False,
      "full_IBSI_compliance":False,
      "mri_rna_hypotheses_run":False,
      "claim_ceiling":"S0",
      "generated_utc":datetime.now(timezone.utc).isoformat()
    }

def offline_test():
    assert len(ROOTS)==2 and len(CONFIGS)==5
    assert CONFIGS["A"]["texture_discretization"]=="FBS25HU"
    assert CONFIGS["C"]["dimensions"]=="3D"
    assert CONFIGS["E"]["interpolation"]=="2x2x2mm tricubic"
    assert all(v["reference_complete"] is False for v in CONFIGS.values())
    print("HCC_IBSI_CT_PHASE_NOMENCLATURE_FIVE_CONFIGS_LICENSE_OFFLINE_PASS")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--offline-test",action="store_true")
    p.add_argument("--repo-dir",default="artifacts/ibsi_original_repo")
    p.add_argument("--out-dir",default="artifacts/hcc_ibsi_ct")
    a=p.parse_args()
    if a.offline_test:return offline_test()
    v=check(a.repo_dir)
    folder=Path(a.out_dir);folder.mkdir(parents=True,exist_ok=True)
    (folder/"hcc_ibsi1_ibsi2_ct_source_provenance_and_config_readiness.json").write_text(
        json.dumps(v,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"status":v["status"],
       "sources":[{"collection":x["collection"],"shape":x["shape"],
                   "spacing_mm":x["spacing_mm"],"roi_count":x["voxel_roi_count"],
                   "image_sha256":x["image_sha256"],"mask_sha256":x["mask_sha256"]}
                  for x in v["original_ct_sources"]],
       "IBSI_1_phase_II_preprocessing_reproduced":False,
       "IBSI_2_phase_II_filtered_feature_benchmark_reproduced":False},ensure_ascii=False))
if __name__=="__main__":main()
