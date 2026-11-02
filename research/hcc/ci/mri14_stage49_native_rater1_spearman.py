#!/usr/bin/env python3
"""HCC Stage49: original full 14x2 reader feature-value artifact -> rater1-only
paired patient rank and bootstrap. Frozen image extraction, no MRI downloads.

Inputs: immutable artifact hcc-pv-3mm-native-vs-resampled-14x2 from GitHub
Actions #41161863748, and repository-frozen 14 index tumor, rater summary,
and independent external OpenSwissHCC 59 original PV source feature rows.

Distinguish rater1 Spearman, reader2 Spearman, original 2-reader mean
Spearman (previous source rho=0.850549) and external n59 original source
rho=0.940795. All comparisons are descriptive post-results methods work:
NO inference of scanner equivalence, treatment timing, MRI-RNA biology,
test-retest, prognostic performance or clinical patient eligibility.
"""
import argparse
import csv
import hashlib
import json
import math
import os
import random
import statistics
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SELECT=ROOT/"HCC_MRI_14_PREOUTCOME_INDEX_LESION_SELECTION_20261030.csv"
CASE14=ROOT/"HCC_MRI_PV_14_NATIVE_3MM_ROI_VOLUME_AND_PRIMARY_FEATURE_CHANGE_20261031.csv"
FEATURE14=ROOT/"HCC_MRI_PV_14X2_NATIVE_VS_3MM_FEATURE_REPRODUCIBILITY_20261031.csv"
EXTERNAL59=ROOT/"HCC_EXTERNAL_OPENSWISSHCC_V2_59_INDEX_PATIENT_GLCM_NATIVE3MM_FROZEN_20261101.csv"
SOURCE_RUN=41161863748
SOURCE_ARTIFACT_ID=13027382220
SOURCE_ARTIFACT_NAME="hcc-pv-3mm-native-vs-resampled-14x2"
SOURCE_ARTIFACT_SHA256="7838588956db579211479c87f681a7e35bbee39f982ce6cb53e02b38fe0aab2d"
SOURCE_FILENAME="hcc_pv_14x2_native_3mm_feature_pairs.csv"
FEATURES=("original_shape_VoxelVolume","original_shape_SurfaceArea","original_shape_Sphericity",
 "original_shape_Elongation","original_firstorder_Mean","original_firstorder_Median",
 "original_firstorder_Entropy","original_firstorder_InterquartileRange",
 "original_glcm_Contrast","original_glcm_JointEntropy")
PRIMARY="original_glcm_Contrast"
PATIENT_OUT_FIELDS=(
 "patient_id","index_tumor","source_reader","native_glcm_contrast",
 "resampled_3mm_glcm_contrast","absolute_relative_change_pct",
 "native_rank_average_ties","resampled_rank_average_ties",
 "absolute_rank_displacement","original_source_run","clinical_eligibility",
 "MRI_RNA_biological_tests","claim_ceiling"
)
FEATURE_OUT_FIELDS=("feature","reader1_rho","reader2_rho",
                    "reader_mean_rho","reader_mean_frozen_rho",
                    "reader_mean_frozen_agreement","source_reader_pairs_n",
                    "clinical_eligible_n","claim_ceiling")

def require(ok,msg):
    if not ok:raise ValueError(msg)

def table(path):
    require(path.is_file(),"FROZEN_SOURCE_FILE_ABSENT:"+str(path))
    with path.open("r",encoding="utf8",newline="") as f:
        return list(csv.DictReader(f))

def ranks(values):
    x=[float(v) for v in values]
    require(len(x)>1 and all(math.isfinite(v) for v in x),"RANK_NONFINITE_OR_TOO_SHORT")
    ordered=sorted(range(len(x)),key=lambda i:(x[i],i))
    result=[None]*len(x)
    k=0
    while k<len(x):
        end=k+1
        while end<len(x) and x[ordered[end]]==x[ordered[k]]:
            end+=1
        midpoint=(k+1+end)/2.0
        for j in range(k,end):
            result[ordered[j]]=midpoint
        k=end
    return result

def pearson(a,b):
    require(len(a)==len(b) and len(a)>2,"INSUFFICIENT_PAIRED_PATIENTS")
    am=statistics.mean(a)
    bm=statistics.mean(b)
    da=[v-am for v in a]
    db=[v-bm for v in b]
    denom=math.sqrt(sum(v*v for v in da)*sum(v*v for v in db))
    if denom<1e-13:
        return None
    return sum(x*y for x,y in zip(da,db))/denom

def spearman(a,b):
    return pearson(ranks(a),ranks(b))

def percentile_sorted(x,p):
    require(x and 0<=p<=1,"BOOTSTRAP_EMPTY_OR_BAD_PERCENTILE")
    pos=(len(x)-1)*p
    i=int(pos)
    j=min(i+1,len(x)-1)
    return x[i]+(pos-i)*(x[j]-x[i])

def bootstrap_paired_rho(a,b,seed=20261102,iterations=4000):
    require(len(a)==len(b) and len(a)>=10,"BOOTSTRAP_N_SOURCE_INVALID")
    randomizer=random.Random(seed)
    valid=[]
    skipped=0
    for _ in range(iterations):
        indices=[randomizer.randrange(len(a)) for _ in a]
        r=spearman([a[i] for i in indices],[b[i] for i in indices])
        if r is None:
            skipped+=1
        else:
            valid.append(r)
    require(len(valid)>=iterations*.95,"TOO_MANY_CONSTANT_BOOTSTRAP_RESAMPLES")
    valid.sort()
    return [percentile_sorted(valid,.025),percentile_sorted(valid,.975)],len(valid),skipped

def leave_one_out(a,b):
    vals=[]
    for i in range(len(a)):
        rho=spearman(a[:i]+a[i+1:],b[:i]+b[i+1:])
        require(rho is not None,"LOO_RANK_NOT_IDENTIFIABLE")
        vals.append(rho)
    return [min(vals),max(vals)]

def find_artifact(root):
    found=list(root.rglob(SOURCE_FILENAME))
    require(len(found)==1,"ORIGINAL_28ROW_PAIRED_SOURCE_ARTIFACT_NOT_UNIQUE:"+str(found))
    return found[0]

def get_source(root):
    path=find_artifact(root)
    data=path.read_bytes()
    digest=hashlib.sha256(data).hexdigest()
    x=table(path)
    return x,digest,path

def validate_pairing(source,selected,case14,feature14):
    expected={r["patient_id"]:r for r in selected}
    previous={r["patient_id"]:r for r in case14}
    feature={r["feature"]:r for r in feature14}
    require(len(expected)==len(previous)==14 and set(expected)==set(previous),
            "FROZEN_14PATIENT_SELECTED_TUMOR_OR_CASE_ROSTER_CHANGED")
    require(len(feature)==10 and set(feature)==set(FEATURES),
            "SOURCE_10_FEATURE_FAMILY_DRIFT")
    require(len(source)==28,"ORIGINAL_SOURCE_ROWS_NOT_14X2")
    pairs={}
    for r in source:
        key=(r["patient_id"],r["rater"])
        require(key not in pairs and r["patient_id"] in expected and
                r["rater"] in ("rater1","rater2"),"SOURCE_PAIR_DUPLICATE_OR_UNKNOWN")
        pairs[key]=r
        pid=r["patient_id"]
        require(str(r["selected_tumor_number"])==str(expected[pid]["representative_tumor_number"])==
                str(previous[pid]["tumor_number"]),
                "SELECTED_TUMOR_CHANGED:"+pid)
        require(r["source_phase"]=="PV" and
                float(r["isotropic_spacing_mm"])==3.0 and
                r["resampling_interpolator"]=="sitkBSpline" and
                r["image_mask_affine_qc"]=="PASS_NATIVE_SOURCE_MATCH" and
                r["native_qc"]=="PASS_FEATURE_EXTRACTION" and
                r["resampled_qc"]=="PASS_3MM_FEATURE_EXTRACTION" and
                "3.1.0" in r["native_extractor_version"] and
                "3.1.0" in r["resampled_extractor_version"],
                "SOURCE_PV_PYRADIOMICS_3MM_SETTINGS_DRIFT:"+pid)
        require(r["clinical_eligibility"]=="HOLD_UNRESOLVED_NOT_EXCLUDED",
                "SOURCE_PATIENT_CLINICAL_FALSE_PROMOTION:"+pid)
        for feat in FEATURES:
            for kind in ("native__","resampled__"):
                require(kind+feat in r,"SOURCE_FEATURE_MISSING:"+kind+feat)
                v=float(r[kind+feat])
                require(math.isfinite(v),"SOURCE_FEATURE_NONFINITE:"+pid)
    require(len(pairs)==28 and all((pid,reader) in pairs
             for pid in expected for reader in ("rater1","rater2")),
            "SOURCE_INCOMPLETE_ONE_TO_ONE_14X2_READER_MATRIX")
    require(next(r for r in selected if r["patient_id"]=="TCGA-BC-A10Y")[
                "representative_tumor_number"]=="3","FROZEN_A10Y_INDEX_TUMOR3_DRIFT")
    for pid in expected:
        r=pairs[pid,"rater1"]
        n=float(r["native__"+PRIMARY])
        t=float(r["resampled__"+PRIMARY])
        require(n>0 and t>0,"SOURCE_PRIMARY_ZERO_OR_NEGATIVE:"+pid)
        pct=abs(t-n)/abs(n)
        existing=float(previous[pid]["glcm_contrast_rater1_absolute_relative_change"])
        require(abs(pct-existing)<.000002,"SOURCE_PAIRED_FEATURE_VS_PRIOR_14_RATER1_PERCENT_DRIFT:"+pid)
        require(previous[pid]["clinical_eligibility"]=="HOLD_UNRESOLVED_NOT_EXCLUDED",
                "PRIOR_CLINICAL_PATIENT_STATUS_CHANGED:"+pid)
    return pairs,expected,feature

def audit(original,source_sha,external_rows):
    old14=table(CASE14)
    selected=table(SELECT)
    feature14=table(FEATURE14)
    pairs,roster,ref=validate_pairing(original,selected,old14,feature14)
    ids=sorted(roster)
    report=[]
    for name in FEATURES:
        nr1=[float(pairs[pid,"rater1"]["native__"+name]) for pid in ids]
        sr1=[float(pairs[pid,"rater1"]["resampled__"+name]) for pid in ids]
        nr2=[float(pairs[pid,"rater2"]["native__"+name]) for pid in ids]
        sr2=[float(pairs[pid,"rater2"]["resampled__"+name]) for pid in ids]
        mean1=[(a+b)/2 for a,b in zip(nr1,nr2)]
        mean2=[(a+b)/2 for a,b in zip(sr1,sr2)]
        a,b,c=spearman(nr1,sr1),spearman(nr2,sr2),spearman(mean1,mean2)
        old=float(ref[name]["patient_mean_feature_spearman_rho"])
        require(c is not None and abs(c-old)<.000002,
                "READER_MEAN_RHO_NOT_REPRODUCED_FROM_ORIGINAL_FULL_FEATURES:"+name)
        report.append(dict(feature=name,reader1_rho=a,reader2_rho=b,reader_mean_rho=c,
          reader_mean_frozen_rho=old,reader_mean_frozen_agreement="PASS",
          source_reader_pairs_n=14,clinical_eligible_n="NOT_ASSESSED",claim_ceiling="S0"))
    original_n=[float(pairs[pid,"rater1"]["native__"+PRIMARY]) for pid in ids]
    resampled_n=[float(pairs[pid,"rater1"]["resampled__"+PRIMARY]) for pid in ids]
    rho14=spearman(original_n,resampled_n)
    require(rho14 is not None and len(external_rows)==59 and
            len({r["subject"] for r in external_rows})==59,
            "SOURCE_EXTERNAL_59_OR_RHO_14_NOT_IDENTIFIABLE")
    ext=sorted(external_rows,key=lambda r:r["subject"])
    external_n=[float(r["original_native25_GLCM_Contrast"]) for r in ext]
    external_r=[float(r["resampled_3mm25_GLCM_Contrast"]) for r in ext]
    require(all(r["original_source_run"]=="41221356861" and r["claim_ceiling"]=="S0" for r in ext),
            "EXTERNAL_ORIGINAL_SOURCE_CLAIM_CHANGED")
    rho59=spearman(external_n,external_r)
    require(rho59 is not None and abs(rho59-.940795)<.000003,
            "EXTERNAL_FROZEN_59_RANK_RHO_SOURCE_DRIFT")
    rank_orig=ranks(original_n)
    rank_new=ranks(resampled_n)
    patients=[]
    for i,pid in enumerate(ids):
        native=original_n[i]
        new=resampled_n[i]
        patients.append(dict(patient_id=pid,
          index_tumor=roster[pid]["representative_tumor_number"],
          source_reader="rater1",native_glcm_contrast=native,
          resampled_3mm_glcm_contrast=new,
          absolute_relative_change_pct=100*abs(new-native)/abs(native),
          native_rank_average_ties=rank_orig[i],
          resampled_rank_average_ties=rank_new[i],
          absolute_rank_displacement=abs(rank_new[i]-rank_orig[i]),
          original_source_run=SOURCE_RUN,clinical_eligibility="NOT_ASSESSED",
          MRI_RNA_biological_tests=0,claim_ceiling="S0"))
    ci14,v14,skip14=bootstrap_paired_rho(original_n,resampled_n,seed=20261102)
    ci59,v59,skip59=bootstrap_paired_rho(external_n,external_r,seed=20261103)
    loo14=leave_one_out(original_n,resampled_n)
    loo59=leave_one_out(external_n,external_r)
    largest=sorted(patients,key=lambda r:(-r["absolute_rank_displacement"],r["patient_id"]))
    by_primary={r["feature"]:r for r in report}
    require(abs(by_primary[PRIMARY]["reader_mean_rho"]-.850549)<.000002,
            "ORIGINAL_READER_MEAN_SOURCE_GLCM_RHO_0850549_NOT_REPRODUCED")
    summary=dict(stage="HCC_STAGE49_ORIGINAL_NATIVE_PV_RATER1_ONLY_PAIRED_PATIENT_RANK",
      original_artifact_source_run_id=SOURCE_RUN,
      original_artifact_name=SOURCE_ARTIFACT_NAME,
      original_artifact_id=SOURCE_ARTIFACT_ID,
      original_zip_sha256_pinned=SOURCE_ARTIFACT_SHA256,
      original_complete_feature_pair_csv_sha256=source_sha,
      original_full_feature_pairs=28,
      original_feature_families=10,
      frozen_original_selected_tumor_patient_n=14,
      internal_original_rater1_rank_rho=rho14,
      internal_original_rater2_rank_rho=by_primary[PRIMARY]["reader2_rho"],
      internal_original_two_reader_mean_rank_rho=by_primary[PRIMARY]["reader_mean_rho"],
      internal_rater1_patient_bootstrap_4000_95pct_interval=ci14,
      internal_rater1_bootstrap_valid_draws=v14,
      internal_rater1_bootstrap_constant_skipped=skip14,
      internal_rater1_leave_one_patient_out_rho_range=loo14,
      internal_rater1_max_abs_rank_displacement=max(x["absolute_rank_displacement"] for x in patients),
      internal_rater1_max_rank_displacement_patient_ids=[x["patient_id"] for x in largest
         if x["absolute_rank_displacement"]==largest[0]["absolute_rank_displacement"]],
      external_original_venous_patient_n=59,
      external_original_primary_mask_rank_rho=rho59,
      external_original_patient_bootstrap_4000_95pct_interval=ci59,
      external_bootstrap_valid_draws=v59,
      external_bootstrap_constant_skipped=skip59,
      external_original_leave_one_patient_out_rho_range=loo59,
      between_cohort_rank_rho_difference_descriptive=rho14-rho59,
      cross_cohort_difference_formal_significance_test_performed=False,
      exact_scanner_or_acquisition_protocol_equivalence=False,
      original_native_PV_technical_14case_source_verified=True,
      new_MRI_image_download_or_feature_extraction_performed=False,
      original_same_MRI_index_lesion_GDC_RNA_aliquot_verified_n=0,
      original_MRI_before_all_HCC_therapy_verified_n=0,
      independent_current_expert_selected_ROI_approved_n=0,
      clinical_eligible_n="NOT_ASSESSED",
      MRI_RNA_biology_tests=0,
      claim_ceiling="S0",
      methods_thesis_status="CONDITIONAL_GO_SUBMISSION_HOLD")
    return patients,report,summary

def write(out,pats,features,summary):
    out.mkdir(parents=True,exist_ok=True)
    with (out/"stage49_rater1_14_native3mm_patient_rank_evidence.csv").open("w",newline="",encoding="utf8") as f:
        w=csv.DictWriter(f,fieldnames=PATIENT_OUT_FIELDS);w.writeheader();w.writerows(pats)
    with (out/"stage49_all10_native3mm_reader1_reader2_mean_spearman.csv").open("w",newline="",encoding="utf8") as f:
        w=csv.DictWriter(f,fieldnames=FEATURE_OUT_FIELDS);w.writeheader();w.writerows(features)
    (out/"stage49_original14_reader1_59_original_rank_summary.json").write_text(json.dumps(summary,indent=2)+"\n")
    main=summary["internal_original_rater1_rank_rho"]
    lines=[
      "# HCC Stage49: independent original n14 reader1-only paired feature rank verification",
      "",
      "**Actual source: original GitHub Actions artifact 13027382220 from run 41161863748, 14 patients × 2 readers × 10 features. No images downloaded.**",
      "- n14 original PV reader1 native→3mm GLCM Contrast Spearman: **"+f"{main:.6f}"+"**.",
      "- Original n14 rater2 Spearman: **"+f'{summary["internal_original_rater2_rank_rho"]:.6f}'+"**.",
      "- Frozen original two-reader-mean n14 Spearman: **"+f'{summary["internal_original_two_reader_mean_rank_rho"]:.6f}'+"** (must reproduce 0.850549).",
      "- Independent external n59 native venous original-mask Spearman: **"+f'{summary["external_original_primary_mask_rank_rho"]:.6f}'+"**.",
      "- Within-reader 14-patient bootstrap Spearman 95% exploratory interval (4,000 paired resamples): "+
          str(summary["internal_rater1_patient_bootstrap_4000_95pct_interval"])+".",
      "- External n59 paired bootstrap Spearman interval: "+
          str(summary["external_original_patient_bootstrap_4000_95pct_interval"])+".",
      "- Internal leave-one-patient-out rho: "+str(summary["internal_rater1_leave_one_patient_out_rho_range"])+".",
      "- Maximum internal native vs resampled absolute patient rank displacement: "+
          str(summary["internal_rater1_max_abs_rank_displacement"])+
          " in "+", ".join(summary["internal_rater1_max_rank_displacement_patient_ids"])+".",
      "",
      "**The n14 reader1-only rho, n14 reader2-only rho and n14 two-reader-mean rho are different estimands.**",
      "No formal independent-cohort difference/equivalence test, scanner cause, clinical accuracy or MRI–RNA biological inference.",
      "This is a POST-RESULTS exploratory methods check and NOT prospective preregistration.",
      "",
      "Clinically eligible n NOT_ASSESSED; MRI–RNA biological tests 0/12; biological claim ceiling S0.",
    ]
    report="\n".join(lines)+"\n"
    (out/"stage49_source_reader1_nativePV_patient_rank_report.md").write_text(report)
    if os.getenv("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"],"a") as f:f.write(report)
    print("HCC_STAGE49_ORIGINAL_READER1_PAIRED_RANK_RESULT",json.dumps(summary,sort_keys=True),flush=True)

def offline():
    require(spearman([1,2,3,4],[4,3,2,1]) is not None and
            abs(spearman([1,2,3,4],[4,3,2,1])+1)<1e-12,
            "RANK_NEGATIVE_PERMUTATION_FIXTURE")
    require(abs(spearman([1,1,2,3],[1,2,2,3])-.8333333333333334)<.05,
            "TIED_RANK_FIXTURE_INVALID")
    require(spearman([1]*10,list(range(10))) is None,
            "CONSTANT_FEATURE_SHOULD_HAVE_UNDEFINED_RHO")
    require(len(FEATURES)==10 and PRIMARY in FEATURES,
            "FROZEN10FEATURE_FAMILY_CHANGED")
    print("HCC_STAGE49_SPEARMAN_AVERAGE_TIES_PAIRED_BOOTSTRAP_NEGATIVE_FIXTURES_PASS")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--source-artifact-root",type=Path)
    ap.add_argument("--out-dir",type=Path,default=Path("artifacts/hcc_stage49_native_rater1"))
    ap.add_argument("--offline-test",action="store_true")
    args=ap.parse_args()
    offline()
    if args.offline_test:
        return
    require(args.source_artifact_root and args.source_artifact_root.is_dir(),
            "REQUIRE_ORIGINAL_28_READER_FEATURE_ROWS_ARTIFACT")
    source,sha,path=get_source(args.source_artifact_root)
    write(args.out_dir,*audit(source,sha,table(EXTERNAL59)))
if __name__=="__main__":
    main()
