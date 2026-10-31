#!/usr/bin/env python3
"""Outcome-blind HCC MRI n=14 paired patient bootstrap for MRI source stability.

All 56 rows are reloaded from the SHA256-pinned original GitHub Actions artifact.
Patient is the independent resampling unit (never 28 readers). Preserve two
expert rater measurements and raw/registered PV pairing inside every resample.
No RNA counts, Hallmark scores, clinical eligibility or associations used.
"""
import argparse,csv,io,json,math,zipfile
from pathlib import Path
import numpy as np
from mri_p0_frozen_source_results_qc import EXPECTED, audit as verify_original
from mri_phase_mask_source_gate import frozen

FEATURES=(
 "original_shape_VoxelVolume","original_shape_SurfaceArea",
 "original_shape_Sphericity","original_shape_Elongation",
 "original_firstorder_Mean","original_firstorder_Median",
 "original_firstorder_Entropy","original_firstorder_InterquartileRange",
 "original_glcm_Contrast","original_glcm_JointEntropy")
LOCKED=("original_firstorder_Entropy","original_firstorder_InterquartileRange",
        "original_glcm_Contrast")
PHASE=("raw_pv","reoriented_art_pv")
RATERS=("rater1","rater2")
SEED=20261031
BOOT=4000
OUTCOME_TESTS=0

def icc_a1(arr):
    # Identical two-way random-effects absolute agreement ICC(A,1)
    # definition as original mri_pv_pyradiomics_rater_icc.py.
    x=np.asarray(arr,dtype=np.float64)
    if x.ndim!=2 or x.shape[1]!=2 or x.shape[0]<3 or not np.isfinite(x).all():
        raise ValueError("ICC_BAD_PAIRED_CASE_READER_MATRICES")
    if float(np.ptp(x))<1e-12:
        raise ValueError("ICC_CONSTANT_FEATURE_UNDEFINED")
    n,k=x.shape
    grand=float(np.mean(x));r=np.mean(x,axis=1);c=np.mean(x,axis=0)
    msr=k*np.sum((r-grand)**2)/(n-1)
    msc=n*np.sum((c-grand)**2)/(k-1)
    resid=x-r[:,None]-c[None,:]+grand
    mse=np.sum(resid**2)/((n-1)*(k-1))
    d=msr+(k-1)*mse+k*(msc-mse)/n
    if d<=0 or not math.isfinite(float(d)):
        raise ValueError("ICC_VARIANCE_DENOMINATOR_UNDEFINED")
    return float((msr-mse)/d)

def average_ranks(values):
    a=np.asarray(values,dtype=float)
    if a.ndim!=1 or not np.isfinite(a).all():
        raise ValueError("RANK_NONFINITE_OR_NOT_1D")
    order=np.argsort(a,kind="stable")
    rank=np.empty(len(a),dtype=float)
    j=0
    while j<len(a):
        k=j+1
        while k<len(a) and a[order[k]]==a[order[j]]:k+=1
        rank[order[j:k]]=(j+1+k)/2.0
        j=k
    return rank

def spearman(x,y):
    a,b=average_ranks(x),average_ranks(y)
    if np.ptp(a)<1e-12 or np.ptp(b)<1e-12:
        return None
    return float(np.corrcoef(a,b)[0,1])

def quant_ci(samples):
    good=[float(a) for a in samples if a is not None and math.isfinite(float(a))]
    if len(good)<int(BOOT*.95):
        return None,None,len(good)
    low,high=np.percentile(good,[2.5,97.5])
    return round(float(low),6),round(float(high),6),len(good)

def read_immutable(source_zip):
    verify_original(source_zip)
    with zipfile.ZipFile(source_zip) as z:
        rows=list(csv.DictReader(io.StringIO(
            z.read("hcc_mri14_raw_vs_registered_pv_all_features.csv").decode("utf-8"))))
    return rows

def make_cube(rows):
    patients=sorted(frozen())
    bykey={}
    for row in rows:
        key=(row["patient_id"],row["phase"],row["rater"])
        if key in bykey:raise ValueError("DUPLICATED_PATIENT_ARM_READER")
        bykey[key]=row
    keys={(p,phase,rater) for p in patients for phase in PHASE for rater in RATERS}
    if set(bykey)!=keys or len(rows)!=56:
        raise ValueError("SOURCE_14x2x2_UNPAIRED_OR_EXTRA_ROW")
    data=np.empty((14,2,2,10),dtype=float)
    for i,pid in enumerate(patients):
        for j,phase in enumerate(PHASE):
            for k,rater in enumerate(RATERS):
                r=bykey[(pid,phase,rater)]
                if (r["eligible_for_MRI_RNA"]!="NOT_ASSESSED" or
                    r["MRI_pretreatment_verified"]!="NOT_ASSESSED" or
                    r["RNA_same_index_lesion"]!="NOT_ASSESSED" or
                    r["research_claim_ceiling"]!="S0"):
                    raise ValueError("ILLEGAL_BIOLOGICAL_SOURCE_PROMOTION")
                if int(r["selected_tumor"])!=frozen()[pid]:
                    raise ValueError("SOURCE_INDEX_TUMOR_CHANGED")
                data[i,j,k,:]=[float(r[f]) for f in FEATURES]
    if not np.isfinite(data).all():raise ValueError("SOURCE_FEATURE_NONFINITE")
    if np.min(data[:,:, :, :4])<=0:raise ValueError("POSITIVE_SHAPE_FEATURE_EXPECTED")
    return patients,data

def summarize(patients,data,b=BOOT,seed=SEED):
    if b!=BOOT:raise ValueError("PREDECLARED_BOOTSTRAP_COUNT_DRIFT")
    if len(patients)!=14 or data.shape!=(14,2,2,10):
        raise ValueError("INDEPENDENT_14_PATIENT_FOUR_ARM_TEN_FEATURE_REQUIRED")
    rng=np.random.default_rng(seed)
    indices=rng.integers(0,14,size=(b,14))
    feature_rows=[];icc_rows=[];case_rows=[]
    for ix,feat in enumerate(FEATURES):
        raw=data[:,0,:,ix].mean(axis=1)
        reg=data[:,1,:,ix].mean(axis=1)
        if np.any(np.abs(raw)<=1e-12):
            raise ValueError("UNDEFINED_SOURCE_RELATIVE_CHANGE_DENOMINATOR")
        pct=(reg-raw)/np.abs(raw)*100
        for pid,val in zip(patients,pct):
            case_rows.append({"patient_id":pid,"feature":feat,
                "rater_averaged_raw":round(float(raw[patients.index(pid)]),8),
                "rater_averaged_registered":round(float(reg[patients.index(pid)]),8),
                "registered_vs_raw_signed_pct":round(float(val),8),
                "RNA_test_performed":"NO","clinical_eligibility":"NOT_ASSESSED"})
        boot_med_abs=np.median(np.abs(pct[indices]),axis=1)
        boot_med_signed=np.median(pct[indices],axis=1)
        boot_rho=[spearman(raw[boot_ix],reg[boot_ix]) for boot_ix in indices]
        med_ci=quant_ci(boot_med_abs)
        signed_ci=quant_ci(boot_med_signed)
        rho_ci=quant_ci(boot_rho)
        if min(med_ci[2],signed_ci[2],rho_ci[2])<int(b*.95):
            raise ValueError("TOO_MANY_DEGENERATE_SOURCE_BOOTSTRAPS")
        row={"feature":feat,"n_independent_patients":14,
            "n_reader_repeated_measures_per_arm":2,"n_paired_bootstrap":b,
            "median_abs_pct":round(float(np.median(np.abs(pct))),6),
            "median_abs_pct_ci95_low":med_ci[0],"median_abs_pct_ci95_high":med_ci[1],
            "median_signed_pct":round(float(np.median(pct)),6),
            "median_signed_pct_ci95_low":signed_ci[0],
            "median_signed_pct_ci95_high":signed_ci[1],
            "spearman_patient_mean_raw_vs_registered":round(float(spearman(raw,reg)),6),
            "spearman_ci95_low":rho_ci[0],"spearman_ci95_high":rho_ci[1],
            "n_valid_boot_rho":rho_ci[2],
            "n_cases_abs_pct_ge10":int(np.sum(np.abs(pct)>=10)),
            "n_cases_abs_pct_ge20":int(np.sum(np.abs(pct)>=20)),
            "locked_primary_MRI_feature":feat in LOCKED,
            "RNA_association_executed":False,"claim_ceiling":"S0"}
        feature_rows.append(row)
        ar=data[:,0,:,ix];br=data[:,1,:,ix]
        observed_raw=icc_a1(ar);observed_reg=icc_a1(br)
        diffs=[]
        for ids in indices:
            try:
                d=icc_a1(br[ids,:])-icc_a1(ar[ids,:])
                if math.isfinite(d):diffs.append(d)
            except ValueError:
                continue
        lo,hi,valid=quant_ci(diffs)
        if valid<int(b*.95):raise ValueError("ICC_DELTA_BOOTSTRAP_TOO_MANY_DEGENERATE")
        icc_rows.append({"feature":feat,"n_patients":14,"bootstrap":b,
            "raw_icc_A1":round(observed_raw,6),"registered_icc_A1":round(observed_reg,6),
            "registered_minus_raw_icc_A1":round(observed_reg-observed_raw,6),
            "paired_boot_icc_difference_ci95_low":lo,
            "paired_boot_icc_difference_ci95_high":hi,
            "valid_bootstrap_count":valid,
            "locked_primary_MRI_feature":feat in LOCKED,
            "biological_inference_allowed":False})
    return feature_rows,icc_rows,case_rows

def offline_test():
    assert list(average_ranks([7,7,1,4]))==[3.5,3.5,1.,2.]
    assert abs(spearman([1,2,3,4],[4,3,2,1])+1)<1e-9
    assert spearman([1,1,1],[2,3,4]) is None
    assert abs(icc_a1([[1,1],[2,2],[3,3]])-1)<1e-12
    r=np.tile(np.array([[1.,2.],[3.,4.],[5.,6.]]),(1,1))
    assert math.isfinite(icc_a1(r))
    fake=np.tile(np.array([1.,2.,3.,4.,5.,6.,7.,8.,9.,10.]),(14,2,2,1))
    # Every person must stay distinct to allow nondegenerate resampling.
    fake*=np.arange(1,15)[:,None,None,None]
    patients=sorted(frozen())
    feature,icc,case=summarize(patients,fake)
    assert len(feature)==10 and len(icc)==10 and len(case)==140
    assert all(x["median_abs_pct"]==0 for x in feature)
    assert all(x["registered_minus_raw_icc_A1"]==0 for x in icc)
    assert all(x["RNA_association_executed"] is False for x in feature)
    try:summarize(patients,fake[:13])
    except ValueError:pass
    else:raise AssertionError("MISSING_PATIENT_MUST_BE_REJECTED")
    fake2=fake.copy();fake2[0,0,0,6]=np.nan
    try:summarize(patients,fake2)
    except (ValueError,AssertionError):pass
    else:raise AssertionError("NONFINITE_FEATURE_MUST_BE_REJECTED")
    print("HCC_MRI14_SOURCE_BOOTSTRAP_10_FEATURE_ICC_DELTA_NEGATIVE_FIXTURES_PASS")

def make_figures(out, feature_rows,case_rows,icc_rows):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    names={"original_firstorder_Entropy":"Entropy",
           "original_firstorder_InterquartileRange":"IQR",
           "original_glcm_Contrast":"GLCM Contrast"}
    selected=[next(x for x in feature_rows if x["feature"]==f) for f in LOCKED]
    fig,ax=plt.subplots(figsize=(9.2,4.8))
    ys=np.arange(len(selected))
    mids=np.asarray([x["median_abs_pct"] for x in selected])
    lower=mids-np.asarray([x["median_abs_pct_ci95_low"] for x in selected])
    upper=np.asarray([x["median_abs_pct_ci95_high"] for x in selected])-mids
    ax.errorbar(mids,ys,xerr=[lower,upper],fmt="o",capsize=4,color="#185e72")
    ax.set_yticks(ys,list(map(names.get,LOCKED)))
    ax.invert_yaxis()
    ax.set_xlim(left=0)
    ax.set_xlabel("Median absolute raw-vs-registered PV change (%) — 95% patient bootstrap CI")
    ax.set_title("HCC 14 independent patients | two readers averaged within patient")
    ax.grid(axis="x",alpha=.25)
    fig.tight_layout()
    fig.savefig(out/"hcc_mri14_locked_source_median_abs_pct_bootstrap_ci.png",dpi=175)
    plt.close(fig)
    fig,ax=plt.subplots(figsize=(9.2,4.8))
    sel=[next(x for x in icc_rows if x["feature"]==f) for f in LOCKED]
    centers=np.asarray([x["registered_minus_raw_icc_A1"] for x in sel])
    lower=centers-np.asarray([x["paired_boot_icc_difference_ci95_low"] for x in sel])
    upper=np.asarray([x["paired_boot_icc_difference_ci95_high"] for x in sel])-centers
    ax.errorbar(centers,ys,xerr=[lower,upper],fmt="s",capsize=4,color="#764a8c")
    ax.axvline(0,color="black",linestyle="--",linewidth=1)
    ax.set_yticks(ys,list(map(names.get,LOCKED)))
    ax.invert_yaxis()
    ax.set_xlabel("Registered PV − raw PV ICC(A,1): 95% paired-patient bootstrap CI")
    ax.set_title("Same 14 patients & masks in both arms; independent unit is patient")
    ax.grid(axis="x",alpha=.25)
    fig.tight_layout()
    fig.savefig(out/"hcc_mri14_locked_paired_icc_difference_bootstrap_ci.png",dpi=175)
    plt.close(fig)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--offline-test",action="store_true")
    ap.add_argument("--evidence-zip",type=Path)
    ap.add_argument("--out-dir",default="artifacts/hcc_mri14_bootstrap_ci")
    args=ap.parse_args()
    if args.offline_test:
        offline_test();return
    if not args.evidence_zip:
        raise ValueError("SHA256_PINNED_ORIGINAL_56_ROW_SOURCE_ARTIFACT_REQUIRED")
    rows=read_immutable(args.evidence_zip)
    patients,data=make_cube(rows)
    feature,icc,case=summarize(patients,data)
    if not(all(x["claim_ceiling"]=="S0" and not x["RNA_association_executed"] for x in feature)
           and len(case)==140 and len(icc)==10):
        raise ValueError("INVALID_SOURCE_ONLY_CI_OUTPUT")
    out=Path(args.out_dir);out.mkdir(parents=True,exist_ok=True)
    for filename,records in [
        ("HCC_MRI14_SOURCE_PAIRED_10_FEATURE_BOOTSTRAP_CI.csv",feature),
        ("HCC_MRI14_SOURCE_PAIRED_10_ICC_DELTA_BOOTSTRAP_CI.csv",icc),
        ("HCC_MRI14_SOURCE_PATIENT_10_FEATURE_SIGNED_CHANGE.csv",case)]:
        with (out/filename).open("w",newline="",encoding="utf-8") as f:
            w=csv.DictWriter(f,fieldnames=list(records[0]))
            w.writeheader();w.writerows(records)
    summary={
        "status":"PASS_SOURCE_SENSITIVITY_UNCERTAINTY_DESCRIPTIVE_ONLY",
        "original_verified_run_id":41191599451,
        "n_independent_patients":14,"n_feature_rows":56,
        "bootstrap_seed":SEED,"n_paired_patient_resamples":BOOT,
        "bootstrap_ci_method":"simple_percentile_2_5_to_97_5",
        "n_source_features":10,"n_original_locked_MRI_features":3,
        "ICC_model":"two_way_random_absolute_agreement_single_rating_McGrawWong_A_1",
        "source_arms":list(PHASE),"source_robustness_is_not_reader_reliability":True,
        "original_three_locked_feature_results":[x for x in feature if x["locked_primary_MRI_feature"]],
        "original_three_locked_feature_icc_differences":[x for x in icc if x["locked_primary_MRI_feature"]],
        "clinical_anatomical_approval":"NOT_ASSESSED",
        "MRI_before_HCC_treatment":"NOT_ASSESSED",
        "MRI_index_tumor_same_as_RNA_tissue":"NOT_ASSESSED",
        "qualified_RNA_matched_n":"NOT_ASSESSED","MRI_RNA_12_tests":"NOT_EXECUTED",
        "biological_p_value_computed":False,
        "claim_ceiling":"S0"}
    (out/"HCC_MRI14_SOURCE_BOOTSTRAP_UNCERTAINTY_METADATA.json").write_text(
        json.dumps(summary,ensure_ascii=False,indent=2)+"\n")
    make_figures(out,feature,case,icc)
    print("HCC_MRI14_SOURCE_BOOTSTRAP_14_PATIENT_10_FEATURE_10_ICC_DELTA_COMPLETE",
          json.dumps({"locked_feature_ci":summary["original_three_locked_feature_results"],
                     "locked_icc_delta":summary["original_three_locked_feature_icc_differences"],
                     "biological_tests":"NOT_EXECUTED","claim_ceiling":"S0"}),flush=True)

if __name__=="__main__":main()
