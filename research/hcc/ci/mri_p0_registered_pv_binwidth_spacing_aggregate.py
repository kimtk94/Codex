#!/usr/bin/env python3
"""Aggregate official registered-PV 14-patient binWidth×voxel-space factorial.

Require immutable 56-row registered native bw25 reference (SHA256-pinned)
before aggregating any unblinded source-only imaging measurement statistics.
"""
import argparse,csv,io,json,math,statistics,zipfile
from pathlib import Path
import numpy as np
from mri_phase_mask_source_gate import frozen
from mri_p0_frozen_source_results_qc import audit as verify_original
from mri_pv_pyradiomics_rater_icc import absolute_agreement_icc
from mri_p0_registered_pv_binwidth_spacing_factorial import (
 SPACES,BINS,RATERS,FEATS,verify
)

METRIC_FIELDS=("feature","grid","bin_width","reference_condition","n_independent_patients",
  "n_reader_measurements","reader_icc_A1","median_abs_change_pct_vs_native25",
  "median_signed_change_pct_vs_native25","median_abs_change_pct_vs_same_grid25",
  "patient_mean_rank_rho_vs_native25","patient_mean_rank_rho_vs_same_grid25",
  "n_patients_abs_change_ge_10pct_vs_native25",
  "n_patients_abs_change_ge_20pct_vs_native25",
  "source_baseline_registered_native25_confirmed","MRI_RNA_tests_executed","claim_ceiling")
PATIENT_FIELDS=("patient_id","feature","rater","native12_5","native25","native50",
 "3mm12_5","3mm25","3mm50","registered_3mm_vs_native25_signed_change_pct",
 "registered_3mm_vs_native25_abs_change_pct",
 "registered_native12_5_vs_native25_abs_change_pct",
 "registered_native50_vs_native25_abs_change_pct",
 "clinical_eligibility","MRI_RNA_tests_executed","claim_ceiling")

def read(p):
    with p.open(newline="",encoding="utf8") as f:return list(csv.DictReader(f))

def rho(x,y):
    # Tied ranks correctly averaged; this does not use molecular outcomes.
    def ranks(vals):
        a=np.asarray(vals,dtype=float)
        order=np.argsort(a,kind="stable");out=np.empty(len(a))
        j=0
        while j<len(a):
            k=j+1
            while k<len(a) and a[order[k]]==a[order[j]]:k+=1
            out[order[j:k]]=(j+k+1)/2
            j=k
        return out
    a,b=ranks(x),ranks(y)
    if np.ptp(a)<1e-12 or np.ptp(b)<1e-12:return None
    return round(float(np.corrcoef(a,b)[0,1]),6)

def relative_percent(x,ref):
    original=np.asarray(ref,dtype=float)
    a=np.asarray(x,dtype=float)
    if np.any(np.abs(original)<=1e-12):
        raise ValueError("UNDEFINED_PATIENT_AVERAGE_RELATIVE_BASELINE")
    return (a-original)/np.abs(original)*100.

def load_shards(base):
    out=[]
    for shard in range(7):
        csvfile=base/f"hcc_registered_factorial_shard_{shard}.csv"
        jsonfile=base/f"hcc_registered_factorial_shard_{shard}.json"
        part=read(csvfile)
        ids=verify(part,shard)
        info=json.loads(jsonfile.read_text())
        if (info["shard"]!=shard or info["patients"]!=ids or info["rows"]!=24
            or info["claim_ceiling"]!="S0" or info["locked_MRI_RNA_tests"]!="NOT_EXECUTED"
            or info["official_phase"]!="reoriented_art_pv"
            or info["pyradiomics_distribution"]!="3.1.0"):
            raise ValueError("SOURCE_SHARD_MANIFEST_OR_SCIENTIFIC_STATUS_DRIFT")
        out+=part
    ids=sorted(frozen())
    keys={(r["patient_id"],r["rater"],r["grid"],float(r["bin_width"])) for r in out}
    expected={(p,r,g,float(b)) for p in ids for r in RATERS for g in SPACES for b in BINS}
    if len(out)!=168 or len(keys)!=168 or keys!=expected:
        raise ValueError("FACTORIAL_ALL14_168_COMPLETE_ROWS_REQUIRED")
    for pid in ids:
        for rater in RATERS:
            rows=[r for r in out if r["patient_id"]==pid and r["rater"]==rater]
            if len({x["mask_sha256"] for x in rows})!=1:
                raise ValueError("ROI_CHANGED_WITHIN_FACTORIAL")
            if len({x["source_sha256"] for x in rows})!=1:
                raise ValueError("REGISTERED_SOURCE_CHANGED_WITHIN_FACTORIAL")
    return out

def reference_from_zip(source):
    verify_original(source)
    with zipfile.ZipFile(source) as z:
        records=list(csv.DictReader(io.StringIO(
           z.read("hcc_mri14_raw_vs_registered_pv_all_features.csv").decode("utf8"))))
    return {(r["patient_id"],r["rater"]):r for r in records if r["phase"]=="reoriented_art_pv"}

def compare_to_previous(rows,original):
    comparisons=0
    for x in rows:
        if x["grid"]!="native" or float(x["bin_width"])!=25:continue
        y=original[(x["patient_id"],x["rater"])]
        for f in FEATS:
            got=float(x[f]);previous=float(y[f])
            # 1e-5 relative accommodates pinned reference float CSV printing,
            # not arbitrary scientific changes; source/ROI SHA must be exact.
            if abs(got-previous)>max(0.00003,abs(previous)*0.00001):
                raise ValueError("OFFICIAL_REGISTERED_NATIVE_BW25_BASELINE_NOT_REPRODUCED:"+f)
            comparisons+=1
        if x["source_sha256"]!=y["source_sha256"] or x["mask_sha256"]!=y["mask_sha256"]:
            raise ValueError("SOURCE_IMAGE_OR_EXPERT_MASK_SHA_CHANGED")
    if comparisons!=14*2*len(FEATS):
        raise ValueError("MISSING_112_REGISTERED_NATIVE25_BASELINE_COMPARISONS")
    return comparisons

def summarize(rows,source_reference):
    confirmed=compare_to_previous(rows,source_reference)
    ids=sorted(frozen())
    by={(r["patient_id"],r["rater"],r["grid"],float(r["bin_width"])):r for r in rows}
    metrics=[];profiles=[]
    def v(pid,rater,grid,bw,feat):
        return float(by[(pid,rater,grid,float(bw))][feat])
    for feature in FEATS:
        native=np.array([np.mean([v(pid,r,"native",25.,feature) for r in RATERS]) for pid in ids])
        for grid in SPACES:
            baseline=np.array([np.mean([v(pid,r,grid,25.,feature) for r in RATERS]) for pid in ids])
            for bw in BINS:
                matrix=np.array([[v(pid,r,grid,bw,feature) for r in RATERS] for pid in ids])
                current=matrix.mean(axis=1)
                delta_native=relative_percent(current,native)
                delta_same=relative_percent(current,baseline)
                metrics.append({
                   "feature":feature,"grid":grid,"bin_width":bw,
                   "reference_condition":"official_registered_pv_native_bw25",
                   "n_independent_patients":14,"n_reader_measurements":28,
                   "reader_icc_A1":round(absolute_agreement_icc(matrix),6),
                   "median_abs_change_pct_vs_native25":round(float(np.median(np.abs(delta_native))),6),
                   "median_signed_change_pct_vs_native25":round(float(np.median(delta_native)),6),
                   "median_abs_change_pct_vs_same_grid25":round(float(np.median(np.abs(delta_same))),6),
                   "patient_mean_rank_rho_vs_native25":rho(current,native),
                   "patient_mean_rank_rho_vs_same_grid25":rho(current,baseline),
                   "n_patients_abs_change_ge_10pct_vs_native25":int(np.sum(np.abs(delta_native)>=10)),
                   "n_patients_abs_change_ge_20pct_vs_native25":int(np.sum(np.abs(delta_native)>=20)),
                   "source_baseline_registered_native25_confirmed":"YES",
                   "MRI_RNA_tests_executed":"NO","claim_ceiling":"S0"})
        for pid in ids:
            for r in RATERS:
                get=lambda grid,bw:v(pid,r,grid,bw,feature)
                x=get("native",25.)
                if abs(x)<=1e-12:raise ValueError("PATIENT_FEATURE_REFERENCE_ZERO")
                shift=(get("3mm",25.)-x)/abs(x)*100
                profiles.append({"patient_id":pid,"feature":feature,"rater":r,
                   "native12_5":get("native",12.5),"native25":x,"native50":get("native",50),
                   "3mm12_5":get("3mm",12.5),"3mm25":get("3mm",25),"3mm50":get("3mm",50),
                   "registered_3mm_vs_native25_signed_change_pct":round(shift,6),
                   "registered_3mm_vs_native25_abs_change_pct":round(abs(shift),6),
                   "registered_native12_5_vs_native25_abs_change_pct":round(
                      abs((get("native",12.5)-x)/abs(x)*100),6),
                   "registered_native50_vs_native25_abs_change_pct":round(
                      abs((get("native",50)-x)/abs(x)*100),6),
                   "clinical_eligibility":"NOT_ASSESSED",
                   "MRI_RNA_tests_executed":"NO","claim_ceiling":"S0"})
    if len(metrics)!=24 or len(profiles)!=14*2*len(FEATS):
        raise ValueError("METRICS_24_PATIENT_READER_PROFILES_112_EXPECTED")
    if any(x["claim_ceiling"]!="S0" or x["MRI_RNA_tests_executed"]!="NO" for x in metrics):
        raise ValueError("CLINICAL_HOLD_VIOLATION")
    return metrics,profiles,confirmed

def offline():
    assert len(frozen())==14
    assert rho([1,2,3,4],[4,3,2,1])==-1
    assert rho([1,2,2,4],[1,2,2,4])==1
    assert all(abs(x)<1e-8 for x in relative_percent([2,4],[2,4]))
    assert len(FEATS)*len(SPACES)*len(BINS)==24
    print("HCC_PV_REGISTERED_FACTORIAL_AGGREGATE_AND_RANK_OFFLINE_PASS")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--offline-test",action="store_true")
    ap.add_argument("--shard-dir",default="artifacts/hcc_reg_factorial")
    ap.add_argument("--source-56-zip",type=Path)
    ap.add_argument("--out-dir",default="artifacts/hcc_reg_factorial_summary")
    args=ap.parse_args()
    if args.offline_test:return offline()
    if args.source_56_zip is None:
        raise ValueError("IMMUTABLE_REGISTERED_SOURCE_56_ROWS_ZIP_REQUIRED")
    rows=load_shards(Path(args.shard_dir))
    orig=reference_from_zip(args.source_56_zip)
    metrics,patients,checks=summarize(rows,orig)
    dest=Path(args.out_dir);dest.mkdir(parents=True,exist_ok=True)
    for name,items,columns in (
      ("hcc_registered_pv_14x2_2x3_glcm_extraction_rows.csv",rows,list(rows[0])),
      ("hcc_registered_pv_24_feature_condition_metrics.csv",metrics,METRIC_FIELDS),
      ("hcc_registered_pv_112_patient_reader_feature_profiles.csv",patients,PATIENT_FIELDS)):
        with (dest/name).open("w",newline="",encoding="utf8") as f:
            w=csv.DictWriter(f,fieldnames=columns)
            w.writeheader();w.writerows(items)
    evidence={
     "status":"PASS_ALL14_REGISTERED_PV_FACTORIAL_SOURCE_METHODS_ONLY",
     "source_run_id":41191599451,"original_source_artifact_id":13039386584,
     "original_registered_native_bw25_feature_checks":checks,
     "n_independent_patients":14,"n_reader_profiles":28,"n_extraction_rows":168,
     "n_condition_metric_rows":24,"n_patient_feature_reader_profiles":112,
     "features":list(FEATS),"phase":"official_reoriented_art_pv",
     "voxel_conditions":list(SPACES),"bin_widths":list(BINS),
     "image_3mm_interpolation":"sitkBSpline","mask_3mm_interpolation":"NEAREST_NEIGHBOR",
     "same_mask_source_per_patient_across_conditions":True,
     "expert_anatomic_review":"NOT_ASSESSED","RNA_same_index_lesion":"NOT_ASSESSED",
     "MRI_before_therapy":"NOT_ASSESSED","clinical_eligible_n":"NOT_ASSESSED",
     "original_12_MRI_RNA_tests":"NOT_EXECUTED","claim_ceiling":"S0",
     "glcm_contrast_conditions":[r for r in metrics if r["feature"]=="original_glcm_Contrast"]}
    (dest/"hcc_registered_pv_2x3_factorial_summary.json").write_text(
        json.dumps(evidence,indent=2)+"\n",encoding="utf8")
    print("HCC_REGISTERED_PV_14_PATIENT_168_SOURCE_EXTRACTED_24_FEATURE_CONDITIONS",
          json.dumps({k:evidence[k] for k in (
          "n_independent_patients","n_extraction_rows","n_condition_metric_rows",
          "original_registered_native_bw25_feature_checks","glcm_contrast_conditions",
          "original_12_MRI_RNA_tests","claim_ceiling")}),flush=True)
if __name__=="__main__":main()
