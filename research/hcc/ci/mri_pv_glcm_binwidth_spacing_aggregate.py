#!/usr/bin/env python3
"""Reduce the outcome-blind 2 spacing × 3 binWidth GLCM experiment.

Baseline for binWidth=25 both native and 3mm must reproduce frozen
reader ICC (A,1) before the factorial result may PASS. All cases retained.
"""
import argparse,csv,json,math,statistics
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
from mri_pv_glcm_binwidth_spacing_factorial import (
    FEATURE_KEYS,SPACING,BINWIDTH,RATERS,validate
)
from mri_pv_3mm_resampling_aggregate import rho,relative
from mri_pv_pyradiomics_rater_icc import absolute_agreement_icc

BASE="research/hcc/HCC_MRI_PV_14X2_NATIVE_VS_3MM_FEATURE_REPRODUCIBILITY_20261031.csv"
CASES="research/hcc/HCC_MRI_14_PREOUTCOME_INDEX_LESION_SELECTION_20261030.csv"
CASE_COLS=("patient_id","rater","feature",
    "native_binwidth12_5","native_binwidth25","native_binwidth50",
    "isotropic3mm_binwidth12_5","isotropic3mm_binwidth25","isotropic3mm_binwidth50",
    "binwidth12_5_vs25_native_abs_relative",
    "binwidth50_vs25_native_abs_relative",
    "binwidth12_5_vs25_3mm_abs_relative",
    "binwidth50_vs25_3mm_abs_relative",
    "3mm_vs_native_at25_abs_relative",
    "clinical_eligibility")
METRIC_COLS=("feature","spacing_condition","binwidth",
    "reader_icc_a1","patient_rater_values","case_mean_rank_rho_vs_binwidth25",
    "median_abs_relative_vs_binwidth25_same_spacing",
    "median_abs_relative_vs_native25",
    "max_abs_relative_vs_native25",
    "largest_change_patient","baseline_frozen_icc_reproduced")

def read(path):
    with Path(path).open(encoding="utf-8",newline="") as f:
        return list(csv.DictReader(f))

def summarize(rows):
    cases=read(CASES)
    ids=sorted({c["patient_id"] for c in cases})
    if len(ids)!=14 or len(rows)!=168:
        raise ValueError("Factorial must have 14×2×2×3=168 extracted rows")
    samples={}
    for r in rows:
        key=(r["patient_id"],r["rater"],r["spacing_condition"],float(r["bin_width"]))
        if key in samples:raise ValueError("Duplicate extraction")
        if r["patient_id"] not in ids or r["clinical_eligibility"]!="HOLD_UNRESOLVED_NOT_EXCLUDED":
            raise ValueError("Clinical eligibility / cohort not frozen")
        samples[key]=r
    expected={(pid,reader,space,bw) for pid in ids for reader in RATERS
                for space in SPACING for bw in BINWIDTH}
    if set(samples)!=expected:raise ValueError("Incomplete patient-reader-factorial")
    frozen={x["feature"]:x for x in read(BASE)}
    if not set(FEATURE_KEYS).issubset(frozen):
        raise ValueError("Missing frozen reference values")
    metric=[];patient=[]
    for feat in FEATURE_KEYS:
        def get(pid,reader,space,bw):
            v=float(samples[(pid,reader,space,bw)][feat])
            if not math.isfinite(v):raise ValueError("Nonfinite GLCM value")
            return v
        for space in SPACING:
            for bw in BINWIDTH:
                arr=np.array([[get(pid,r,space,bw) for r in RATERS] for pid in ids],float)
                icc=absolute_agreement_icc(arr)
                reference_key=("native_icc_a1" if space=="native" else "resampled_3mm_icc_a1")
                baseline_ok="NOT_BASELINE"
                if bw==25.:
                    target=float(frozen[feat][reference_key])
                    if abs(icc-target)>0.003:
                        raise ValueError(f"Native/original GLCM source drift: {feat} {space} {icc} vs {target}")
                    baseline_ok="YES"
                refarr=np.array([[get(pid,r,space,25.) for r in RATERS] for pid in ids],float)
                orig=np.array([[get(pid,r,"native",25.) for r in RATERS] for pid in ids],float)
                rank=rho(arr.mean(axis=1),refarr.mean(axis=1))
                baseline_rels=[relative(float(refarr[i,j]),float(arr[i,j]))
                               for i in range(14) for j in range(2)]
                orig_rels=[relative(float(orig[i,j]),float(arr[i,j]))
                           for i in range(14) for j in range(2)]
                imax=np.unravel_index(np.argmax(np.array([
                  [relative(float(orig[i,j]),float(arr[i,j])) for j in range(2)]
                  for i in range(14)])),(14,2))[0]
                metric.append({
                  "feature":feat,"spacing_condition":space,"binwidth":bw,
                  "reader_icc_a1":round(icc,6),
                  "patient_rater_values":28,
                  "case_mean_rank_rho_vs_binwidth25":"" if rank is None else round(rank,6),
                  "median_abs_relative_vs_binwidth25_same_spacing":round(statistics.median(baseline_rels),6),
                  "median_abs_relative_vs_native25":round(statistics.median(orig_rels),6),
                  "max_abs_relative_vs_native25":round(max(orig_rels),6),
                  "largest_change_patient":ids[imax],
                  "baseline_frozen_icc_reproduced":baseline_ok,
                })
        for pid in ids:
            for reader in RATERS:
                dic={
                  "patient_id":pid,"rater":reader,"feature":feat,
                  "clinical_eligibility":"HOLD_UNRESOLVED_NOT_EXCLUDED"
                }
                for space,prefix in (("native","native"),("3mm","isotropic3mm")):
                    for bw,suffix in ((12.5,"12_5"),(25.,"25"),(50.,"50")):
                        dic[prefix+"_binwidth"+suffix]=round(get(pid,reader,space,bw),9)
                    dic["binwidth12_5_vs25_"+("native" if space=="native" else "3mm")+"_abs_relative"]=round(relative(get(pid,reader,space,25.),get(pid,reader,space,12.5)),6)
                    dic["binwidth50_vs25_"+("native" if space=="native" else "3mm")+"_abs_relative"]=round(relative(get(pid,reader,space,25.),get(pid,reader,space,50.)),6)
                dic["3mm_vs_native_at25_abs_relative"]=round(relative(get(pid,reader,"native",25.),get(pid,reader,"3mm",25.)),6)
                patient.append(dic)
    results={
      "status":"PASS_GLCM_2x3_14_CASE_2_READER_FACTORIAL_BASELINE_REPRODUCED",
      "checked_utc":datetime.now(timezone.utc).isoformat(),
      "frozen_technical_patients":14,
      "reader_profiles":28,"factorial_cells":168,
      "unique_feature_names":len(FEATURE_KEYS),"reference_binwidth":25.,
      "binwidth_values":BINWIDTH,"voxel_conditions":SPACING,
      "baseline_icc_25_native_and_3mm_reproduced":sum(x["baseline_frozen_icc_reproduced"]=="YES" for x in metric),
      "glcm_contrast_native_25_median_absolute_shift_vs_3mm25":next(x["median_abs_relative_vs_native25"] for x in metric if x["feature"]=="original_glcm_Contrast" and x["spacing_condition"]=="3mm" and x["binwidth"]==25.),
      "no_automatic_patient_exclusions":True,
      "clinical_eligible_n":"NOT_ASSESSED",
      "radiologist_lesion_review":"NOT_ASSESSED",
      "MRI_RNA_pair_specific_timing":"NOT_VERIFIED",
      "original_12_mri_rna_hypotheses_executed":False,
      "ibsi_phantom_full_agreement":"NOT_TESTED",
      "claim_ceiling":"S0",
      "note":"Binning and voxel grid jointly influence GLCM; comparisons within fixed grid isolate binWidth effects. 2×3 sensitivity is not IBSI phantom certification or cross-scanner evidence."
    }
    if results["baseline_icc_25_native_and_3mm_reproduced"]!=2*len(FEATURE_KEYS):
        raise ValueError("Incomplete original ICC reproduction")
    return metric,patient,results

def offline_test():
    assert len(SPACING)*len(BINWIDTH)==6
    assert len(FEATURE_KEYS)==4
    assert abs(rho([1,2,3,4],[4,3,2,1])+1)<1e-12
    assert abs(relative(2,4)-1.0)<1e-12
    print("HCC_GLCM_FACTORIAL_2X3_AGGREGATOR_OFFLINE_PASS")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--offline-test",action="store_true")
    ap.add_argument("--shard-dir",default="artifacts/hcc_glcm_factorial")
    ap.add_argument("--out-dir",default="artifacts/hcc_glcm_factorial_summary")
    a=ap.parse_args()
    if a.offline_test:return offline_test()
    rows=[]
    for shard in (0,1):
        f=Path(a.shard_dir)/f"shard{shard}"/f"glcm_bin_spacing_shard{shard}.csv"
        part=read(f)
        ids=sorted({r["patient_id"] for r in part})
        if len(ids)!=7 or len(part)!=84:
            raise ValueError("Incomplete patient shard "+str(shard))
        rows.extend(part)
    metric,patient,result=summarize(rows)
    target=Path(a.out_dir);target.mkdir(parents=True,exist_ok=True)
    for name,data,columns in (
       ("hcc_glcm_14x2_2x3_case_feature_grid.csv",patient,CASE_COLS),
       ("hcc_glcm_2x3_reader_icc_and_rank_summary.csv",metric,METRIC_COLS)
    ):
        with (target/name).open("w",encoding="utf-8",newline="") as f:
            writer=csv.DictWriter(f,fieldnames=columns)
            writer.writeheader();writer.writerows(data)
    (target/"hcc_glcm_2x3_factorial_summary.json").write_text(
        json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False))
if __name__=="__main__":main()
