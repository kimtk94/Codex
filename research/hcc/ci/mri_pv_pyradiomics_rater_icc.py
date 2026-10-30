#!/usr/bin/env python3
"""HCC public LiverHccSeg PV MRI: two-reader PyRadiomics feature stability.

Input cases are the *previously frozen* index lesions, selected by rater1 tumor
volume, not by gene correlation. Fetch MRI PV once and tumor rater1/rater2
same lesion number via bounded public Zenodo ZIP HTTP Range. ZIP CRC checked.
No full image or expression matrix committed; no MRI-RNA association tested.

ICC(A,1) is a two-way random effects absolute-agreement, single-rating ICC.
Patient bootstrap percentile intervals are descriptive with n <=14.
Physical/tissue chronology and reviewer anatomical approval are NOT inferred.
"""
import argparse
import csv
import gzip
import json
import math
import os
import statistics
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

SOURCE_CSV = "research/hcc/HCC_MRI_14_PREOUTCOME_INDEX_LESION_SELECTION_20261030.csv"
FEATURES = {
    "shape": ["VoxelVolume", "SurfaceArea", "Sphericity", "Elongation"],
    "firstorder": ["Mean", "Median", "Entropy", "InterquartileRange"],
    "glcm": ["Contrast", "JointEntropy"],
}
# This is a PILOT configuration; not a complete IBSI-compliant declaration.
PARAMS = {
    "binWidth": 25.0,
    "normalize": True,
    "normalizeScale": 100.0,
    "voxelArrayShift": 0,
    "resampledPixelSpacing": None,
    "correctMask": False,
    "additionalInfo": False,
    "minimumROIDimensions": 2,
    "preCrop": True,
}
CSV_FIELDS = ("patient_id", "rater", "selected_tumor_number", "source_phase",
              "source_image", "tumor_mask", "extractor_version",
              "voxel_spacing_mm", "qc_status", "error")
ICC_FIELDS = ("feature", "n_patients", "icc_a1_absolute_agreement",
              "bootstrap_ci95_low", "bootstrap_ci95_high",
              "reliability_status", "rater1_median", "rater2_median")


def load_frozen_cases(path):
    with Path(path).open(encoding="utf-8", newline="") as f:
        items=list(csv.DictReader(f))
    if len(items)!=14:
        raise ValueError(f"Frozen patient manifest must be exactly 14; found {len(items)}")
    cases={}
    for row in items:
        pid=row["patient_id"]
        if pid in cases:
            raise ValueError("Duplicate patient")
        if row["segmentation_qc_status"]!="PASS_GEOMETRY_WITH_REVIEW_FLAGS":
            raise ValueError(f"Unverified index lesion for {pid}")
        if row["pv_selected_roi_pixel_qc_run"].strip()=="":
            raise ValueError(f"No selected ROI pixel QC provenance for {pid}")
        idx=int(row["representative_tumor_number"])
        if not 1<=idx<=20:raise ValueError(f"Invalid tumor label {pid}")
        cases[pid]=idx
    return cases


def absolute_agreement_icc(arr):
    """McGraw-Wong ICC(A,1), n patients x 2 raters, not ICC(C,1).

    For two-way random-effects absolute agreement:
    (MSR-MSE)/(MSR+(k-1)*MSE+k*(MSC-MSE)/n).
    Do not assume constant-feature ICC is 1 or silently drop subjects.
    """
    x=np.asarray(arr, dtype=np.float64)
    if x.ndim!=2 or x.shape[1]!=2 or x.shape[0]<3:
        raise ValueError("ICC requires >=3 independent cases and exactly 2 raters")
    if not np.isfinite(x).all():
        raise ValueError("ICC data contain nonfinite values")
    if np.max(x)-np.min(x)<1.e-12:
        raise ValueError("ICC undefined for constant feature")
    n,k=x.shape
    grand=np.mean(x)
    rows=np.mean(x,axis=1)
    cols=np.mean(x,axis=0)
    msr=k*np.sum((rows-grand)**2)/(n-1)
    msc=n*np.sum((cols-grand)**2)/(k-1)
    residual=x-rows[:,None]-cols[None,:]+grand
    mse=np.sum(residual**2)/((n-1)*(k-1))
    denom=msr+(k-1)*mse + k*(msc-mse)/n
    if denom<=0 or not np.isfinite(denom):
        raise ValueError("ICC nonpositive variance denominator")
    return float((msr-mse)/denom)


def feature_icc(rows, n_boot=300, seed=20261030):
    ids=sorted({r["patient_id"] for r in rows})
    if len(rows)!=len(ids)*2:
        raise ValueError("Exactly 2 feature rows per patient are needed")
    features=sorted(set(FEATURES_to_names()))
    values={(r["patient_id"],r["rater"]):r for r in rows}
    rng=np.random.default_rng(seed)
    output=[]
    for feat in features:
        try:
            matrix=np.array([[float(values[(pid,"rater1")][feat]),
                              float(values[(pid,"rater2")][feat])]
                             for pid in ids], dtype=np.float64)
            estimate=absolute_agreement_icc(matrix)
            boots=[]
            for _ in range(n_boot):
                ix=rng.integers(0,len(ids),size=len(ids))
                try:boots.append(absolute_agreement_icc(matrix[ix,:]))
                except ValueError:continue
            if len(boots)<max(50,n_boot//2):
                raise ValueError("Too few valid patient bootstrap estimates")
            lo,hi=np.percentile(boots,[2.5,97.5])
            level=("STRONG_PILOT" if estimate>=0.90 else
                   "RELIABLE_PILOT" if estimate>=0.75 else
                   "NOT_RELIABLE_BY_PILOT_THRESHOLD")
            output.append({
                "feature":feat,"n_patients":len(ids),
                "icc_a1_absolute_agreement":round(estimate,5),
                "bootstrap_ci95_low":round(float(lo),5),
                "bootstrap_ci95_high":round(float(hi),5),
                "reliability_status":level,
                "rater1_median":round(float(np.median(matrix[:,0])),6),
                "rater2_median":round(float(np.median(matrix[:,1])),6),
            })
        except (ValueError,KeyError) as e:
            output.append({
                "feature":feat,"n_patients":len(ids),
                "icc_a1_absolute_agreement":"","bootstrap_ci95_low":"",
                "bootstrap_ci95_high":"",
                "reliability_status":"UNESTIMABLE_"+type(e).__name__,
                "rater1_median":"","rater2_median":"",
            })
    return output


def FEATURES_to_names():
    for family, names in FEATURES.items():
        for name in names:
            yield f"original_{family}_{name}"


def make_extractor():
    from radiomics import featureextractor
    extractor=featureextractor.RadiomicsFeatureExtractor(**PARAMS)
    extractor.disableAllImageTypes()
    extractor.enableImageTypeByName("Original")
    extractor.disableAllFeatures()
    extractor.enableFeaturesByName(**FEATURES)
    return extractor


def read_member(archive,path,destination):
    """Fetch full already-compressed .nii.gz without decompressing to RAM."""
    if is_apple_sidecar(path) or path not in archive.NameToInfo:
        raise ValueError("Missing official MRI/mask archive member")
    info=archive.getinfo(path)
    data=get_member_with_ranges(ARCHIVE,info,archive.fp.total)
    destination.write_bytes(data)
    if destination.stat().st_size!=len(data):
        raise ValueError("Incomplete extracted NIfTI archive member")


def niftis_match(image_file,mask_file):
    import nibabel as nib
    img=nib.load(str(image_file))
    m=nib.load(str(mask_file))
    if len(img.shape)!=3 or img.shape!=m.shape:
        raise ValueError("Image–mask physical 3D shape mismatch")
    if corner_offset_mm(img.affine,m.affine,img.shape)>0.5:
        raise ValueError("Image–mask physical affine mismatch")
    arr=np.asanyarray(m.dataobj)
    if not np.isfinite(arr).all() or np.count_nonzero(arr)<=50:
        raise ValueError("Empty/too-small mask")
    if not np.all(np.isin(np.unique(arr),[0,1])):
        raise ValueError("Unexpected tumor mask labels")
    return [round(float(v),4) for v in np.linalg.norm(img.affine[:3,:3],axis=0)]


def selected_paths(root,tumor):
    if not root.endswith("/rater1_tumor1.nii.gz"):
        raise ValueError("Source mask inventory unexpected rater1 tumor path")
    base=root.rsplit("/",1)[0]+"/"
    return (base+"pv.nii.gz",
            base+f"rater1_tumor{tumor}.nii.gz",
            base+f"rater2_tumor{tumor}.nii.gz")


def run_case(archive,patient,root_mask_path,tumor,extractor):
    import radiomics
    if patient not in root_mask_path:
        raise ValueError("Mask patient ID mismatch")
    pv,m1,m2=selected_paths(root_mask_path,tumor)
    with tempfile.TemporaryDirectory(prefix="hcc_mri_radiomics_") as td:
        paths={}
        for label,archive_name in (("pv",pv),("rater1",m1),("rater2",m2)):
            filepath=Path(td)/(label+".nii.gz")
            read_member(archive,archive_name,filepath)
            paths[label]=filepath
        rows=[]
        for reader in ("rater1","rater2"):
            spacing=niftis_match(paths["pv"],paths[reader])
            values=extractor.execute(str(paths["pv"]),str(paths[reader]),label=1)
            feature_values={k:float(values[k]) for k in FEATURES_to_names()}
            if not all(math.isfinite(v) for v in feature_values.values()):
                raise ValueError("Non-finite extracted feature")
            rows.append({
                "patient_id":patient,"rater":reader,"selected_tumor_number":tumor,
                "source_phase":"PV","source_image":pv,
                "tumor_mask":m1 if reader=="rater1" else m2,
                "extractor_version":radiomics.__version__,
                "voxel_spacing_mm":"x".join(str(x) for x in spacing),
                "qc_status":"PASS_FEATURE_EXTRACTION","error":"",
                **feature_values,
            })
        return rows


def offline_test():
    """Pure statistics tests run without PyRadiomics installation."""
    perfect=np.array([[1.,1.],[2.,2.],[3.,3.],[4.,4.]])
    assert abs(absolute_agreement_icc(perfect)-1.)<1.e-12
    systematically_shifted=np.array([[1.,11.],[2.,12.],[3.,13.],[4.,14.]])
    assert absolute_agreement_icc(systematically_shifted)<0.75
    assert absolute_agreement_icc(np.array([[1.,2.],[1.,3.],[1.,4.]]))<1
    try:absolute_agreement_icc(np.ones((4,2)))
    except ValueError:pass
    else:raise AssertionError("Constant feature ICC must fail")
    cases=load_frozen_cases(SOURCE_CSV)
    assert len(cases)==14 and cases["TCGA-BC-A10Y"]==3
    synthetic=[]
    for i,pid in enumerate(sorted(cases)):
        for reader in ("rater1","rater2"):
            synthetic.append({"patient_id":pid,"rater":reader,**{
                f:10+i*(j+1)+(0.01 if reader=="rater2" else 0)
                for j,f in enumerate(FEATURES_to_names())}})
    f=feature_icc(synthetic,n_boot=60)
    assert len(f)==sum(len(v) for v in FEATURES.values())
    assert all(r["reliability_status"]=="STRONG_PILOT" for r in f)
    print("HCC_MRI_RADIOMICS_ICC_A1_OFFLINE_TEST_PASS")


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--offline-test",action="store_true")
    ap.add_argument("--inventory",default="artifacts/hcc_mri/tcga_liverhccseg_mri_mask_voxel_qc.csv")
    ap.add_argument("--out-dir",default="artifacts/hcc_radiomics_icc")
    ap.add_argument("--max-cases",type=int,default=2)
    ap.add_argument("--bootstrap",type=int,default=300)
    args=ap.parse_args()
    if args.offline_test:
        offline_test();return
    if not 2<=args.max_cases<=14 or not 100<=args.bootstrap<=2000:
        raise ValueError("Must request 2-14 cases and 100-2000 bootstrap replicates")
    cases=load_frozen_cases(SOURCE_CSV)
    with open(args.inventory,encoding="utf-8",newline="") as f:
        manifest=list(csv.DictReader(f))
    if len(manifest)!=14 or {x["patient_id"] for x in manifest}!=set(cases):
        raise ValueError("Unexpected 14-case source mask inventory")
    chosen=sorted(manifest,key=lambda r:r["patient_id"])[:args.max_cases]
    extractor=make_extractor()
    rows=[];errors=[]
    with ZipFile(HTTPRangeFile(ARCHIVE)) as archive:
        for item in chosen:
            pid=item["patient_id"]
            try:
                new=run_case(archive,pid,item["nifti_member_path"],
                             cases[pid],extractor)
                if len(new)!=2:raise ValueError("Need exactly two rater extractions")
                rows+=new
            except Exception as exc:
                errors.append({"patient_id":pid,
                               "type":type(exc).__name__,
                               "error":str(exc)[:250]})
    output=Path(args.out_dir)
    output.mkdir(parents=True,exist_ok=True)
    names=list(FEATURES_to_names())
    with (output/"mri_pv_two_reader_radiomics_features.csv").open(
            "w",newline="",encoding="utf-8") as f:
        writer=csv.DictWriter(f,fieldnames=(*CSV_FIELDS,*names))
        writer.writeheader()
        writer.writerows(rows)
    iccs=[]
    if not errors and len(rows)==2*len(chosen):
        iccs=feature_icc(rows,n_boot=args.bootstrap) if len(chosen)>=3 else []
    with (output/"mri_pv_feature_icc_a1.csv").open(
            "w",newline="",encoding="utf-8") as f:
        writer=csv.DictWriter(f,fieldnames=ICC_FIELDS)
        writer.writeheader()
        writer.writerows(iccs)
    counts=Counter(x.get("reliability_status") for x in iccs)
    report={
        "status":("PASS_FEATURE_EXTRACTION_AND_ICC" if not errors and iccs else
                  "PASS_TWO_CASE_EXTRACTION_PILOT_NO_ICC" if not errors else
                  "FAILED_OR_PARTIAL"),
        "generated_utc":datetime.now(timezone.utc).isoformat(),
        "patients_requested":len(chosen),"patients_extracted":len(rows)//2,
        "two_reader_feature_rows":len(rows),
        "features_extracted_per_reader":len(names),
        "icc_feature_classes":dict(counts),
        "feature_icc_pilot_thresholds":{"exploratory":0.75,"strong":0.90},
        "settings":PARAMS,"feature_whitelist":FEATURES,
        "source_phase":"PV","source_archive":ARCHIVE,
        "errors":errors,"expert_roi_review":"NOT_ASSESSED",
        "treatment_timing":"NOT_ASSESSED",
        "independent_biological_replication":"NOT_ASSESSED",
        "eligible_radiogenomics_patients":"NOT_ASSESSED",
        "notes":[
            "Even high ICC from 14 patients is not a confidence guarantee; inspect bootstrap CI and sensitivity.",
            "Original-only features, no wavelet/LoG, no geometry resampling; anisotropic MRI may distort textures.",
            "PyRadiomics fixed-bin discretization and resampling differ from some IBSI definitions.",
            "Absolute agreement ICC(A,1) for two rater masks; not patient-level biological reproducibility.",
            "Feature-rater pairs share the same MRI image; no MRI-RNA associations in this workflow."
        ],
    }
    (output/"mri_pv_feature_icc_summary.json").write_text(
        json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False))
    if errors:
        raise SystemExit(1)


if __name__=="__main__":
    main()
