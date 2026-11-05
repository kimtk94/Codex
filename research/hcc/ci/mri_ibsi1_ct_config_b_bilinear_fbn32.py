#!/usr/bin/env python3
"""IBSI-1 CT configuration B: an explicitly REVIEW-capable bilinear+FBN32 pilot.

Official docs: https://ibsi.readthedocs.io/en/master/05_Reference_data_sets.html
             https://ibsi.readthedocs.io/en/master/02_Image_processing.html
             https://ibsi.readthedocs.io/en/master/03_Image_features.html
No raw or resampled CT voxels are uploaded, only non-identifying QC metrics.
NOTE: independent GLCM math and PyRadiomics share one SimpleITK interpolation
implementation here. This is NOT an independent interpolation validation.
"""
import argparse
import json
import math
from pathlib import Path
from datetime import datetime, timezone
import mri_ibsi1_ct_config_a_benchmark as ca

REF_B = {
    "Mean": (11.5,1.1,"Q4LE"),
    "Median": (45.,.3,"Y12H"),
    "InterquartileRange": (52.,.5,"SALO"),
    "GLCM_2D_averaged_Contrast": (11.9,.1,"ACUI"),
    "GLCM_2_5D_direction_merged_Contrast": (8.66,.09,"ACUI"),
}
EXPECTED_SIZE = (100, 99, 60)
SOURCE_DOC = "https://ibsi.readthedocs.io/en/master/03_Image_features.html"

def preflight(src):
    import SimpleITK as sitk
    import numpy as np
    image_path,mask_path = ca.source_paths(src)
    image = sitk.ReadImage(str(image_path))
    mask = sitk.ReadImage(str(mask_path))
    if tuple(image.GetSize()) != (204,201,60):
        raise ValueError("Original image size mismatch")
    if (tuple(image.GetSize()) != tuple(mask.GetSize())
        or not np.allclose(image.GetDirection(),mask.GetDirection(),atol=1e-5)
        or not np.allclose(image.GetOrigin(),mask.GetOrigin(),atol=1e-4)
        or not np.allclose(image.GetSpacing(),mask.GetSpacing(),atol=1e-4)):
        raise ValueError("Original source image/mask geometry mismatch")
    # IBSI recommends initial NIfTI image rounding before interpolation.
    original_array = np.rint(sitk.GetArrayFromImage(image).astype(np.float32))
    rounded = sitk.GetImageFromArray(original_array.astype(np.float32))
    rounded.CopyInformation(image)
    original_mask = sitk.GetArrayFromImage(mask) > 0
    if int(original_mask.sum()) != 125256:
        raise ValueError("Invalid original source GTV count")
    src_mask = sitk.GetImageFromArray(original_mask.astype(np.float32))
    src_mask.CopyInformation(mask)
    return rounded, src_mask

def grid_parameters(image):
    import numpy as np
    native_size = np.array(image.GetSize(),dtype=np.float64)
    native_spacing = np.array(image.GetSpacing(),dtype=np.float64)
    target_spacing = np.array([2.,2.,native_spacing[2]])
    target_size = np.ceil(native_size * native_spacing / target_spacing).astype(int)
    if tuple(target_size) != EXPECTED_SIZE:
        raise ValueError(f"Official B grid expected {EXPECTED_SIZE}, got {target_size}")
    direction = np.array(image.GetDirection(),dtype=np.float64).reshape(3,3)
    center = np.array(image.GetOrigin()) + direction @ ((native_size-1)*native_spacing/2)
    target_origin = center-direction @ ((target_size-1)*target_spacing/2)
    return tuple(int(v) for v in target_size), tuple(float(v) for v in target_spacing), tuple(float(v) for v in target_origin)

def preprocess(repo):
    import SimpleITK as sitk
    import numpy as np
    image, mask = preflight(repo)
    size,spacing,origin = grid_parameters(image)
    def resample(source, default):
        res=sitk.ResampleImageFilter()
        res.SetSize(list(size))
        res.SetOutputSpacing(list(spacing))
        res.SetOutputOrigin(list(origin))
        res.SetOutputDirection(image.GetDirection())
        res.SetTransform(sitk.Transform(3,sitk.sitkIdentity))
        res.SetInterpolator(sitk.sitkLinear)
        res.SetDefaultPixelValue(default)
        res.SetOutputPixelType(sitk.sitkFloat32)
        return res.Execute(source)
    res_im=resample(image,-1000.)
    res_mask=resample(mask,0.)
    # IBSI B: image nearest integer rounding after resampling;
    # partial ROI >= 0.5 (NOT nearest-neighbour binary resampling).
    values=np.rint(sitk.GetArrayFromImage(res_im)).astype(np.float32)
    fractional=np.asarray(sitk.GetArrayFromImage(res_mask),dtype=np.float32)
    morphological=fractional>=.5
    intensity=morphological & (values>=-500.) & (values<=400.)
    if intensity.sum()<1000:
        raise ValueError("Bad B interpolated intensity ROI")
    roi_vals=values[intensity]
    vmin=float(roi_vals.min())
    vmax=float(roi_vals.max())
    if vmax<=vmin:
        raise ValueError("Bad FBN dynamic range")
    bins=np.zeros_like(values,dtype=np.uint8)
    b=np.floor(32.0*(roi_vals-vmin)/(vmax-vmin)).astype(np.int64)+1
    b=np.clip(b,1,32)
    bins[intensity]=b.astype(np.uint8)
    if int(bins[intensity].min()) != 1 or int(bins[intensity].max()) != 32:
        raise ValueError("FBN32 bins not spanning 1..32")
    qc={
        "source_original_size_xyz":[204,201,60],
        "resampled_size_xyz":list(size),
        "resampled_spacing_mm":list(spacing),
        "resampled_origin_xyz_mm":list(origin),
        "image_resample":"SimpleITK bilinear in axial planes",
        "mask_resample":"SimpleITK bilinear >=0.5",
        "interpolation_validation":"SINGLE_IMPLEMENTATION_NOT_INDEPENDENT",
        "morphological_voxels":int(morphological.sum()),
        "intensity_roi_voxels":int(intensity.sum()),
        "image_rounding":"before and after interpolation nearest integer",
        "intensity_range_hu":[float(vmin),float(vmax)],
        "FBN":"32 bins actual resegmented ROI minimum and maximum, not HU window",
        "FBN_min":int(bins[intensity].min()),
        "FBN_max":int(bins[intensity].max()),
        "HU_min_resegmentation":-500,
        "HU_max_resegmentation":400,
    }
    return values,bins,intensity,qc,image,origin,spacing

def independently_measure(repo):
    import numpy as np
    val,bins,mask,qc,*_=preprocess(repo)
    v=val[mask].astype(np.float64)
    # Previous independent 2D-avg and 2.5D-dmrg implementation expects x,y,z.
    matrices=ca.glcm_two_aggregations(
        np.transpose(bins,(2,1,0)),np.transpose(mask,(2,1,0)))
    return {
        "Mean":float(np.mean(v)),"Median":float(np.median(v)),
        "InterquartileRange":float(np.percentile(v,75)-np.percentile(v,25)),
        "GLCM_2D_averaged_Contrast":matrices["GLCM_2D_averaged_Contrast"],
        "GLCM_2_5D_direction_merged_Contrast":matrices["GLCM_2_5D_direction_merged_Contrast"],
    },qc

def pyradiomics_measure(repo):
    import numpy as np
    import SimpleITK as sitk
    import radiomics
    from radiomics import featureextractor
    if radiomics.__version__.lstrip("v") != "3.1.0":
        raise ValueError("PyRadiomics version unpinned")
    values,bins,intensity,qc,source,origin,spacing=preprocess(repo)
    def make_img(array):
        out=sitk.GetImageFromArray(array)
        out.SetSpacing(tuple(spacing))
        out.SetOrigin(tuple(origin))
        out.SetDirection(source.GetDirection())
        return out
    m=make_img(intensity.astype(np.uint8))
    def run(img,features):
        x=featureextractor.RadiomicsFeatureExtractor(
            binWidth=1, normalize=False, resampledPixelSpacing=None,
            interpolator=None, force2D=True, force2Ddimension=0,
            weightingNorm=None, distances=[1], minimumROIDimensions=2,
            correctMask=False)
        x.disableAllImageTypes();x.enableImageTypeByName("Original")
        x.disableAllFeatures()
        x.enableFeaturesByName(**features)
        return x.execute(img,m,label=1)
    first=run(make_img(values.astype(np.float32)),
              {"firstorder":["Mean","Median","InterquartileRange"]})
    glcm=run(make_img(bins.astype(np.float32)),{"glcm":["Contrast"]})
    measured={
        "Mean":float(first["original_firstorder_Mean"]),
        "Median":float(first["original_firstorder_Median"]),
        "InterquartileRange":float(first["original_firstorder_InterquartileRange"]),
        "GLCM_2_5D_direction_merged_Contrast":float(glcm["original_glcm_Contrast"])
    }
    qc["software"]="PyRadiomics "+radiomics.__version__
    qc["FBN_method"]="Explicit preprocessing FBN32 into 1..32 before PyRadiomics binWidth1; no native FBN option"
    qc["GLCM_aggregation"]="2.5D direction merged (NOT 2D avg)"
    return measured,qc

def comparisons(measured):
    rows=[]
    for name,value in measured.items():
        reference,tol,code=REF_B[name]
        if not math.isfinite(value):
            raise ValueError("Non-finite CT B benchmark")
        rows.append({"feature":name,"IBSI_code":code,"reference":reference,
                     "observed":value,"absolute_difference":abs(value-reference),
                     "tolerance":tol,"tolerance_provenance":"IBSI_OFFICIAL",
                     "status":"PASS" if abs(value-reference)<=tol else "REVIEW_REFERENCE_DEVIATION",
                     "reference_source":SOURCE_DOC})
    return rows

def execute(mode,repo):
    measured,qc=(independently_measure(repo) if mode=="independent"
                 else pyradiomics_measure(repo))
    rows=comparisons(measured)
    return {"mode":mode, "status":"PASS_REFERENCE_COMPARISONS" if
           all(x["status"]=="PASS" for x in rows) else "REVIEW_B_PREPROCESSING_OR_AGGREGATION",
           "configuration":"IBSI1_CT_Patient_PAT1_CONFIG_B",
           "source_commit":ca.SOURCE_SHA,
           "image_sha256":ca.CT_IMG_SHA,"mask_sha256":ca.CT_MASK_SHA,
           "diagnostics":qc,"comparisons":rows,"HCC18":"PARTIAL",
           "HCC20":"PENDING","claim_ceiling":"S0",
           "IBSI_2_CT_filtered":"NOT_EXECUTED",
           "generated_utc":datetime.now(timezone.utc).isoformat()}

def join(a,b):
    expected={"independent":set(REF_B),
              "pyradiomics":set(REF_B)-{"GLCM_2D_averaged_Contrast"}}
    for d in (a,b):
        if d["mode"] not in expected or d["source_commit"]!=ca.SOURCE_SHA:
            raise ValueError("Wrong source or mode")
        if d["image_sha256"]!=ca.CT_IMG_SHA or d["mask_sha256"]!=ca.CT_MASK_SHA:
            raise ValueError("Source drift in B results")
        if {x["feature"] for x in d["comparisons"]}!=expected[d["mode"]]:
            raise ValueError("Missing official B references")
        if d["HCC18"]!="PARTIAL" or d["HCC20"]!="PENDING":
            raise ValueError("Clinical claims changed")
    if a["mode"]!="independent" or b["mode"]!="pyradiomics":
        raise ValueError("Incorrect join order")
    keys=["resampled_size_xyz","morphological_voxels","intensity_roi_voxels",
          "intensity_range_hu"]
    matching=all(a["diagnostics"][k]==b["diagnostics"][k] for k in keys)
    aa={r["feature"]:r for r in a["comparisons"]}
    bb={r["feature"]:r for r in b["comparisons"]}
    discrepancy=abs(aa["GLCM_2_5D_direction_merged_Contrast"]["observed"]-
                    bb["GLCM_2_5D_direction_merged_Contrast"]["observed"])
    # Diagnostic local threshold separate from published IBSI tolerances.
    cross_ok=discrepancy<1e-5
    success=a["status"]=="PASS_REFERENCE_COMPARISONS" and b["status"]=="PASS_REFERENCE_COMPARISONS" and matching and cross_ok
    return {"status":"PASS_CT_B_INTERPOLATION_FBN32_FEATURE_REFERENCES" if success
            else "REVIEW_CT_B_INTERPOLATION_FBN32_REFERENCE_MISMATCH",
            "matched_preprocessing_diagnostics":matching,
            "PyRadiomics_extraction_reproduces_2D_avg":False,
            "independent_reference_matched":sum(x["status"]=="PASS" for x in a["comparisons"]),
            "pyradiomics_reference_matched":sum(x["status"]=="PASS" for x in b["comparisons"]),
            "cross_software_2_5D_contrast_absolute_difference":discrepancy,
            "local_cross_tool_tolerance_not_IBSI":1e-5,
            "preprocessing_comparison":"SHARED_SIMPLEITK_SINGLE_RESAMPLER",
            "clinical_HCC_evidence":"NOT_ASSESSED",
            "HCC18":"PARTIAL","HCC20":"PENDING","claim_ceiling":"S0",
            "IBSI_CT_C_D_E":"NOT_EXECUTED",
            "IBSI2_filtered":"NOT_EXECUTED"}

def test():
    assert len(REF_B)==5
    assert REF_B["GLCM_2D_averaged_Contrast"][:2]==(11.9,.1)
    assert REF_B["GLCM_2_5D_direction_merged_Contrast"][:2]==(8.66,.09)
    assert comparisons({"Mean":11.5})[0]["status"]=="PASS"
    assert comparisons({"Mean":15})[0]["status"]=="REVIEW_REFERENCE_DEVIATION"
    print("IBSI_CT_B_FBN32_AND_REVIEW_OFFLINE_PASS")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--mode",choices=["independent","pyradiomics","join","offline-test"],required=True)
    p.add_argument("--source-dir",default="artifacts/ibsi_original_repo")
    p.add_argument("--out-dir",default="artifacts/hcc_ibsi_ct_b")
    p.add_argument("--independent",default="artifacts/hcc_ibsi_ct_b_independent/ct_b.json")
    p.add_argument("--pyradiomics",default="artifacts/hcc_ibsi_ct_b_pyradiomics/ct_b.json")
    a=p.parse_args()
    if a.mode=="offline-test":
        test();return
    if a.mode=="join":
        result=join(json.loads(Path(a.independent).read_text()),
                    json.loads(Path(a.pyradiomics).read_text()))
    else:
        result=execute(a.mode,a.source_dir)
    out=Path(a.out_dir);out.mkdir(parents=True,exist_ok=True)
    (out/"ct_b.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps(result,ensure_ascii=False))
    # Preserve REVIEW in the JSON and Action summary even when the job itself completes.

if __name__=="__main__":
    main()
