#!/usr/bin/env python3
"""HCC 14 original PV HCC MRI × 2 raters, GLCM binWidth × voxel-grid factorial.

OUTCOME BLIND: no RNA, p-values, patient exclusion or pathway scores.
Prespecified 2x3 grid: native/3mm isotropic × binWidth 12.5, 25, 50
(PyRadiomics 3.1.0, normalize=True, normalizeScale=100).
Reference binWidth25 native and 3mm must reproduce frozen ICC before any
interpretation. Mask and image interpolation are unchanged from 3mm pilot.
"""
import argparse,csv,json,math,tempfile
from datetime import datetime,timezone
from pathlib import Path
from zipfile import ZipFile

from mri_pv_3mm_resampling_sensitivity import (
 index_archive_members,RATERS,ISOTROPIC_MM,RESAMPLE_INTERPOLATOR
)
from mri_pv_pyradiomics_rater_icc import (
 PARAMS, load_frozen_cases,niftis_match,read_member
)
from mri_mask_voxel_audit import HTTPRangeFile
from zenodo_nifti_zip_inventory import ARCHIVE

SOURCE="research/hcc/HCC_MRI_14_PREOUTCOME_INDEX_LESION_SELECTION_20261030.csv"
VERSION="hcc-pv-glcm-spacing-binwidth-factorial-v1"
SPACING=("native","3mm")
BINWIDTH=(12.5,25.0,50.0)
FEATURES={
 "glcm":["Contrast","JointEntropy"],
 "firstorder":["Entropy","InterquartileRange"],
}
FEATURE_KEYS=(
 "original_glcm_Contrast","original_glcm_JointEntropy",
 "original_firstorder_Entropy","original_firstorder_InterquartileRange"
)
FIELDS=("patient_id","rater","tumor_number","phase","spacing_condition",
        "target_voxel_spacing_mm","bin_width","native_z_spacing_mm",
        "pyradiomics_version","image_interpolation","roi_mask_interpolation",
        "symmetric_glcm","glcm_neighbor_distance_voxels",
        "clinical_eligibility")+FEATURE_KEYS

def make_extractor(spacing,bin_width):
    from radiomics import featureextractor
    params=dict(PARAMS)
    params["binWidth"]=float(bin_width)
    params["symmetricalGLCM"]=True
    params["distances"]=[1]
    if spacing=="3mm":
        params.update({
            "resampledPixelSpacing":[3.0,3.0,3.0],
            "interpolator":"sitkBSpline",
            "padDistance":5,
        })
    elif spacing!="native":
        raise ValueError("Unknown spacing")
    out=featureextractor.RadiomicsFeatureExtractor(**params)
    out.disableAllImageTypes()
    out.enableImageTypeByName("Original")
    out.disableAllFeatures()
    out.enableFeaturesByName(**FEATURES)
    return out

def extract_case(archive,pid,index,paths,extractors):
    import radiomics
    import SimpleITK as sitk
    if radiomics.__version__.lstrip("v")!="3.1.0":
        raise ValueError("Pinned PyRadiomics 3.1.0 mismatch")
    pv,m1,m2=paths
    with tempfile.TemporaryDirectory(prefix="hcc_factor_") as directory:
        image_path=Path(directory)/"pv.nii.gz"
        mask_paths={}
        read_member(archive,pv,image_path)
        for rater,member in zip(RATERS,(m1,m2)):
            mask_paths[rater]=Path(directory)/(rater+".nii.gz")
            read_member(archive,member,mask_paths[rater])
        image=sitk.ReadImage(str(image_path))
        output=[]
        for rater in RATERS:
            s=niftis_match(image_path,mask_paths[rater])
            mask=sitk.ReadImage(str(mask_paths[rater]))
            if s[-1]<=0:raise ValueError("No native z spacing")
            for space in SPACING:
                for bw in BINWIDTH:
                    features=extractors[(space,bw)].execute(image,mask,label=1)
                    values={key:float(features[key]) for key in FEATURE_KEYS}
                    if not all(math.isfinite(x) for x in values.values()):
                        raise ValueError("Nonfinite extracted GLCM or firstorder feature")
                    output.append({
                        "patient_id":pid,"rater":rater,"tumor_number":index,
                        "phase":"PV","spacing_condition":space,
                        "target_voxel_spacing_mm":"" if space=="native" else 3.0,
                        "bin_width":bw,
                        "native_z_spacing_mm":s[-1],
                        "pyradiomics_version":radiomics.__version__,
                        "image_interpolation":"NONE" if space=="native" else "sitkBSpline",
                        "roi_mask_interpolation":"NONE" if space=="native" else "NEAREST_NEIGHBOR",
                        "symmetric_glcm":"YES",
                        "glcm_neighbor_distance_voxels":1,
                        "clinical_eligibility":"HOLD_UNRESOLVED_NOT_EXCLUDED",
                        **values
                    })
        return output

def validate(rows,ids):
    if len(ids)!=7 or len(rows)!=7*2*len(SPACING)*len(BINWIDTH):
        raise ValueError("Each shard must contain 7×2×2×3=84 extraction records")
    expected={(pid,r,space,bw) for pid in ids for r in RATERS
              for space in SPACING for bw in BINWIDTH}
    observed={(r["patient_id"],r["rater"],r["spacing_condition"],float(r["bin_width"]))
              for r in rows}
    if len(observed)!=len(rows) or expected!=observed:
        raise ValueError("Missing/duplicated patient-rater-condition cells")
    for row in rows:
        if (row["clinical_eligibility"]!="HOLD_UNRESOLVED_NOT_EXCLUDED" or
            row["phase"]!="PV" or row["symmetric_glcm"]!="YES"):
            raise ValueError("Frozen source/GLCM assumption unexpectedly changed")
        if row["spacing_condition"]=="3mm" and row["image_interpolation"]!="sitkBSpline":
            raise ValueError("Wrong interpolation")
        if not all(math.isfinite(float(row[f])) for f in FEATURE_KEYS):
            raise ValueError("Nonfinite extraction")
    return True

def offline_test():
    cases=load_frozen_cases(SOURCE)
    assert len(cases)==14 and cases["TCGA-BC-A10Y"]==3
    assert len(SPACING)*len(BINWIDTH)==6
    assert PARAMS["binWidth"]==25.0 and PARAMS["normalizeScale"]==100.
    # PyRadiomics docs example: symmetric horizontal 5x5 GLCM entries
    # matrix count sum = 40, sum[p(i,j)*(i-j)^2] = 116
    # Contrast for this one direction = 116/40 = 2.9.
    p=((6,4,3,0,0),(4,0,2,1,3),(3,2,0,1,2),
       (0,1,1,0,0),(0,3,2,0,2))
    z=sum(p[i][j]*(i-j)**2 for i in range(5) for j in range(5))
    assert sum(map(sum,p))==40 and z==116 and abs(z/40-2.9)<1e-12
    print("HCC_GLCM_2x3_FACTORIAL_AND_PYRAD_DOC_EXAMPLE_OFFLINE_PASS")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--offline-test",action="store_true")
    ap.add_argument("--shard",type=int,default=0)
    ap.add_argument("--out-dir",default="artifacts/hcc_factorial")
    a=ap.parse_args()
    if a.offline_test:return offline_test()
    if a.shard not in (0,1):raise ValueError("Locked two shards")
    frozen=load_frozen_cases(SOURCE)
    ids=sorted(frozen)[a.shard::2]
    if len(ids)!=7:raise ValueError("Wrong cohort shard")
    extractors={(s,b):make_extractor(s,b) for s in SPACING for b in BINWIDTH}
    records=[];errors=[]
    with ZipFile(HTTPRangeFile(ARCHIVE)) as archive:
        paths=index_archive_members(archive,frozen)
        for pid in ids:
            try:
                records.extend(extract_case(archive,pid,frozen[pid],paths[pid],extractors))
                print("HCC_FACTORIAL_SOURCE_PATIENT_PASS="+pid,flush=True)
            except Exception as exc:
                errors.append({"patient_id":pid,"error_type":type(exc).__name__,
                               "error_message":str(exc)[:350]})
                print("HCC_FACTORIAL_SOURCE_PATIENT_FAIL="+pid+":"+str(exc)[:180],flush=True)
    target=Path(a.out_dir);target.mkdir(parents=True,exist_ok=True)
    with (target/f"glcm_bin_spacing_shard{a.shard}.csv").open(
            "w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();w.writerows(records)
    state={
        "version":VERSION,"shard":a.shard,"patients_expected":ids,
        "patients_with_extraction_rows":len({x["patient_id"] for x in records}),
        "total_extraction_rows":len(records),"errors":errors,
        "factorial_spacing_conditions":SPACING,"bin_widths":BINWIDTH,
        "glcm_options":{"symmetricalGLCM":True,"distances":[1],"weightingNorm":None},
        "resampling":{"target_spacing_mm":3.0,"image_interpolation":"sitkBSpline",
                      "mask_interpolation":"nearest-neighbor"},
        "clinical_eligibility":"NOT_ASSESSED",
        "mri_rna_association_run":False
    }
    if not errors:
        validate(records,ids)
        state["status"]="PASS_7_PATIENT_84_EXTRACTOR_FACTORIAL"
    else:state["status"]="FAIL_SOURCE_EXTRACTION"
    (target/f"glcm_bin_spacing_shard{a.shard}.json").write_text(
        json.dumps(state,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(state,ensure_ascii=False))
    if errors:raise SystemExit(1)
if __name__=="__main__":main()
