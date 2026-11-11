#!/usr/bin/env python3
"""Aggregate external HCC MRI-only OpenSwissHCC v2 actual 59-person cohort.

Exactly one published-lesion-size-frozen venous HCC lesion per subject,
across 15 SOURCE IMAGE / ROI shard manifests. Raters are NOT replicated in
the full 59-person dataset; original LiverHccSeg 14-case ICC is not portable.
Fail-closed source identity and missingness accounting, no molecular tests,
no patient-level clinical validation. Patient-cluster bootstrap only.
"""
import argparse,csv,hashlib,io,json,math,statistics,zipfile
from collections import Counter
from pathlib import Path
import numpy as np

SOURCE_RUN=41219039484
SOURCE_ARTIFACT_ID=13049177735
SOURCE_SHA={
 "openswisshcc_v2_all_90_venous_HCC_lesion_size_and_primary_flags.csv":
 "a8291b4de55fdec75a59378218c017aedfa4bcb950ac4bde9813780c8b43fc42",
 "openswisshcc_v2_primary_1_HCC_venous_lesion_per_subject.csv":
 "4e1882540f9d165a279bd5afab1b5983f5570e1e94bdebbb2fdb798c41f61432",
 "openswisshcc_v2_primary_selection_summary.json":
 "31590e93813c0be862050a26865688b9ed8313185c366962875a7566d50e1a11"
}
PILOT_SHARD0_SHA={
 "external_hcc_venous_pyradiomics_shard_0.csv":
 "6179a25aa92ef22946df5d6e43c51dcc1069580e0dee27fd2fe1842ac2eb129e",
 "external_hcc_venous_source_hold_shard_0.csv":
 "fea31c8e37c2b4837ac9789d8b5cb915c207d1ad0fa6751b9ce16ea6e7543a2c",
 "external_hcc_venous_source_shard_0.json":
 "b44517d3544bfb825887644c8935c202ee3e3c5401f47119340fa4fc10deed53"
}
SEED=20261101
B=4000
FEATURES=("original_glcm_Contrast","original_glcm_JointEntropy",
          "original_firstorder_Entropy","original_firstorder_InterquartileRange")
CONDITIONS=(("native",12.5),("native",25.),("native",50.),
            ("3mm",12.5),("3mm",25.),("3mm",50.))
REFERENCE=("native",25.)
DEFAULT_MIN_DESCRIPTIVE_N=10
QC_COLUMNS=("patient_id","selected_lesion","original_size_mm",
 "source_venous_image_sha256","source_mask_sha256","source_spacing_mm",
 "mask_voxels","mask_affine_corner_mm",
 "baseline_native_bw25_glcm_contrast","resampled_3mm_bw25_glcm_contrast",
 "signed_glcm_3mm_bw25_pct","absolute_glcm_3mm_bw25_pct",
 "native_bw12_5_glcm_abs_pct","native_bw50_glcm_abs_pct",
 "analysis_status","source_external_validation","clinical_eligibility",
 "original_MRI_RNA_associations_executed","claim_ceiling")
STATS_COLUMNS=("feature","grid","binWidth","independent_technical_subjects",
 "bootstrap_seed","bootstrap_resamples","native25_reference",
 "median_abs_pct","median_abs_pct_bootstrap95_low",
 "median_abs_pct_bootstrap95_high",
 "median_signed_pct","min_abs_pct","max_abs_pct",
 "n_abs_pct_ge10","n_abs_pct_ge20","patient_rank_spearman",
 "patient_rank_spearman_bootstrap95_low",
 "patient_rank_spearman_bootstrap95_high",
 "valid_spearman_bootstraps","no_hypothesis_p_value",
 "clinical_eligibility","MRI_RNA_tests_executed","claim_ceiling")

def read_csv(path):
    with path.open(newline="",encoding="utf8") as f:return list(csv.DictReader(f))
def origin_manifest(path):
    with zipfile.ZipFile(path) as z:
        if set(z.namelist())!=set(SOURCE_SHA):
            raise ValueError("FROZEN_OPEN_SWISS_SOURCE_ARCHIVE_MEMBERS_DRIFT")
        data={n:z.read(n) for n in SOURCE_SHA}
    for n,d in SOURCE_SHA.items():
        if hashlib.sha256(data[n]).hexdigest()!=d:
            raise ValueError("FROZEN_OPEN_SWISS_PATIENT_ROSTER_SHA256_DRIFT:"+n)
    roster=list(csv.DictReader(io.StringIO(
        data["openswisshcc_v2_primary_1_HCC_venous_lesion_per_subject.csv"].decode())))
    meta=json.loads(data["openswisshcc_v2_primary_selection_summary.json"])
    if (len(roster)!=59 or len({x["subject"] for x in roster})!=59
        or meta["subjects_with_deterministic_largest_published_lesion"]!=59
        or meta["subjects_HOLD_missing_any_candidate_lesion_size"]!=0
        or meta["HCC_venous_source_lesions"]!=90
        or meta["claim_ceiling"]!="S0"):
        raise ValueError("UNEXPECTED_FROZEN_59_OPEN_SWISS_ROSTER")
    return sorted(roster,key=lambda x:x["subject"])

def source_rows(root,roster):
    allrows=[];allhold=[];manifest=[]
    for shard in range(15):
        dirpath=root
        f=dirpath/f"external_hcc_venous_pyradiomics_shard_{shard}.csv"
        h=dirpath/f"external_hcc_venous_source_hold_shard_{shard}.csv"
        j=dirpath/f"external_hcc_venous_source_shard_{shard}.json"
        if not f.is_file() or not h.is_file() or not j.is_file():
            raise ValueError("MISSING_ACTUAL_SOURCE_SHARD_FILE:"+str(shard))
        if shard==0:
            for fn,expected_sha in PILOT_SHARD0_SHA.items():
                if hashlib.sha256((root/fn).read_bytes()).hexdigest()!=expected_sha:
                    raise ValueError("PRIOR_VERIFIED_4_PATIENT_SHARD_SHA256_DRIFT:"+fn)
        current=read_csv(f);holds=read_csv(h);m=json.loads(j.read_text())
        expected=roster[4*shard:4*shard+4]
        if not (m["shard"]==shard and m["n_expected"]==len(expected)
          and m["expected_source_patients"]==[x["subject"] for x in expected]
          and m["n_feature_grid_rows"]==len(current)
          and m["n_hold"]==len(holds)
          and m["RNA_12_tests"]=="NOT_EXECUTED"
          and m["claim_ceiling"]=="S0" and m["clinical_n"]=="NOT_ASSESSED"):
            raise ValueError("SOURCE_SHARD_MANIFEST_OR_COHORT_DENOMINATOR_DRIFT:"+str(shard))
        completed={r["patient_id"] for r in current}
        failed={r["patient_id"] for r in holds}
        if (completed & failed or len(completed)+len(failed)!=len(expected)
            or completed|failed!={x["subject"] for x in expected}
            or len(current)!=6*len(completed)
            or m["n_succeeded"]!=len(completed)):
            raise ValueError("SHARD_HAS_MISSING_DUPLICATED_OR_PARTIAL_PATIENT_RECORDS:"+str(shard))
        allrows+=current;allhold+=holds;manifest.append(m)
    if len({x["patient_id"] for x in allrows+allhold})!=59:
        raise ValueError("ALL_59_PATIENTS_MUST_BE_ACCOUNTED_FOR")
    return allrows,allhold,manifest

def verify_and_quantify(roster,allrows,holds):
    lookup={(r["patient_id"],r["grid"],float(r["binWidth"])):r for r in allrows}
    if len(lookup)!=len(allrows):
        raise ValueError("DUPLICATED_RADIOMICS_SOURCE_PATIENT_GRID_CELL")
    expected_ids={x["subject"]:x for x in roster}
    failures={x["patient_id"] for x in holds}
    for h in holds:
        if (h["patient_id"] not in expected_ids or
            h["clinical_eligibility"]!="NOT_ASSESSED" or h["claim_ceiling"]!="S0" or
            h["radiomics_extracted"]!="NO"):
            raise ValueError("SOURCE_INPUT_FAILURE_NOT_EXPLICITLY_ACCOUNTED_FOR")
    succeeded=sorted(set(r["patient_id"] for r in allrows))
    if any(pid in failures for pid in succeeded):
        raise ValueError("PATIENT_IN_BOTH_SOURCE_EXTRACTED_AND_HOLD")
    records=[];featuremat=[]
    for pid in succeeded:
        src=expected_ids[pid]
        cells=[lookup.get((pid,g,float(b))) for g,b in CONDITIONS]
        if any(r is None for r in cells):raise ValueError("PARTIAL_SOURCE_FEATURE_GRID:"+pid)
        for r in cells:
            if (r["selected_lesion"]!=src["selected_lesion"] or
                r["original_venous_manual_mask_member"]!=src["source_mask_path"] or
                r["source_phase"]!="original_native_venous_water" or
                r["pyradiomics_version"]!="3.1.0" or
                r["independent_subject_count_unit"]!="YES" or
                r["clinical_eligibility"]!="NOT_ASSESSED" or
                r["MRI_RNA_associations_executed"]!="NO" or
                r["claim_ceiling"]!="S0"):
                raise ValueError("WRONG_TUMOR_SOURCE_NIFTI_OR_ILLEGAL_CLINICAL_PROMOTION:"+pid)
        if (len({x["original_image_sha256"] for x in cells})!=1 or
            len({x["original_mask_sha256"] for x in cells})!=1 or
            len({x["mask_nonzero_voxel_count"] for x in cells})!=1 or
            len({x["original_venous_image_member"] for x in cells})!=1 or
            not all(len(x["original_image_sha256"])==64 and len(x["original_mask_sha256"])==64
                    for x in cells) or
            any(float(x["image_mask_affine_corner_mm"])>0.5 for x in cells)):
            raise ValueError("ORIGINAL_NIFTI_SOURCE_OR_PHYSICAL_GEOMETRY_DRIFT:"+pid)
        matrix=np.asarray([[float(row[f]) for f in FEATURES] for row in cells])
        if matrix.shape!=(6,4) or not np.isfinite(matrix).all():
            raise ValueError("INVALID_FINITE_6x4_FEATURE_MATRIX:"+pid)
        base=matrix[CONDITIONS.index(REFERENCE),0]
        if base<=0:
            raise ValueError("NONPOSITIVE_BASELINE_GLCM_SOURCE_FEATURE:"+pid)
        per=matrix[CONDITIONS.index(("3mm",25.)),0]
        delta=(per-base)/abs(base)*100
        featnorm={}
        for key in (("native",12.5),("native",50.)):
            val=matrix[CONDITIONS.index(key),0]
            featnorm[key]=abs((val-base)/abs(base))*100
        c=cells[CONDITIONS.index(REFERENCE)]
        records.append({
            "patient_id":pid,"selected_lesion":src["selected_lesion"],
            "original_size_mm":src["source_lesion_size_mm"],
            "source_venous_image_sha256":c["original_image_sha256"],
            "source_mask_sha256":c["original_mask_sha256"],
            "source_spacing_mm":";".join(str(c[f]) for f in (
                 "source_voxel_spacing_x_mm","source_voxel_spacing_y_mm",
                 "source_voxel_spacing_z_mm")),
            "mask_voxels":c["mask_nonzero_voxel_count"],
            "mask_affine_corner_mm":c["image_mask_affine_corner_mm"],
            "baseline_native_bw25_glcm_contrast":round(float(base),9),
            "resampled_3mm_bw25_glcm_contrast":round(float(per),9),
            "signed_glcm_3mm_bw25_pct":round(float(delta),6),
            "absolute_glcm_3mm_bw25_pct":round(abs(float(delta)),6),
            "native_bw12_5_glcm_abs_pct":round(featnorm[("native",12.5)],6),
            "native_bw50_glcm_abs_pct":round(featnorm[("native",50.)],6),
            "analysis_status":"ORIGINAL_VENOUS_NIFTI_SOURCE_AND_MASK_GEOMETRY_TECHNICALLY_VERIFIED",
            "source_external_validation":"IMAGING_METHODS_DESCRIPTIVE_ONLY",
            "clinical_eligibility":"NOT_ASSESSED",
            "original_MRI_RNA_associations_executed":"NO","claim_ceiling":"S0"})
        featuremat.append(matrix)
    if len(records)+len(holds)!=59:
        raise ValueError("DID_NOT_ACCOUNT_FOR_ALL_59_HCC_PATIENTS")
    return records,np.stack(featuremat) if featuremat else np.empty((0,6,4))

def ranked(values):
    x=np.asarray(values,dtype=float)
    order=np.argsort(x,kind="stable");out=np.empty(len(x),dtype=float)
    k=0
    while k<len(x):
        j=k+1
        while j<len(x) and x[order[j]]==x[order[k]]:j+=1
        out[order[k:j]]=(k+1+j)/2.
        k=j
    return out
def spearman(x,y):
    a,b=ranked(x),ranked(y)
    if np.ptp(a)<1e-12 or np.ptp(b)<1e-12:return None
    return float(np.corrcoef(a,b)[0,1])

def distribution(matrix):
    n=matrix.shape[0]
    if n<DEFAULT_MIN_DESCRIPTIVE_N:
        return [],"HOLD_FEWER_THAN_10_GEOMETRICALLY_VALID_SUBJECTS"
    rng=np.random.default_rng(SEED)
    samples=rng.integers(0,n,size=(B,n))
    results=[]
    for fi,feat in enumerate(FEATURES):
        base=matrix[:,CONDITIONS.index(REFERENCE),fi]
        if np.any(np.abs(base)<1e-12):
            return [],"HOLD_ZERO_SOURCE_REFERENCE_FOR_FROZEN_FEATURE"
        for ci,(grid,bw) in enumerate(CONDITIONS):
            current=matrix[:,ci,fi]
            changes=(current-base)/np.abs(base)*100
            medabs=float(np.median(np.abs(changes)))
            resampled=np.median(np.abs(changes)[samples],axis=1)
            low,high=np.percentile(resampled,[2.5,97.5])
            rho=spearman(base,current)
            if rho is None and ci==CONDITIONS.index(REFERENCE):rho=1.
            rhos=[spearman(base[ix],current[ix]) for ix in samples]
            good=[x for x in rhos if x is not None and math.isfinite(x)]
            if len(good)<int(0.95*B):
                raise ValueError("UNSTABLE_SPEARMAN_BOOTSTRAP_TOO_FEW_VALID_DRAWS")
            rlo,rhi=np.percentile(good,[2.5,97.5])
            results.append({
                "feature":feat,"grid":grid,"binWidth":bw,
                "independent_technical_subjects":n,
                "bootstrap_seed":SEED,"bootstrap_resamples":B,
                "native25_reference":"SAME_NATIVE_VENOUS_IMAGE",
                "median_abs_pct":round(medabs,6),
                "median_abs_pct_bootstrap95_low":round(float(low),6),
                "median_abs_pct_bootstrap95_high":round(float(high),6),
                "median_signed_pct":round(float(np.median(changes)),6),
                "min_abs_pct":round(float(np.min(np.abs(changes))),6),
                "max_abs_pct":round(float(np.max(np.abs(changes))),6),
                "n_abs_pct_ge10":int(np.sum(np.abs(changes)>=10)),
                "n_abs_pct_ge20":int(np.sum(np.abs(changes)>=20)),
                "patient_rank_spearman":None if rho is None else round(rho,6),
                "patient_rank_spearman_bootstrap95_low":round(float(rlo),6),
                "patient_rank_spearman_bootstrap95_high":round(float(rhi),6),
                "valid_spearman_bootstraps":len(good),
                "no_hypothesis_p_value":"YES",
                "clinical_eligibility":"NOT_ASSESSED",
                "MRI_RNA_tests_executed":"NO",
                "claim_ceiling":"S0"})
    if len(results)!=24:raise ValueError("FROZEN_24_SOURCE_ONLY_EXTERNAL_CONDITIONS_INCOMPLETE")
    return results,"PASS_DESCRIPTIVE_EXTERNAL_VENOUS_SOURCE_METHODS_ONLY"

def write(path,columns,data):
    with path.open("w",encoding="utf8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=columns)
        w.writeheader();w.writerows(data)

def plot(dest,records,stats):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    vals=sorted((float(r["absolute_glcm_3mm_bw25_pct"]),r["patient_id"]) for r in records)
    fig,ax=plt.subplots(figsize=(12,5))
    ax.plot(range(1,len(vals)+1),[a for a,_ in vals],marker="o",lw=1.6,ms=3.2)
    ax.set_xlabel("Independent source-qualified OpenSwissHCC HCC subject (ascending sensitivity rank)")
    ax.set_ylabel("Absolute GLCM Contrast change, native→3mm (binWidth 25), %")
    ax.set_title(f"External original portal venous MRI: {len(vals)} independent technical subjects")
    ax.grid(alpha=.2)
    fig.tight_layout()
    fig.savefig(dest/"external_openswisshcc_venous_glcm_ranked_source_sensitivity.png",dpi=180)
    plt.close(fig)
    fig,ax=plt.subplots(figsize=(8,6))
    x=[float(r["baseline_native_bw25_glcm_contrast"]) for r in records]
    y=[float(r["resampled_3mm_bw25_glcm_contrast"]) for r in records]
    ax.scatter(x,y,alpha=.75)
    mx=max(x+y)
    ax.plot([0,mx],[0,mx],linestyle="--",color="gray",linewidth=1)
    ax.set_xlabel("Original venous MRI native spacing, binWidth25 GLCM Contrast")
    ax.set_ylabel("Same venous MRI resampled 3mm, binWidth25 GLCM Contrast")
    ax.set_title("Matched within-source MRI technical effects; not a clinical HCC biomarker")
    ax.grid(alpha=.2)
    fig.tight_layout()
    fig.savefig(dest/"external_openswisshcc_glcm_native_vs_3mm_same_image.png",dpi=180)
    plt.close(fig)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--offline-test",action="store_true")
    ap.add_argument("--source-primary-zip",type=Path)
    ap.add_argument("--shard-dir",type=Path)
    ap.add_argument("--out-dir",type=Path,default=Path("artifacts/openswiss_hcc_59cohort_aggregate"))
    args=ap.parse_args()
    if args.offline_test:
        assert spearman([1,2,3,4],[4,3,2,1])==-1.
        assert spearman([1,2,3,4],[1,2,3,4])==1.
        assert len(CONDITIONS)==6 and len(FEATURES)==4 and B==4000
        sample=np.array([[[float(i+1)*(j+1)*(k+1) for k in range(4)]
                           for j in range(6)] for i in range(14)],dtype=float)
        stats,state=distribution(sample)
        assert state.startswith("PASS_") and len(stats)==24
        assert all(row["median_abs_pct"]==0 for row in stats if row["grid"]=="native" and float(row["binWidth"])==25.)
        assert all(row["claim_ceiling"]=="S0" for row in stats)
        _,state=distribution(sample[:9])
        assert state.startswith("HOLD_")
        print("HCC_OPENSWISS_SOURCE_N59_15_SHARD_AGGREGATOR_NEGATIVE_FIXTURE_PASS")
        return
    if args.source_primary_zip is None or args.shard_dir is None:
        raise ValueError("ORIGINAL_59_SOURCE_PRIMARY_AND_15_SHARD_RECORDS_REQUIRED")
    original=origin_manifest(args.source_primary_zip)
    allrows,holds,manifests=source_rows(args.shard_dir,original)
    records,matrix=verify_and_quantify(original,allrows,holds)
    stats,technical_status=distribution(matrix)
    args.out_dir.mkdir(parents=True,exist_ok=True)
    write(args.out_dir/"external_venous_59_primary_patient_source_profiles.csv",QC_COLUMNS,records)
    write(args.out_dir/"external_venous_59_source_case_level_HOLD.csv",list(holds[0]) if holds else (
        "patient_id","selected_lesion","source_archive","error_type",
        "error_message","source_mask_path","radiomics_extracted",
        "clinical_eligibility","claim_ceiling"),holds)
    write(args.out_dir/"external_venous_59_primary_6_condition_4_feature_extraction.csv",list(allrows[0]) if allrows else (
        "patient_id","grid","binWidth","claim_ceiling"),allrows)
    write(args.out_dir/"external_venous_24_feature_condition_patient_bootstrap_ci.csv",STATS_COLUMNS,stats)
    summary={
      "status":technical_status,
      "source":"OpenSwissHCC v2 Zenodo 21992461",
      "discovery_cohort":"LiverHccSeg v1.1 n14",
      "external_source_independent_subject_candidates":59,
      "original_venous_HCC_manual_mask_candidates":90,
      "original_HCC_primary_source_artifact":SOURCE_ARTIFACT_ID,
      "first_4_subject_verified_shard_artifact":13049338566,
      "succeeded_source_matched_venous_n":len(records),
      "HOLD_source_geometry_or_extraction_n":len(holds),
      "source_accounting_n":len(records)+len(holds),
      "source_HOLD_reasons":dict(Counter(x["error_type"] for x in holds)),
      "source_extraction_rows":len(allrows),
      "feature_condition_statistics":len(stats),
      "analysis_unit":"one independent subject, largest published HCC lesion with genuine venous mask",
      "source_phase":"ORIGINAL_NATIVE_VENOUS_WATER_NOT_LIVERHCCSEG_ARTERIAL_REGISTERED_PV",
      "main_effect":"per-patient absolute 3mm/25 vs native/25 GLCM Contrast source percentage change",
      "bootstrap_resamples":B,"bootstrap_seed":SEED,
      "eligible_radiogenomics_n":"NOT_ASSESSED",
      "same_lesion_RNA_link":"NOT_ASSESSED",
      "qualified_image_anatomy_review":"NOT_ASSESSED",
      "two_reader_ICC_performed":False,
      "MRI_RNA_12_tests":"NOT_EXECUTED",
      "clinical_predictive_utility":"NOT_ASSESSED",
      "external_validity_claim":"DESCRIPTIVE_PREPROCESSING_SENSITIVITY_ONLY",
      "claim_ceiling":"S0",
      "glcm_3mm25":next((x for x in stats if x["feature"]=="original_glcm_Contrast" and x["grid"]=="3mm" and float(x["binWidth"])==25.),None)
    }
    (args.out_dir/"external_venous_59_primary_source_technical_summary.json").write_text(
        json.dumps(summary,ensure_ascii=False,indent=2)+"\n")
    if stats:plot(args.out_dir,records,stats)
    print("OPEN_SWISS_EXTERNAL_N59_ORIGINAL_VENOUS_SOURCE_COHORT_RESULT",json.dumps(summary),flush=True)

if __name__=="__main__":main()
