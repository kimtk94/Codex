#!/usr/bin/env python3
"""HCC PV MRI paired 3mm isotropic resampling sensitivity: 14 index lesions × 2 readers.

NO RNA outcomes here. Original native radiomics uses unchanged published pilot
extraction parameters (PyRadiomics 3.1.0) and the same original image and
same-lesion binary masks in both conditions. Internal PyRadiomics resampling:
3mm isotropic voxels, B-spline image interpolation, nearest-neighbor label
interpolation. We do not infer that 10.8mm original sections regain detail.

Choose configuration before observing MRI-RNA associations. The original
3×4 feature/pathway plan remains unchanged and blocked by clinical gates.
"""
import argparse,csv,json,math,statistics,tempfile
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
from zipfile import ZipFile

import numpy as np
from fast_zip_member_range import get_member_with_ranges
from mri_mask_voxel_audit import HTTPRangeFile
from mri_pv_pyradiomics_rater_icc import (
    PARAMS,FEATURES,FEATURES_to_names,absolute_agreement_icc,
    load_frozen_cases,make_extractor,niftis_match,selected_paths,read_member
)
from zenodo_nifti_zip_inventory import ARCHIVE,is_apple_sidecar

ISOTROPIC_MM=3.0
RESAMPLE_INTERPOLATOR="sitkBSpline"
MIN_ROI_VOXELS=50
VERSION="hcc-pv-3mm-resampling-v1"
SOURCE="research/hcc/HCC_MRI_14_PREOUTCOME_INDEX_LESION_SELECTION_20261030.csv"
PATIENTS=14
RATERS=("rater1","rater2")
SETTINGS={
 "resampledPixelSpacing":[ISOTROPIC_MM]*3,
 "interpolator":RESAMPLE_INTERPOLATOR,
 "padDistance":5,
}
FIELDS=("patient_id","rater","selected_tumor_number","source_phase",
        "voxel_spacing_mm","native_roi_voxels","native_roi_volume_ml",
        "estimated_grid_roi_voxels_3mm","isotropic_spacing_mm",
        "resampling_interpolator","native_extractor_version",
        "resampled_extractor_version","image_mask_affine_qc","native_qc",
        "resampled_qc","clinical_eligibility")
FEATURE_NAMES=tuple(FEATURES_to_names())
COLS=FIELDS + tuple("native__"+k for k in FEATURE_NAMES)+tuple("resampled__"+k for k in FEATURE_NAMES)

def iso_extractor():
    from radiomics import featureextractor
    params={**PARAMS,**SETTINGS}
    x=featureextractor.RadiomicsFeatureExtractor(**params)
    x.disableAllImageTypes()
    x.enableImageTypeByName("Original")
    x.disableAllFeatures()
    x.enableFeaturesByName(**FEATURES)
    return x

def index_archive_members(archive, cases):
    names={x.filename for x in archive.infolist() if not x.is_dir()
           and not is_apple_sidecar(x.filename)}
    result={}
    for pid in sorted(cases):
        roots=sorted(x for x in names
                     if pid in x and x.endswith("/rater1_tumor1.nii.gz"))
        if len(roots)!=1:
            raise ValueError(f"{pid} expected exactly one known source mask root; got {len(roots)}")
        pv,m1,m2=selected_paths(roots[0],cases[pid])
        if not all(x in names for x in (pv,m1,m2)):
            raise ValueError(f"Missing PV and same-index two reader masks for {pid}")
        result[pid]=(pv,m1,m2)
    return result

def extract_case(archive,pid,tumor,member_paths,native,iso):
    import nibabel as nib
    import radiomics
    from radiomics import imageoperations
    import SimpleITK as sitk
    if radiomics.__version__.lstrip("v")!="3.1.0":
        raise ValueError("Require frozen original PyRadiomics 3.1.0 not "+radiomics.__version__)
    pv,m1,m2=member_paths
    with tempfile.TemporaryDirectory(prefix="hcc_pv_iso_") as d:
        paths={}
        for label,member in (("pv",pv),("rater1",m1),("rater2",m2)):
            target=Path(d)/(label+".nii.gz")
            read_member(archive,member,target)
            paths[label]=target
        image=nib.load(str(paths["pv"]))
        pixvol=float(abs(np.linalg.det(image.affine[:3,:3])))
        if not 0<pixvol<200:raise ValueError("Implausible source mm3 voxel")
        result=[]
        for rater in RATERS:
            spacing=niftis_match(paths["pv"],paths[rater])
            mask=nib.load(str(paths[rater]))
            arr=np.asarray(mask.dataobj)
            voxels=int(np.count_nonzero(arr))
            if voxels<MIN_ROI_VOXELS:raise ValueError("Native tumor mask empty")
            # Check both resampling conditions using the same physical ROI.
            old=native.execute(str(paths["pv"]),str(paths[rater]),label=1)
            newer=iso.execute(str(paths["pv"]),str(paths[rater]),label=1)
            v1={k:float(old[k]) for k in FEATURE_NAMES}
            v2={k:float(newer[k]) for k in FEATURE_NAMES}
            if not all(math.isfinite(v) for v in (*v1.values(),*v2.values())):
                raise ValueError("Nonfinite original or 3mm PyRadiomics feature")
            # PyRadiomics resampleImage gives exact regridded label
            # (nearest neighbor) independent of feature values.
            sitk_img=sitk.ReadImage(str(paths["pv"]))
            sitk_mask=sitk.ReadImage(str(paths[rater]))
            grid_img,grid_mask=imageoperations.resampleImage(
                sitk_img,sitk_mask,resampledPixelSpacing=[ISOTROPIC_MM]*3,
                interpolator=RESAMPLE_INTERPOLATOR,
                padDistance=5,label=1)
            iso_array=sitk.GetArrayViewFromImage(grid_mask)
            nn=int(np.count_nonzero(iso_array))
            if nn<MIN_ROI_VOXELS or any(abs(float(s)-ISOTROPIC_MM)>1e-5
                   for s in grid_mask.GetSpacing()):
                raise ValueError("Isotropic mask grid spacing/volume invalid")
            original_ml=voxels*pixvol/1000.0
            iso_ml=nn*(ISOTROPIC_MM**3)/1000.0
            # Grid-induced ROI volume drift is QC observation, not automatic exclusion.
            if original_ml<=0 or not math.isfinite(iso_ml):
                raise ValueError("Invalid physical source volume")
            result.append({
                "patient_id":pid,"rater":rater,
                "selected_tumor_number":tumor,
                "source_phase":"PV",
                "voxel_spacing_mm":"x".join(str(v) for v in spacing),
                "native_roi_voxels":voxels,
                "native_roi_volume_ml":round(original_ml,6),
                "estimated_grid_roi_voxels_3mm":nn,
                "isotropic_spacing_mm":ISOTROPIC_MM,
                "resampling_interpolator":RESAMPLE_INTERPOLATOR,
                "native_extractor_version":radiomics.__version__,
                "resampled_extractor_version":radiomics.__version__,
                "image_mask_affine_qc":"PASS_NATIVE_SOURCE_MATCH",
                "native_qc":"PASS_FEATURE_EXTRACTION",
                "resampled_qc":"PASS_3MM_FEATURE_EXTRACTION",
                "clinical_eligibility":"HOLD_UNRESOLVED_NOT_EXCLUDED",
                **{"native__"+k:v for k,v in v1.items()},
                **{"resampled__"+k:v for k,v in v2.items()}
            })
        return result

def validate_rows(rows,expected,shard_index,num_shards):
    ids=sorted({r["patient_id"] for r in rows})
    if ids!=sorted(expected) or len(rows)!=2*len(expected):
        raise ValueError("Incomplete shard or missing patient-rater pairs")
    by_key={}
    for r in rows:
        k=(r["patient_id"],r["rater"])
        if k in by_key or r["rater"] not in RATERS:
            raise ValueError("Duplicate reader case pair")
        by_key[k]=r
        if r["clinical_eligibility"]!="HOLD_UNRESOLVED_NOT_EXCLUDED":
            raise ValueError("Unverified MRI/RNA case promoted")
        if (r["isotropic_spacing_mm"]!=3.0 or
            r["resampling_interpolator"]!="sitkBSpline" or
            r["image_mask_affine_qc"]!="PASS_NATIVE_SOURCE_MATCH"):
            raise ValueError("Wrong configured image interpolation or affine")
        for name in FEATURE_NAMES:
            for prefix in ("native__","resampled__"):
                val=float(r[prefix+name])
                if not math.isfinite(val):
                    raise ValueError("Nonfinite feature on "+str(k))
    return {"status":"PASS_SHARD_PAIRED_NATIVE_3MM_FEATURES",
            "shard_index":shard_index,"num_shards":num_shards,
            "patients":len(expected),"rater_rows":len(rows),
            "feature_count":len(FEATURE_NAMES),"feature_family_locked":True,
            "source_resampled_pixel_spacing_mm":ISOTROPIC_MM,
            "resampling_interpolator":RESAMPLE_INTERPOLATOR,
            "exclusion_by_outcome":False,"clinical_eligibility":"NOT_ASSESSED",
            "mri_rna_tests_executed":False,
            "generated_utc":datetime.now(timezone.utc).isoformat()}

def offline_test():
    cases=load_frozen_cases(SOURCE)
    assert len(cases)==14 and cases["TCGA-BC-A10Y"]==3
    assert len(FEATURE_NAMES)==10
    assert PARAMS["resampledPixelSpacing"] is None
    assert SETTINGS["resampledPixelSpacing"]==[3.0,3.0,3.0]
    assert SETTINGS["interpolator"]=="sitkBSpline"
    ids=sorted(cases)
    assert len(ids[:7])==7 and len(ids[7:])==7
    # No model-level RNA outcome available to this script.
    print("HCC_PV_3MM_IMAGE_RESAMPLING_SENSITIVITY_OFFLINE_PASS")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--offline-test",action="store_true")
    ap.add_argument("--shard-index",type=int,default=0)
    ap.add_argument("--num-shards",type=int,default=2)
    ap.add_argument("--out-dir",default="artifacts/hcc_pv_resampling")
    args=ap.parse_args()
    if args.offline_test:return offline_test()
    if args.num_shards!=2 or args.shard_index not in (0,1):
        raise ValueError("Locked exactly two seven-patient independent shards")
    cases=load_frozen_cases(SOURCE)
    ids=sorted(cases)
    selected=ids[args.shard_index::args.num_shards]
    if len(selected)!=7:raise ValueError("Expected exactly seven patients per shard")
    native=make_extractor()
    iso=iso_extractor()
    rows=[]; errors=[]
    with ZipFile(HTTPRangeFile(ARCHIVE)) as archive:
        paths=index_archive_members(archive,cases)
        for pid in selected:
            try:
                rows.extend(extract_case(archive,pid,cases[pid],paths[pid],native,iso))
                print("HCC_RESAMPLED_PATIENT_PASS="+pid,flush=True)
            except Exception as e:
                errors.append({"patient_id":pid,"error_type":type(e).__name__,
                               "message":str(e)[:500]})
                print("HCC_RESAMPLED_PATIENT_FAILURE="+pid+": "+str(e)[:200],flush=True)
    out=Path(args.out_dir);out.mkdir(parents=True,exist_ok=True)
    with (out/f"hcc_pv_native_3mm_features_shard{args.shard_index}.csv").open(
        "w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=COLS)
        w.writeheader();w.writerows(rows)
    summary={"version":VERSION,
             "requested_patient_ids":selected,"errors":errors,
             "settings_native":PARAMS,
             "settings_resampled":{**PARAMS,**SETTINGS},
             "source_archive":ARCHIVE,
             "features":list(FEATURE_NAMES)}
    if not errors:
        summary.update(validate_rows(rows,selected,args.shard_index,args.num_shards))
    else:summary["status"]="FAIL_SHARD_SUBJECT_MISSING"
    (out/f"hcc_pv_3mm_summary_shard{args.shard_index}.json").write_text(
        json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:v for k,v in summary.items() if k not in ("settings_native","settings_resampled")},ensure_ascii=False))
    if errors:raise SystemExit(1)

if __name__=="__main__":main()
