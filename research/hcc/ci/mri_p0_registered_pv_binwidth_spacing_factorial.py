#!/usr/bin/env python3
"""Official registered-PV HCC radiomics 2 spacing × 3 gray level bin widths.

Outcome-blind. 14 frozen patients / 2 expert masks / 6 conditions each.
PyRadiomics 3.1.0 wheel, same settings & signed NIfTI orientation as the
provenance-audited 56-row registered source run (#41191599451).
3mm mask resampling is SimpleITK NN and image interpolation BSpline, which
must never be confused with the original authors' registered art_pv source.
"""
import argparse,csv,hashlib,json,math,tempfile
from pathlib import Path
from zipfile import ZipFile
from importlib.metadata import version
from mri_mask_voxel_audit import HTTPRangeFile
from mri_phase_mask_source_gate import frozen
from mri_p0_registered_pv_all14_sharded import case_sources
from mri_p0_raw_vs_registered_pv_radiomics_pilot import orient_to_mask
from mri_pv_pixel_overlay_audit import corner_offset_mm
from mri_pv_glcm_binwidth_spacing_factorial import make_extractor as old_maker
from zenodo_nifti_zip_inventory import ARCHIVE

SPACES=("native","3mm")
BINS=(12.5,25.0,50.0)
RATERS=("rater1","rater2")
FEATS=("original_glcm_Contrast","original_glcm_JointEntropy",
       "original_firstorder_Entropy","original_firstorder_InterquartileRange")
FROZEN_RUN="41191599451"
FIELDS=("patient_id","selected_tumor","rater","official_source_phase","source_member","source_sha256",
        "mask_member","mask_sha256","mask_affine_max_corner_mm","axis_order","axis_flips",
        "grid","bin_width","image_interpolation","mask_interpolation","extractor_dist_version",
        *FEATS,"clinical_eligibility","registered_anatomical_expert_approval","MRI_RNA_tests_executed","claim_ceiling")

def make_extractors():
    if version("pyradiomics")!="3.1.0":
        raise ValueError("PYRADIOMICS_EXACT_DISTRIBUTION_3_1_0_REQUIRED")
    out={}
    for grid in SPACES:
        for bw in BINS:
            ex=old_maker(grid,bw)
            ex.settings["geometryTolerance"]=0.5
            out[(grid,bw)]=ex
    return out

def case(archive,pid,tumor,extractors):
    import nibabel as nib
    with tempfile.TemporaryDirectory(prefix="hcc_registered_pv_factorial_") as td:
        imgs,source=case_sources(archive,pid,tumor,td)
        mask=imgs[f"rater1_tumor{tumor}"]
        registered,axes,signs=orient_to_mask(imgs["art_pv"],mask)
        if axes!=[0,1,2] or sum(s<0 for s in signs) not in (1,2):
            raise ValueError("OFFICIAL_PV_VOXEL_ORIENTATION_NOT_VERIFIED")
        source_path=Path(td)/"registered_art_pv_geometry_corrected.nii.gz"
        nib.save(registered,str(source_path))
        result=[]
        for rater in RATERS:
            key=f"{rater}_tumor{tumor}"
            m=imgs[key]
            off=corner_offset_mm(registered.affine,m.affine,m.shape)
            if m.shape!=registered.shape or off>0.5:
                raise ValueError("SOURCE_PHASE_AND_RATER_MASK_GEOMETRY_MISMATCH")
            maskpath=Path(td)/(key+"_for_extractor.nii.gz")
            nib.save(m,str(maskpath))
            for grid in SPACES:
                for bw in BINS:
                    measured=extractors[(grid,bw)].execute(str(source_path),str(maskpath),label=1)
                    values={name:float(measured[name]) for name in FEATS}
                    if not all(math.isfinite(v) for v in values.values()):
                        raise ValueError("NONFINITE_REGISTERED_SOURCE_GL_CM")
                    result.append({
                        "patient_id":pid,"selected_tumor":tumor,"rater":rater,
                        "official_source_phase":"reoriented_art_pv",
                        "source_member":source["art_pv"]["member"],
                        "source_sha256":source["art_pv"]["sha256"],
                        "mask_member":source[key]["member"],"mask_sha256":source[key]["sha256"],
                        "mask_affine_max_corner_mm":round(off,6),
                        "axis_order":";".join(map(str,axes)),
                        "axis_flips":";".join(map(str,signs)),
                        "grid":grid,"bin_width":bw,
                        "image_interpolation":"NONE" if grid=="native" else "sitkBSpline",
                        "mask_interpolation":"NONE" if grid=="native" else "NEAREST_NEIGHBOR",
                        "extractor_dist_version":"pyradiomics==3.1.0",
                        **values,
                        "clinical_eligibility":"NOT_ASSESSED",
                        "registered_anatomical_expert_approval":"NOT_ASSESSED",
                        "MRI_RNA_tests_executed":"NO","claim_ceiling":"S0"})
        if len(result)!=12:raise ValueError("EXPECTED_12_ROWS_PER_PATIENT")
        print("HCC_REGISTERED_FACTORIAL_SOURCE_CASE_PASS",pid,flush=True)
        return result

def verify(rows,index):
    ids=sorted(frozen())[2*index:2*index+2]
    if len(ids)!=2 or len(rows)!=24:
        raise ValueError("TWO_PATIENT_SHARD_REQUIRES_24_ROWS")
    keys={(p,r,g,float(b)) for p in ids for r in RATERS for g in SPACES for b in BINS}
    actual={(r["patient_id"],r["rater"],r["grid"],float(r["bin_width"])) for r in rows}
    if len(actual)!=len(rows) or keys!=actual:
        raise ValueError("MISSING_OR_DUPLICATE_REGISTERED_FACTORIAL_CELLS")
    if any(int(r["selected_tumor"])!=frozen()[r["patient_id"]] or
           r["official_source_phase"]!="reoriented_art_pv" or
           r["clinical_eligibility"]!="NOT_ASSESSED" or
           r["registered_anatomical_expert_approval"]!="NOT_ASSESSED" or
           r["MRI_RNA_tests_executed"]!="NO" or r["claim_ceiling"]!="S0"
           or float(r["mask_affine_max_corner_mm"])>0.5 for r in rows):
        raise ValueError("FROZEN_ROI_GEOMETRY_OR_CLINICAL_HOLD_CHANGED")
    if any(not math.isfinite(float(r[f])) for r in rows for f in FEATS):
        raise ValueError("NONFINITE_FEATURE")
    for pid in ids:
        for rater in RATERS:
            subset=[r for r in rows if r["patient_id"]==pid and r["rater"]==rater]
            if len({r["source_sha256"] for r in subset})!=1 or len({r["mask_sha256"] for r in subset})!=1:
                raise ValueError("CHANGING_NIFTI_WITHIN_FACTORIZATION")
    return ids

def offline():
    assert len(frozen())==14 and frozen()["TCGA-BC-A10Y"]==3
    assert len(SPACES)*len(BINS)==6 and len(FEATS)==4
    good=[]
    for pid in sorted(frozen())[:2]:
        for r in RATERS:
            for grid in SPACES:
                for bw in BINS:
                    good.append({k:(1.0 if k in FEATS else "") for k in FIELDS} | {
                        "patient_id":pid,"selected_tumor":frozen()[pid],
                        "rater":r,"grid":grid,"bin_width":bw,"official_source_phase":"reoriented_art_pv",
                        "source_sha256":"0"*64,"mask_sha256":"1"*64,"mask_affine_max_corner_mm":0.,
                        "clinical_eligibility":"NOT_ASSESSED",
                        "registered_anatomical_expert_approval":"NOT_ASSESSED",
                        "MRI_RNA_tests_executed":"NO","claim_ceiling":"S0"})
    verify(good,0)
    bad=[dict(x) for x in good];bad[0]["clinical_eligibility"]="YES"
    try:verify(bad,0)
    except ValueError:pass
    else:raise AssertionError("CLINICAL_GATE_MUST_FAIL_CLOSED")
    print("HCC_REGISTERED_PV_FACTORIAL_14_PATIENT_7_SHARD_2x3_OFFLINE_PASS")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--offline-test",action="store_true")
    p.add_argument("--shard",type=int)
    p.add_argument("--out-dir",default="artifacts/hcc_registered_factorial")
    a=p.parse_args()
    if a.offline_test:return offline()
    if a.shard is None or a.shard not in range(7):
        raise ValueError("EXPECTED_SEVEN_FROZEN_2_CASE_SHARDS")
    cohort=frozen()
    ids=sorted(cohort)[2*a.shard:2*a.shard+2]
    ex=make_extractors();allrows=[]
    with ZipFile(HTTPRangeFile(ARCHIVE)) as archive:
        for pid in ids:
            allrows.extend(case(archive,pid,cohort[pid],ex))
    verify(allrows,a.shard)
    dest=Path(a.out_dir);dest.mkdir(parents=True,exist_ok=True)
    with (dest/f"hcc_registered_factorial_shard_{a.shard}.csv").open("w",newline="",encoding="utf8") as o:
        w=csv.DictWriter(o,fieldnames=FIELDS);w.writeheader();w.writerows(allrows)
    info={"shard":a.shard,"source":"https://zenodo.org/records/8179129",
          "official_phase":"reoriented_art_pv","patients":ids,"rows":len(allrows),
          "param_grid":list(SPACES),"bin_widths":list(BINS),"feature_names":list(FEATS),
          "pyradiomics_distribution":"3.1.0","clinical_eligible_n":"NOT_ASSESSED",
          "locked_MRI_RNA_tests":"NOT_EXECUTED","claim_ceiling":"S0"}
    (dest/f"hcc_registered_factorial_shard_{a.shard}.json").write_text(json.dumps(info,indent=2)+"\n")
    print("HCC_REGISTERED_PV_FACTORIAL_SHARD_COMPLETE",a.shard,len(allrows),flush=True)
if __name__=="__main__":main()
