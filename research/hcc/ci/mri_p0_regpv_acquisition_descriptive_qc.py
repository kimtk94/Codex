#!/usr/bin/env python3
"""Descriptive HCC n14 registered MRI voxel-spacing / contrast-agent sensitivity.

Exact official registered ART_PV NIfTI source headers are measured independently
in 7 shards. 14-case patient-level GLCM effects are drawn ONLY from the four
SHA256-validated original 168-row PyRadiomics source members. The published
contrast-agent labels are study-level, not matched exact selected PV series.

Exploratory engineering QC: no p-values, hypothesis testing, adjustment,
ComBat, RNA, clinical inclusion/exclusion or biological correlations.
"""
import argparse,csv,json,math,statistics
from collections import Counter
from pathlib import Path
from scipy.stats import spearmanr

from mri_phase_mask_source_gate import frozen
from mri_p0_registered_pv_factorial_patient_bootstrap import checked_source
from mri_p0_registered_pv_exact_header_audit import verify as check_header

ROOT=Path("research/hcc")
AGENT=ROOT/"HCC_MRI_14_PUBLISHED_FIELDSTRENGTH_CONTRAST_20261031.csv"
OLD=ROOT/"HCC_MRI_14_PV_NATIVE_SPACING_QC_20261031.csv"
GLCM="original_glcm_Contrast"
SPACING_COLS=("registered_voxel_spacing_z_mm","registered_inplane_mean_mm",
              "registered_z_inplane_anisotropy_ratio",
              "registered_z_minus_target_3mm_abs_mm",
              "historical_raw_pv_z_mm")
OUTCOME_COLS=("glcm_3mm25_abs_change_pct","glcm_3mm25_signed_change_pct",
              "glcm_native12_5_abs_change_pct","glcm_3mm50_abs_change_pct")
FIELDS=("patient_id","index_tumor","official_regpv_source_sha256",
 "registered_spacing_x_mm","registered_spacing_y_mm","registered_voxel_spacing_z_mm",
 "registered_inplane_mean_mm","registered_z_inplane_anisotropy_ratio",
 "registered_z_minus_target_3mm_abs_mm","registered_vs_historical_raw_z_diff_mm",
 "historical_raw_pv_z_mm","published_study_field_strength_T",
 "published_study_contrast_category","published_study_contrast_label",
 "published_acquisition_metadata_not_verified_for_exact_art_pv",
 "glcm_native25_rater_mean","glcm_3mm25_rater_mean",
 "glcm_3mm25_abs_change_pct","glcm_3mm25_signed_change_pct",
 "glcm_native12_5_abs_change_pct","glcm_3mm50_abs_change_pct",
 "possible_acquisition_outlier_flag","qualified_image_review",
 "MRI_RNA_association_tests","clinical_eligibility","claim_ceiling")
ASSOC_FIELDS=("covariate","descriptive_feature_change","n_independent_patients",
              "spearman_rho","leave_one_patient_out_min_rho",
              "leave_one_patient_out_max_rho","no_p_value_or_significance_claim",
              "clinical_eligibility","claim_ceiling")
AGENT_FIELDS=("published_study_contrast_category","n","feature_change",
              "median_change_pct","min_change_pct","max_change_pct",
              "source_is_study_level_only","claim_ceiling")

def read(path):
    with path.open(newline="",encoding="utf8") as f:
        return list(csv.DictReader(f))

def one(rows):
    result={}
    for row in rows:
        pid=row["patient_id"]
        if pid in result:raise ValueError("DUPLICATE_PATIENT_SOURCE_METADATA")
        result[pid]=row
    return result

def header_shards(directory):
    result=[]
    for shard in range(7):
        f=directory/f"hcc_registered_header_shard_{shard}.csv"
        j=directory/f"hcc_registered_header_shard_{shard}.json"
        rows=read(f)
        ids=check_header(rows,shard)
        meta=json.loads(j.read_text())
        if (meta["shard"]!=shard or meta["patients"]!=ids or meta["n_cases"]!=2
            or meta["source_phase"]!="reoriented_art_pv"
            or meta["claim_ceiling"]!="S0" or meta["clinical_eligibility"]!="NOT_ASSESSED"):
            raise ValueError("OFFICIAL_NIFTI_HEADER_SHARD_PROVENANCE_DRIFT")
        result+=rows
    if len(result)!=14 or set(one(result))!=set(frozen()):
        raise ValueError("MISSING_OFFICIAL_REGISTERED_NIFTI_PATIENT_HEADER")
    return one(result)

def rank(x,y):
    a=float(spearmanr(x,y).statistic)
    if not math.isfinite(a):raise ValueError("UNDEFINED_SPACING_GLCM_RANK")
    return a

def make_rows(header,source_rows,meta):
    ids=sorted(frozen())
    lookup={}
    for r in source_rows:
        k=(r["patient_id"],r["rater"],r["grid"],float(r["bin_width"]))
        if k in lookup:raise ValueError("DUPLICATE_ORIGINAL_168_SOURCE_ROW")
        lookup[k]=r
    if len(lookup)!=168 or set(header)!=set(ids):
        raise ValueError("ORIGINAL_FACTORIAL_OR_HEADER_PATIENT_UNIVERSE_CHANGED")
    agent=one(read(AGENT));old=one(read(OLD))
    if set(agent)!=set(ids) or set(old)!=set(ids):
        raise ValueError("PUBLISHED_METADATA_OR_ORIGINAL_PV_SPACING_MISSING")
    def get(pid,grid,bw):
        pair=[lookup[(pid,r,grid,float(bw))] for r in ("rater1","rater2")]
        return sum(float(x[GLCM]) for x in pair)/2
    out=[]
    for pid in ids:
        h=header[pid];o=old[pid];a=agent[pid]
        if int(h["selected_tumor"])!=frozen()[pid]:
            raise ValueError("FROZEN_TUMOR_SELECTED_DIFFERENTLY")
        for reader in ("rater1","rater2"):
            raw=lookup[(pid,reader,"native",25.)]
            if (raw["source_sha256"]!=h["registered_art_pv_sha256"] or
                raw["official_source_phase"]!="reoriented_art_pv"):
                raise ValueError("ACTUAL_REGISTERED_IMAGE_SHA_NOT_SAME_AS_168_SOURCE_EXPERIMENT")
            if reader=="rater1" and raw["mask_sha256"]!=h["reader1_mask_sha256"]:
                raise ValueError("ACTUAL_SOURCE_MASK_SHA_NOT_SAME_AS_168_SOURCE_EXPERIMENT")
        if h["claim_ceiling"]!="S0" or h["qualified_anatomical_review"]!="NOT_ASSESSED":
            raise ValueError("UNAUTHORIZED_EXPERT_ANATOMY_PASS")
        if o["source_phase"]!="PV" or o["clinical_eligibility"]!="NOT_ASSESSED":
            raise ValueError("HISTORICAL_RAW_PV_SOURCE_CHANGED")
        if a["verified_exact_pv_series_scanner"]!="NOT_VERIFIED" or a["verified_patient_pretreatment_mri"]!="NOT_VERIFIED":
            raise ValueError("MISATTRIBUTED_PUBLISHED_SCANNER_CLINICAL_CERTIFICATION")
        if float(a["study_magnetic_field_strength_t"])!=1.5:
            raise ValueError("PUBLISHED_FIELD_STRENGTH_CHANGED")
        cat=a["source_contrast_agent_category"]
        if cat not in ("Extracellular","Hepatobiliary-specific","not avaliable"):
            raise ValueError("UNKNOWN_PUBLIC_STUDY_CONTRAST_LABEL")
        base=get(pid,"native",25.)
        if base==0:raise ValueError("GLCM_REF_ZERO")
        shift25=(get(pid,"3mm",25.)-base)/abs(base)*100
        z=float(h["registered_voxel_spacing_z_mm"])
        rawz=float(o["voxel_spacing_z_mm"])
        row={
          "patient_id":pid,"index_tumor":frozen()[pid],
          "official_regpv_source_sha256":h["registered_art_pv_sha256"],
          "registered_spacing_x_mm":h["registered_voxel_spacing_x_mm"],
          "registered_spacing_y_mm":h["registered_voxel_spacing_y_mm"],
          "registered_voxel_spacing_z_mm":z,
          "registered_inplane_mean_mm":h["registered_inplane_mean_mm"],
          "registered_z_inplane_anisotropy_ratio":h["registered_z_inplane_anisotropy_ratio"],
          "registered_z_minus_target_3mm_abs_mm":h["registered_z_minus_target_3mm_abs_mm"],
          "registered_vs_historical_raw_z_diff_mm":round(z-rawz,6),
          "historical_raw_pv_z_mm":rawz,
          "published_study_field_strength_T":1.5,
          "published_study_contrast_category":cat,
          "published_study_contrast_label":a["source_contrast_agent_name"],
          "published_acquisition_metadata_not_verified_for_exact_art_pv":"YES",
          "glcm_native25_rater_mean":round(base,8),
          "glcm_3mm25_rater_mean":round(get(pid,"3mm",25.),8),
          "glcm_3mm25_abs_change_pct":round(abs(shift25),6),
          "glcm_3mm25_signed_change_pct":round(shift25,6),
          "glcm_native12_5_abs_change_pct":round(abs((get(pid,"native",12.5)-base)/abs(base)*100),6),
          "glcm_3mm50_abs_change_pct":round(abs((get(pid,"3mm",50.)-base)/abs(base)*100),6),
          "possible_acquisition_outlier_flag":"HISTORICAL_RAW_Z_GE_5MM" if rawz>=5 else "NONE",
          "qualified_image_review":"NOT_ASSESSED",
          "MRI_RNA_association_tests":"NOT_EXECUTED",
          "clinical_eligibility":"NOT_ASSESSED","claim_ceiling":"S0"}
        out.append(row)
    if len(out)!=14 or sum(x["possible_acquisition_outlier_flag"]!="NONE" for x in out)!=1:
        raise ValueError("OUTLIER_COHORT_ORIGINAL_14_POLICY_CHANGED")
    if Counter(r["published_study_contrast_category"] for r in out)!={
       "Extracellular":7,"Hepatobiliary-specific":4,"not avaliable":3}:
        raise ValueError("SMALL_CONTRAST_STUDY_CATEGORIES_CHANGED")
    if meta["original_registered_native_bw25_feature_checks"]!=112 or meta["claim_ceiling"]!="S0":
        raise ValueError("SOURCE_NATIVE_BW25_REFERENCE_CHANGED")
    return out

def descriptive_stats(rows):
    assoc=[]
    for factor in SPACING_COLS:
        x=[float(row[factor]) for row in rows]
        if len(set(x))<2:raise ValueError("UNIDENTIFIABLE_CONSTANT_COVARIATE")
        for outcome in OUTCOME_COLS:
            y=[float(row[outcome]) for row in rows]
            whole=rank(x,y)
            loo=[rank(x[:i]+x[i+1:],y[:i]+y[i+1:]) for i in range(14)]
            assoc.append({
              "covariate":factor,"descriptive_feature_change":outcome,
              "n_independent_patients":14,
              "spearman_rho":round(whole,6),
              "leave_one_patient_out_min_rho":round(min(loo),6),
              "leave_one_patient_out_max_rho":round(max(loo),6),
              "no_p_value_or_significance_claim":"YES",
              "clinical_eligibility":"NOT_ASSESSED","claim_ceiling":"S0"})
    groups=[]
    for label in ("Extracellular","Hepatobiliary-specific","not avaliable"):
        members=[r for r in rows if r["published_study_contrast_category"]==label]
        for outcome in OUTCOME_COLS:
            y=[float(r[outcome]) for r in members]
            groups.append({"published_study_contrast_category":label,
               "n":len(members),"feature_change":outcome,
               "median_change_pct":round(statistics.median(y),6),
               "min_change_pct":round(min(y),6),
               "max_change_pct":round(max(y),6),
               "source_is_study_level_only":"YES","claim_ceiling":"S0"})
    if len(assoc)!=20 or len(groups)!=12:
        raise ValueError("EXPECTED_20_DESCRIPTIVE_RANK_AND_12_CONTRAST_GROUP_QC_ROWS")
    return assoc,groups

def write(path,rows,columns):
    with path.open("w",newline="",encoding="utf8") as f:
        w=csv.DictWriter(f,fieldnames=columns)
        w.writeheader();w.writerows(rows)

def fixture():
    assert len(frozen())==14 and frozen()["TCGA-BC-A10Y"]==3
    x=[1,2,3,4]
    assert rank(x,x)==1.0 and rank(x,list(reversed(x)))==-1.
    assert "Hepatobiliary-specific" in ("Extracellular","Hepatobiliary-specific","not avaliable")
    fake=[]
    for i in range(14):
        fake.append({k:float(i+1) for k in SPACING_COLS+OUTCOME_COLS}
                    |{"published_study_contrast_category":(
                       "Extracellular" if i<7 else "Hepatobiliary-specific" if i<11 else "not avaliable")})
    a,b=descriptive_stats(fake)
    assert len(a)==20 and len(b)==12
    assert all(r["no_p_value_or_significance_claim"]=="YES" for r in a)
    print("HCC_REGISTERED_PV_VOXEL_SPACING_DESCRIPTIVE_14PATIENT_20RANK_12GROUP_FIXTURE_PASS")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--offline-test",action="store_true")
    p.add_argument("--header-shard-dir",type=Path)
    p.add_argument("--source-168-zip",type=Path)
    p.add_argument("--out-dir",type=Path,default=Path("artifacts/hcc_regpv_acquisition_exploratory"))
    a=p.parse_args()
    if a.offline_test:return fixture()
    if not a.header_shard_dir or not a.source_168_zip:
        raise ValueError("EXACT_SOURCE_HEADERS_AND_ORIGINAL_168ROWS_REQUIRED")
    header=header_shards(a.header_shard_dir)
    source,metrics,meta=checked_source(a.source_168_zip)
    cases=make_rows(header,source,meta)
    assoc,groups=descriptive_stats(cases)
    out=a.out_dir;out.mkdir(parents=True,exist_ok=True)
    write(out/"hcc_regpv_14_patient_exact_spacing_glcm_and_agent.csv",cases,FIELDS)
    write(out/"hcc_regpv_20_spacing_glcm_spearman_descriptive_loo.csv",assoc,ASSOC_FIELDS)
    write(out/"hcc_regpv_12_published_study_contrast_group_descriptives.csv",groups,AGENT_FIELDS)
    summary={
        "status":"SOURCE_ENGINEERING_EXPLORATORY_ASSOCIATIONS_DESCRIPTIVE_ONLY",
        "n_technical_cases":14,"n_mri_extraction_rows":168,
        "n_exact_official_art_pv_source_headers":14,
        "n_descriptive_spearman_loo_combinations":20,
        "n_study_level_agent_group_descriptors":12,
        "original_factorial_reference_values_reproduced":112,
        "published_field_strength_1_5T_all14_no_variance":True,
        "scanner_vendor_for_exact_pv_series":"NOT_VERIFIED",
        "contrast_agent_for_exact_pv_series":"NOT_VERIFIED",
        "study_level_contrast_group_sizes":{"Extracellular":7,"Hepatobiliary-specific":4,"not avaliable":3},
        "historical_raw_PV_spacing_is_not_official_registered_PV_spacing":True,
        "MRI_RNA_12_tests":"NOT_EXECUTED",
        "qualified_anatomical_review":"NOT_ASSESSED",
        "clinical_eligibility":"NOT_ASSESSED","claim_ceiling":"S0",
        "method":"no covariate pvalues; Spearman rho with 14 leave-one-patient-out sensitivity estimates; descriptive median/range agent groups",
        "reg_z_min_mm":min(float(r["registered_voxel_spacing_z_mm"]) for r in cases),
        "reg_z_max_mm":max(float(r["registered_voxel_spacing_z_mm"]) for r in cases),
        "glcm_3mm_abs_change_median_pct":statistics.median(float(r["glcm_3mm25_abs_change_pct"]) for r in cases),
        "rank_samples":assoc}
    (out/"hcc_regpv_acquisition_descriptive_summary.json").write_text(json.dumps(summary,indent=2)+"\n")
    print("HCC_REGPV_ACTUAL_HEADER_14_PATIENT_SPACING_20RANK_12AGENT_DESCRIPTIVES_PASS",
          json.dumps({"z_range":[summary["reg_z_min_mm"],summary["reg_z_max_mm"]],
              "contrast_groups":summary["study_level_contrast_group_sizes"],
              "GLCM_3mm_abs_median":summary["glcm_3mm_abs_change_median_pct"],
              "clinical_eligibility":"NOT_ASSESSED","claim_ceiling":"S0"}),flush=True)
if __name__=="__main__":main()
