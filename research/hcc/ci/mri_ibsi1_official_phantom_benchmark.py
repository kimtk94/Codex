#!/usr/bin/env python3
"""IBSI-1 OFFICIAL 5x4x4 digital phantom, not a synthetic reproduction.

Three modes:
  source: original GitHub checkout image/mask provenance/hash/volume anatomy.
  measure: pinned PyRadiomics 3.1.0 (3D averaged GLCM Contrast) on original
           official phantom NIfTI, reports diff from IBSI 5.32.
  offline-test: no download: assert reference bookkeeping and fail-closed.
IBSI 3D merged contrast 5.12 is a different estimator and NOT the reference
for default PyRadiomics feature averaging. Result mismatches are REVIEW,
never silently labelled compliant. This is not an IBSI conformance certificate.
"""
import argparse,hashlib,json,math,subprocess
from datetime import datetime,timezone
from pathlib import Path

OFFICIAL="https://github.com/theibsi/data_sets"
PHANTOM_SUB="ibsi_1_digital_phantom/nifti"
REFERENCE={"3d_direction_average":5.32,"3d_direction_merge":5.12}
ACCEPT=0.025  # diagnostic bound, not IBSI-published phantom tolerance
EXPECTED_DIMS=(5,4,4)
EXPECTED_ROI=74
SETTINGS={
 "binWidth":1.0,"normalize":False,"voxelArrayShift":0,
 "resampledPixelSpacing":None,"correctMask":False,
 "additionalInfo":False,"minimumROIDimensions":2,
 "symmetricalGLCM":True,"distances":[1],"weightingNorm":None,
}

def sha(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda:f.read(1048576),b""):h.update(chunk)
    return h.hexdigest()

def find_original_files(folder):
    root=Path(folder)
    path=root/PHANTOM_SUB
    if not path.is_dir():raise ValueError("Official NIfTI path not found: "+str(path))
    all_files=sorted(p for p in path.rglob("*") if p.is_file()
                     and (p.name.endswith(".nii.gz") or p.name.endswith(".nii")))
    def choose(kind):
        candidates=[p for p in all_files if kind in p.name.lower()]
        if len(candidates)!=1:
            raise ValueError(f"Ambiguous official IBSI NIfTI {kind} files "+
                             repr([str(p) for p in all_files]))
        return candidates[0]
    return choose("image"),choose("mask")

def source_info(folder):
    image,mask=find_original_files(folder)
    sha_commit=subprocess.check_output(
         ["git","-C",str(folder),"rev-parse","HEAD"],text=True).strip()
    return {"official_source_repo":OFFICIAL,"official_source_commit_sha":sha_commit,
            "official_source_image":str(image),"official_source_mask":str(mask),
            "image_sha256":sha(image),"mask_sha256":sha(mask),
            "image_bytes":image.stat().st_size,"mask_bytes":mask.stat().st_size,
            "source_reference_3d_avg":REFERENCE["3d_direction_average"],
            "distinct_3d_merged_reference":REFERENCE["3d_direction_merge"],
            "phantom_claim":"IBSI_1_ORIGINAL_NOT_IBSI_2"}

def verify_phantom(image,mask):
    import nibabel as nib
    import numpy as np
    img=nib.load(str(image));msk=nib.load(str(mask))
    if img.shape!=msk.shape or sorted(img.shape)!=sorted(EXPECTED_DIMS):
        raise ValueError(f"Official image/mask dimensions mismatch: {img.shape}, {msk.shape}")
    if not np.allclose(img.affine,msk.affine,atol=1.e-4):
        raise ValueError("Official source image/mask geometry mismatch")
    roi=np.asarray(msk.dataobj)>0
    n=int(np.count_nonzero(roi))
    if n!=EXPECTED_ROI:raise ValueError("IBSI original ROI should have exactly 74 voxels: "+str(n))
    values=np.asarray(img.dataobj)[roi]
    if np.any(~np.isfinite(values)) or np.min(values)<0:
        raise ValueError("IBSI image intensity is not finite positive")
    return {"shape":[int(x) for x in img.shape],
            "affine_match":True,"original_roi_voxels":n,
            "input_gray_level_min":float(np.min(values)),
            "input_gray_level_max":float(np.max(values)),
            "mask_label_values":sorted(float(x) for x in np.unique(np.asarray(msk.dataobj))),
            "original_spacing_mm":[float(x) for x in img.header.get_zooms()[:3]]}

def compute(img,msk):
    import radiomics
    from radiomics import featureextractor
    if radiomics.__version__.lstrip("v")!="3.1.0":
        raise ValueError("Expected pinned PyRadiomics v3.1.0")
    x=featureextractor.RadiomicsFeatureExtractor(**SETTINGS)
    x.disableAllImageTypes()
    x.enableImageTypeByName("Original")
    x.disableAllFeatures()
    x.enableFeaturesByName(glcm=["Contrast","JointEntropy"])
    results=x.execute(str(img),str(msk),label=1)
    observed=float(results["original_glcm_Contrast"])
    entropy=float(results["original_glcm_JointEntropy"])
    if not math.isfinite(observed) or not math.isfinite(entropy):
        raise ValueError("Nonfinite software benchmark")
    difference=observed-REFERENCE["3d_direction_average"]
    return {
      "status":"PASS_MATCH_TO_IBSI_3D_AVG_REFERENCE" if abs(difference)<=ACCEPT
                else "REVIEW_SOFTWARE_REFERENCE_DEVIATION",
      "software":"PyRadiomics","software_version":radiomics.__version__,
      "feature":"original_glcm_Contrast","IBSI_feature_code":"ACUI",
      "aggregation":"3D_DIRECTION_AVERAGE_PYRAD_DEFAULT_UNWEIGHTED",
      "referenced_IBSI_3d_avg":REFERENCE["3d_direction_average"],
      "observed_contrast":observed,"signed_difference_from_5_32":difference,
      "absolute_difference":abs(difference),
      "diagnostic_tolerance_not_official":ACCEPT,
      "distinct_IBSI_3d_merge_reference_not_tested":REFERENCE["3d_direction_merge"],
      "observed_joint_entropy":entropy,
      "settings":SETTINGS,
      "do_not_claim_full_IBSI_certification":True,
      "hcc_14_patient_clinical_eligibility":"NOT_ASSESSED",
      "mri_rna_associations_run":False
    }

def offline_test():
    assert REFERENCE["3d_direction_average"]==5.32
    assert REFERENCE["3d_direction_merge"]==5.12
    assert ACCEPT<abs(REFERENCE["3d_direction_average"]-REFERENCE["3d_direction_merge"])
    assert SETTINGS["normalize"] is False
    assert SETTINGS["binWidth"]==1.
    assert SETTINGS["resampledPixelSpacing"] is None
    assert SETTINGS["distances"]==[1]
    assert SETTINGS["symmetricalGLCM"] is True
    print("IBSI1_OFFICIAL_PHANTOM_SOURCE_AND_GLCM_REFERENCE_OFFLINE_PASS")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--mode",choices=("source","measure"),default="source")
    p.add_argument("--repo-dir",default="artifacts/ibsi_original_repo")
    p.add_argument("--out-dir",default="artifacts/hcc_ibsi")
    p.add_argument("--offline-test",action="store_true")
    a=p.parse_args()
    if a.offline_test:return offline_test()
    source=source_info(a.repo_dir)
    if a.mode=="measure":
        image,mask=find_original_files(a.repo_dir)
        source["original_image_roi"]=verify_phantom(image,mask)
        source.update(compute(image,mask))
    else:source["status"]="PASS_OFFICIAL_NIFTI_SOURCE_PROVENANCE"
    source["created_utc"]=datetime.now(timezone.utc).isoformat()
    out=Path(a.out_dir);out.mkdir(parents=True,exist_ok=True)
    filename=("hcc_ibsi1_pyradiomics_benchmark.json" if a.mode=="measure"
               else "hcc_ibsi1_official_source_manifest.json")
    (out/filename).write_text(json.dumps(source,ensure_ascii=False,indent=2)+"\n",
                              encoding="utf-8")
    print(json.dumps(source,ensure_ascii=False))
if __name__=="__main__":main()
