#!/usr/bin/env python3
"""HCC source-only registered-PV factorial: paired-patient bootstrap uncertainty.

The 168 rows and all published metrics must match the immutable 9-job GitHub
Actions archive from run #41208617950. Resample 14 patients (NOT 28 raters)
for every 2-grid/3-binWidth/4-feature condition, preserving both readers and
the six condition measurements within each patient. No molecular data.
"""
import argparse,csv,hashlib,io,json,math,zipfile
from pathlib import Path
import numpy as np
from scipy.stats import spearmanr
from mri_phase_mask_source_gate import frozen

SOURCE_RUN=41208617950
SOURCE_ARTIFACT=13046135524
SEED=20261101
BOOTS=4000
BASELINE=("native",25.)
CONDITIONS=(("native",12.5),("native",25.),("native",50.),
            ("3mm",12.5),("3mm",25.),("3mm",50.))
FEATURES=("original_glcm_Contrast","original_glcm_JointEntropy",
          "original_firstorder_Entropy","original_firstorder_InterquartileRange")
MEMBER_SHA={
 "hcc_registered_pv_14x2_2x3_glcm_extraction_rows.csv":"66286993a268a177ed663d8d328a5f9b5048d3630e897132b6c503bb44a94911",
 "hcc_registered_pv_24_feature_condition_metrics.csv":"ac65f81c2be42021a3a77f7752145f329b2e9fd694a7a7850d58e8c3a0387784",
 "hcc_registered_pv_112_patient_reader_feature_profiles.csv":"44d6a22d4e80f9135a3f0cd267d24eafc639b4aa5d2b1dbde5913533a356d98f",
 "hcc_registered_pv_2x3_factorial_summary.json":"638d4f91c530da2e30ffdadcc56f28bd8b459f7a3528fe55077ac1cc7e755a82",
}
COLS=("feature","grid","bin_width","n_independent_patients",
      "n_paired_bootstraps","boot_seed","median_abs_change_pct",
      "median_abs_change_pct_ci95_low","median_abs_change_pct_ci95_high",
      "patient_rank_rho","patient_rank_rho_ci95_low","patient_rank_rho_ci95_high",
      "valid_rho_bootstraps","n_cases_abs_change_ge10pct",
      "n_cases_abs_change_ge20pct","MRI_RNA_tests_executed","clinical_eligibility","claim_ceiling")

def read_csv(source):
    return list(csv.DictReader(io.TextIOWrapper(io.BytesIO(source),encoding="utf-8")))

def checked_source(path):
    with zipfile.ZipFile(path) as z:
        if set(z.namelist())!=set(MEMBER_SHA):
            raise ValueError("PINNED_FACTORIAL_SOURCE_ARTIFACT_MEMBER_FAMILY_CHANGED")
        contents={n:z.read(n) for n in MEMBER_SHA}
    for name,sha in MEMBER_SHA.items():
        if hashlib.sha256(contents[name]).hexdigest()!=sha:
            raise ValueError("ORIGINAL_168_ROW_SOURCE_SHA256_CHANGED:"+name)
    rows=read_csv(contents["hcc_registered_pv_14x2_2x3_glcm_extraction_rows.csv"])
    metrics=read_csv(contents["hcc_registered_pv_24_feature_condition_metrics.csv"])
    meta=json.loads(contents["hcc_registered_pv_2x3_factorial_summary.json"])
    if (len(rows)!=168 or len(metrics)!=24 or
        meta["original_registered_native_bw25_feature_checks"]!=112 or
        meta["n_independent_patients"]!=14 or meta["n_extraction_rows"]!=168 or
        meta["original_12_MRI_RNA_tests"]!="NOT_EXECUTED" or
        meta["claim_ceiling"]!="S0" or meta["clinical_eligible_n"]!="NOT_ASSESSED"):
        raise ValueError("FACTORIAL_OR_CLINICAL_HOLD_SOURCE_PROVENANCE_CHANGED")
    return rows,metrics,meta

def matrix(rows):
    ids=sorted(frozen())
    lookup={}
    for r in rows:
        key=(r["patient_id"],r["rater"],r["grid"],float(r["bin_width"]))
        if key in lookup:raise ValueError("DUPLICATE_RATER_OR_CONDITION")
        lookup[key]=r
    expected={(pid,rat,grid,float(bw)) for pid in ids
              for rat in ("rater1","rater2") for grid,bw in CONDITIONS}
    if len(ids)!=14 or len(rows)!=168 or set(lookup)!=expected:
        raise ValueError("FROZEN_14_CASE_FACTORIAL_INCOMPLETE")
    value=np.empty((14,2,6,4),dtype=float)
    for i,pid in enumerate(ids):
        for j,rat in enumerate(("rater1","rater2")):
            shas=set()
            for k,(grid,bw) in enumerate(CONDITIONS):
                row=lookup[(pid,rat,grid,bw)]
                shas.add(row["source_sha256"]+":"+row["mask_sha256"])
                if (row["official_source_phase"]!="reoriented_art_pv" or
                    row["clinical_eligibility"]!="NOT_ASSESSED" or
                    row["registered_anatomical_expert_approval"]!="NOT_ASSESSED" or
                    row["MRI_RNA_tests_executed"]!="NO" or row["claim_ceiling"]!="S0"):
                    raise ValueError("SOURCE_OR_BIOLOGY_LOCK_DRIFT")
                if float(row["mask_affine_max_corner_mm"])>0.5:
                    raise ValueError("SOURCE_MASK_AFFINE_OUTSIDE_0_5MM")
                value[i,j,k,:]=[float(row[f]) for f in FEATURES]
            if len(shas)!=1:raise ValueError("IMAGE_OR_ROI_CHANGED_WITHIN_PATIENT")
    if not np.isfinite(value).all():
        raise ValueError("FACTORIAL_FEATURE_NONFINITE")
    return ids,value.mean(axis=1)

def estimate(ids,patient_means,metrics):
    rng=np.random.default_rng(SEED)
    sampled=rng.integers(0,14,size=(BOOTS,14))
    current_metrics={(r["feature"],r["grid"],float(r["bin_width"])):r for r in metrics}
    out=[]
    for feature_index,feature in enumerate(FEATURES):
        baseline=patient_means[:,CONDITIONS.index(BASELINE),feature_index]
        if np.any(np.abs(baseline)<=1e-12):
            raise ValueError("UNDEFINED_NONZERO_RELATIVE_BASELINE")
        for cond_index,(grid,bw) in enumerate(CONDITIONS):
            values=patient_means[:,cond_index,feature_index]
            signed=(values-baseline)/np.abs(baseline)*100
            absolute=np.abs(signed)
            median=float(np.median(absolute))
            medboot=np.median(absolute[sampled],axis=1)
            low,high=np.percentile(medboot,[2.5,97.5])
            reference=current_metrics[(feature,grid,bw)]
            if abs(median-float(reference["median_abs_change_pct_vs_native25"]))>0.00001:
                raise ValueError("PINNED_FACTORIAL_PATIENT_EFFECT_DISAGREES:"+feature)
            c=float(spearmanr(baseline,values).statistic)
            if not np.isfinite(c):
                if np.array_equal(baseline,values):c=1.0
                else:raise ValueError("UNDEFINED_PATIENT_RANK_CORRELATION")
            if abs(c-float(reference["patient_mean_rank_rho_vs_native25"]))>0.00001:
                raise ValueError("PINNED_FACTORIAL_RANK_DISAGREES:"+feature)
            bootrho=[]
            for indices in sampled:
                v=float(spearmanr(baseline[indices],values[indices]).statistic)
                if np.isfinite(v):bootrho.append(v)
            if len(bootrho)<3800:
                raise ValueError("TOO_MANY_DEGENERATE_RANK_RESAMPLES")
            rlo,rhi=np.percentile(bootrho,[2.5,97.5])
            out.append({
                "feature":feature,"grid":grid,"bin_width":bw,
                "n_independent_patients":14,"n_paired_bootstraps":BOOTS,
                "boot_seed":SEED,"median_abs_change_pct":round(median,6),
                "median_abs_change_pct_ci95_low":round(float(low),6),
                "median_abs_change_pct_ci95_high":round(float(high),6),
                "patient_rank_rho":round(c,6),
                "patient_rank_rho_ci95_low":round(float(rlo),6),
                "patient_rank_rho_ci95_high":round(float(rhi),6),
                "valid_rho_bootstraps":len(bootrho),
                "n_cases_abs_change_ge10pct":int(np.sum(absolute>=10)),
                "n_cases_abs_change_ge20pct":int(np.sum(absolute>=20)),
                "MRI_RNA_tests_executed":"NO",
                "clinical_eligibility":"NOT_ASSESSED","claim_ceiling":"S0"})
    if len(out)!=24:raise ValueError("EXPECTED_24_CONDITION_UNCERTAINTY_OUTPUTS")
    return out

def offline():
    # Publication-independent statistical fixtures.
    assert len(frozen())==14 and frozen()["TCGA-BC-A10Y"]==3
    assert len(CONDITIONS)==6 and len(FEATURES)==4
    assert float(spearmanr([1,2,3,4],[4,3,2,1]).statistic)==-1.
    assert float(spearmanr([1,2,2,4],[1,2,2,4]).statistic)==1.
    samples=np.zeros((14,6,4),dtype=float)
    for i in range(14):
        samples[i,:,:]=(i+1)*np.arange(1,5)[None,:]
    prior=[]
    for fidx,f in enumerate(FEATURES):
        for g,b in CONDITIONS:
            prior.append({"feature":f,"grid":g,"bin_width":b,
                "median_abs_change_pct_vs_native25":"0.0",
                "patient_mean_rank_rho_vs_native25":"1.0"})
    result=estimate(sorted(frozen()),samples,prior)
    assert len(result)==24 and all(r["median_abs_change_pct"]==0 for r in result)
    assert all(r["patient_rank_rho"]==1. for r in result)
    bad=samples.copy();bad[0,0,0]=float("nan")
    # A missing case or invalid feature must never be silently accepted.
    try:estimate(sorted(frozen()),bad,prior)
    except ValueError:pass
    else:raise AssertionError("NONFINITE_REFERENCE_NOT_REJECTED")
    print("HCC_REGISTERED_PV_PATIENT_BOOTSTRAP_24_CONDITION_NEGATIVE_FIXTURE_PASS")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--offline-test",action="store_true")
    p.add_argument("--source-zip",type=Path)
    p.add_argument("--out-dir",default="artifacts/hcc_regpv_factorial_bootstrap")
    a=p.parse_args()
    if a.offline_test:return offline()
    if a.source_zip is None:raise ValueError("PINNED_168_ROW_SOURCE_ARTIFACT_REQUIRED")
    rows,metrics,meta=checked_source(a.source_zip)
    ids,patient_means=matrix(rows)
    out=estimate(ids,patient_means,metrics)
    dest=Path(a.out_dir);dest.mkdir(parents=True,exist_ok=True)
    with (dest/"hcc_registered_pv_factorial_24_condition_4000_patient_bootstrap_ci.csv").open("w",newline="",encoding="utf8") as f:
        w=csv.DictWriter(f,fieldnames=COLS)
        w.writeheader();w.writerows(out)
    summary={
        "status":"SOURCE_FACTORIAL_PAIRED_PATIENT_BOOTSTRAP_PASS",
        "source_run_id":SOURCE_RUN,"original_artifact_id":SOURCE_ARTIFACT,
        "patients_independent":14,"reader_measurements_repeated_within_patient":2,
        "patient_resamples_with_replacement":BOOTS,"seed":SEED,
        "n_frozen_source_extraction_rows":168,"n_feature_condition_results":24,
        "no_MRI_RNA_data":True,"MRI_RNA_12_tests":"NOT_EXECUTED",
        "qualified_radiology_review":"NOT_ASSESSED","eligible_n":"NOT_ASSESSED",
        "claim_ceiling":"S0",
        "glcm_contrast":[x for x in out if x["feature"]=="original_glcm_Contrast"]
    }
    (dest/"hcc_registered_pv_factorial_bootstrap_provenance_summary.json").write_text(json.dumps(summary,indent=2)+"\n")
    print("HCC_REGISTERED_PV_FACTORIAL_24_CONDITION_4000_PATIENT_BOOTSTRAP_COMPLETE",json.dumps(summary),flush=True)

if __name__=="__main__":main()
