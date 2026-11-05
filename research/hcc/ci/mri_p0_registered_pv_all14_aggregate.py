#!/usr/bin/env python3
"""Aggregate 7 frozen HCC MRI14 registered-PV feature shards with strict provenance.

14 patients x 2 readers x 2 sources x 10 frozen radiomics features; all numbers
are descriptive and do not authorize MRI–RNA inference or patient inclusion.
"""
import argparse,csv,json,math
from pathlib import Path
from collections import Counter
import numpy as np
from mri_phase_mask_source_gate import frozen
from mri_p0_registered_pv_all14_sharded import (
 ALL_FEATURES,LOCKED,PHASES,RATERS,SHARDS,FIELDS,verify_shard)
from mri_pv_pyradiomics_rater_icc import feature_icc

def rankdata(x):
    # Average ranks of ties; n=14, pure numpy avoids additional SciPy dependency.
    a=np.asarray(x,dtype=np.float64)
    order=np.argsort(a,kind="stable")
    ranks=np.empty(len(a),dtype=np.float64)
    i=0
    while i<len(a):
        j=i+1
        while j<len(a) and a[order[j]]==a[order[i]]:j+=1
        ranks[order[i:j]]=(i+1+j)/2.0
        i=j
    return ranks

def rho(x,y):
    x=rankdata(x);y=rankdata(y)
    if np.std(x)==0 or np.std(y)==0:
        return None
    return round(float(np.corrcoef(x,y)[0,1]),6)

def load(directory):
    cases=frozen()
    data=[];manifests=[]
    for index in range(SHARDS):
        filename=directory/f"hcc_mri14_registered_phase_shard_{index}.csv"
        manifest=directory/f"hcc_mri14_registered_phase_shard_{index}.json"
        with filename.open(newline="",encoding="utf-8") as f:
            records=list(csv.DictReader(f))
        # This verifier is shared with the extractor, so parse the CSV selected
        # tumor integer explicitly rather than trusting deserialized strings.
        for r in records:r["selected_tumor"]=int(r["selected_tumor"])
        verify_shard(records,index)
        data+=records
        m=json.loads(manifest.read_text(encoding="utf-8"))
        if m["shard_index"]!=index or m["source_case_ids"]!=sorted(cases)[2*index:2*index+2]:
            raise ValueError("SHARD_MANIFEST_PATIENT_DRIFT")
        if (m["qualified_clinical_n"]!="NOT_ASSESSED" or
            m["12_primary_MRI_RNA_associations"]!="NOT_EXECUTED" or
            m["pyradiomics_distribution"]!="3.1.0" or
            not m["no_registered_image_resampling"]):
            raise ValueError("FROZEN_SOURCE_OR_CLINICAL_MANIFEST_DRIFT")
        manifests.append(m)
    if len(data)!=56 or len({(r["patient_id"],r["rater"],r["phase"]) for r in data})!=56:
        raise ValueError("FULL_14_2_2_MANIFEST_NOT_COMPLETE")
    for pid in cases:
        for phase in PHASES:
            records=[r for r in data if r["patient_id"]==pid and r["phase"]==phase]
            if len(records)!=2 or records[0]["source_sha256"]!=records[1]["source_sha256"]:
                raise ValueError("PHASE_SOURCE_SHA_CONFLICT")
        for rater in RATERS:
            records=[r for r in data if r["patient_id"]==pid and r["rater"]==rater]
            if len(records)!=2 or records[0]["mask_sha256"]!=records[1]["mask_sha256"]:
                raise ValueError("READER_SOURCE_MASK_SHA_CONFLICT")
    return data,manifests

def summarize(data):
    ids=sorted(frozen())
    bykey={(r["patient_id"],r["rater"],r["phase"]):r for r in data}
    feature_results=[]
    for feat in ALL_FEATURES:
        # Two-reader averages of each case, NOT 28 independent patient samples.
        a=[];b=[];pct=[]
        for pid in ids:
            raw=float(np.mean([float(bykey[(pid,r,"raw_pv")][feat]) for r in RATERS]))
            reg=float(np.mean([float(bykey[(pid,r,"reoriented_art_pv")][feat]) for r in RATERS]))
            a.append(raw);b.append(reg)
            pct.append(float((reg-raw)/abs(raw)*100) if abs(raw)>1e-12 else None)
        valid=[x for x in pct if x is not None]
        def q(x):
            return round(float(x),5)
        feature_results.append({
            "feature":feat,"patients":14,
            "source_arm":"raw_pv_to_reoriented_art_pv",
            "source_pairwise_patient_rank_rho":rho(a,b),
            "n_pct_valid":len(valid),
            "median_abs_pct_change":q(np.median(np.abs(valid))) if valid else None,
            "max_abs_pct_change":q(np.max(np.abs(valid))) if valid else None,
            "n_cases_abs_pct_ge_10":sum(abs(x)>=10 for x in valid),
            "n_cases_abs_pct_ge_20":sum(abs(x)>=20 for x in valid),
            "median_signed_pct_change":q(np.median(valid)) if valid else None,
            "locked_MRI_RNA_primary_feature":feat in LOCKED,
            "MRI_RNA_association_tested":False})
    icc=[]
    for phase in PHASES:
        subset=[r for r in data if r["phase"]==phase]
        calculated=feature_icc(subset,n_boot=300,seed=20261031)
        for r in calculated:
            icc.append({"source_phase":phase,**r})
    if len(feature_results)!=10 or len(icc)!=20:
        raise ValueError("EXACT_10_FEATURE_SOURCE_COMPARISON_AND_20_ICCS_REQUIRED")
    return feature_results,icc

def offline():
    x=rankdata([7,7,1,4])
    assert list(x)==[3.5,3.5,1.,2.]
    assert rho([1,2,3,4],[4,3,2,1])==-1.
    assert rho([1,1,1,1],[1,2,3,4]) is None
    assert len(frozen())==14 and len(ALL_FEATURES)==10
    print("HCC_MRI14_REGISTERED_SOURCE_VS_RAW_AGGREGATION_NEGATIVE_GATES_PASS")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--offline-test",action="store_true")
    p.add_argument("--shard-dir",default="artifacts/hcc_mri14_source_shards")
    p.add_argument("--out-dir",default="artifacts/hcc_mri14_source_comparison")
    a=p.parse_args()
    if a.offline_test:
        offline();return
    rows,manifests=load(Path(a.shard_dir))
    feature_results,iccs=summarize(rows)
    out=Path(a.out_dir);out.mkdir(parents=True,exist_ok=True)
    for name,items in (
       ("hcc_mri14_raw_vs_registered_pv_all_features.csv",rows),
       ("hcc_mri14_pv_source_feature_sensitivity.csv",feature_results),
       ("hcc_mri14_pv_source_two_reader_icc_a1.csv",iccs)):
        with (out/name).open("w",newline="",encoding="utf-8") as f:
            writer=csv.DictWriter(f,fieldnames=list(items[0]))
            writer.writeheader();writer.writerows(items)
    summary={
        "status":"PASS_14_CASE_SOURCE_METHODS_REPRODUCIBILITY_ONLY",
        "public_dataset":"https://zenodo.org/records/8179129",
        "n_patients":14,"n_source_rater_rows":56,
        "n_features":10,"n_locked_primary_features":3,
        "n_feature_source_sensitivity_results":10,"n_reader_icc_estimates":20,
        "source_arms":list(PHASES),"source_shards":SHARDS,
        "locked_MRI_RNA_features":list(LOCKED),
        "clinical_review":"NOT_ASSESSED",
        "clinical_eligible_n":"NOT_ASSESSED","MRI_RNA_12_associations":"NOT_EXECUTED",
        "no_RNA_measurements_processed":True,
        "historical_raw_PV_measurements_overwritten":False,
        "qualified_RNA_image_pair_verified":0,
        "registered_image_expert_anatomical_validation":"NOT_ASSESSED",
        "claim_ceiling":"S0",
        "HCC12":"PARTIAL","HCC13":"PARTIAL","HCC17":"PENDING","HCC20":"PENDING",
        "locked_feature_sensitivity":[r for r in feature_results if r["locked_MRI_RNA_primary_feature"]],
        "ICC_outcomes":[r for r in iccs if r["feature"] in LOCKED],
        "unestimable_ICC_count":sum(r["reliability_status"].startswith("UNESTIMABLE") for r in iccs)
    }
    (out/"hcc_mri14_registered_source_reproducibility_summary.json").write_text(
        json.dumps(summary,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print("HCC_MRI14_ALL_FULL_SOURCE_COMPARISON_COMPLETE",json.dumps({
        k:summary[k] for k in ("n_patients","n_source_rater_rows","n_features","n_reader_icc_estimates",
                              "unestimable_ICC_count","claim_ceiling")}),flush=True)

if __name__=="__main__":main()
