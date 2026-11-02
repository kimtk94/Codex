#!/usr/bin/env python3
"""Stage50 frozen-source MRI acquisition and ROI influence audit.

Using Stage49 original full14 rater1 nativePV->3mm rank measurements (CI
#41448904879), repository 14-person original native slice spacing / native
rater1 ROI volumes (CI #41161863748), and original native PV external 59
OpenSwissHCC cases (CI #41221356861).

All checks are POST-RESULTS exploratory and descriptive. Thick slice A10Y is
an influence sensitivity case, never silently excluded from the primary n14.
Cohorts have different acquisition/mask sources. No causal effect, clinical
claims or MRI-RNA tests.
"""
import argparse,csv,json,math,os,statistics
from collections import Counter
from pathlib import Path
from mri14_stage49_native_rater1_spearman import spearman,ranks

ROOT=Path(__file__).resolve().parents[1]
INTERNAL=ROOT/"HCC_MRI_PV_14_NATIVE_3MM_ROI_VOLUME_AND_PRIMARY_FEATURE_CHANGE_20261031.csv"
EXTERNAL=ROOT/"HCC_EXTERNAL_OPENSWISSHCC_V2_59_INDEX_PATIENT_GLCM_NATIVE3MM_FROZEN_20261101.csv"
FLAGGED="TCGA-BC-A10Y"
FIELDS=(
 "cohort","patient_id","source_index_lesion","native_throughplane_spacing_mm",
 "native_mask_volume_ml","original_native_glcm_contrast","resampled_3mm_glcm_contrast",
 "absolute_native_to3mm_glcm_change_pct","original_native_patient_rank",
 "resampled_patient_rank","absolute_patient_rank_displacement",
 "source_mask_or_rater","source_run","record_posthoc_thick_slice_sensitivity_only",
 "source_clinical_eligible","MRI_RNA_biological_tests","claim_ceiling")
CORR_FIELDS=("cohort","source_n","geometry_parameter","outcome","Spearman_rho",
             "leave_one_patient_out_rho_low","leave_one_patient_out_rho_high",
             "parameter_constant","posthoc_exploratory_only","clinical_claim_level")
PAIRS=(
 ("native_throughplane_spacing_mm","absolute_native_to3mm_glcm_change_pct"),
 ("native_throughplane_spacing_mm","absolute_patient_rank_displacement"),
 ("native_mask_volume_ml","absolute_native_to3mm_glcm_change_pct"),
 ("native_mask_volume_ml","absolute_patient_rank_displacement")
)

def require(flag,code):
    if not flag: raise ValueError(code)

def records(path):
    require(path.is_file(),"FROZEN_SOURCE_FILE_MISSING:"+str(path))
    with path.open(newline="",encoding="utf8") as f:return list(csv.DictReader(f))

def finite(v,positive=False):
    x=float(v)
    require(math.isfinite(x) and (x>0 if positive else True),"SOURCE_NONFINITE_OR_NONPOSITIVE")
    return x

def med(values):
    return statistics.median(values)

def dataset(rows,mask,source,patient_field="patient_id"):
    require(len(rows)==len(mask)==len(source) and len(rows)>4,"SOURCE_COHORT_ROSTER_N_CHANGED")
    ids=sorted({r[patient_field] for r in rows})
    require(len(ids)==len(rows) and ids==sorted(mask) and ids==sorted(source),
            "SOURCE_COHORT_INVALID_PATIENT_IDENTITY")
    return ids

def internal(rows,case_rows,stage49_summary):
    cases={r["patient_id"]:r for r in case_rows}
    source={r["patient_id"]:r for r in rows}
    ids=dataset(rows,cases,source)
    require(len(ids)==14 and FLAGGED in source,"INTERNAL_14_FROZEN_SOURCE_CHANGED")
    require(stage49_summary["frozen_original_selected_tumor_patient_n"]==14 and
            stage49_summary["original_full_feature_pairs"]==28 and
            stage49_summary["clinical_eligible_n"]=="NOT_ASSESSED" and
            stage49_summary["MRI_RNA_biology_tests"]==0 and
            stage49_summary["claim_ceiling"]=="S0","STAGE49_ORIGINAL_SOURCE_STATUS_CHANGED")
    out=[]
    for pid in ids:
        row=source[pid];case=cases[pid]
        require(row["patient_id"]==pid and row["source_reader"]=="rater1" and
                row["index_tumor"]==case["tumor_number"],
                "SOURCE_RATER1_OR_FROZEN_INDEX_LESION_CHANGED:"+pid)
        require(row["clinical_eligibility"]=="NOT_ASSESSED" and
                row["claim_ceiling"]=="S0" and
                row["MRI_RNA_biological_tests"]=="0",
                "STAGE49_ORIGINAL_PATIENT_FALSE_CLINICAL_GO:"+pid)
        require(case["clinical_eligibility"]=="HOLD_UNRESOLVED_NOT_EXCLUDED",
                "STAGE14_SOURCE_CLINICAL_STATUS_CHANGED:"+pid)
        z=finite(case["native_z_mm"],True)
        volume=finite(case["rater1_roi_volume_native_ml"],True)
        native=finite(row["native_glcm_contrast"],True)
        new=finite(row["resampled_3mm_glcm_contrast"],True)
        pct=100*abs(new-native)/abs(native)
        require(abs(pct-float(row["absolute_relative_change_pct"]))<.00001,
                "SOURCE_STAGE49_PAIRED_GLCM_VALUES_CHANGED:"+pid)
        require(abs(pct/100-float(case["glcm_contrast_rater1_absolute_relative_change"]))<.000003,
                "ORIGINAL_INTERNAL_14_SOURCE_PERCENTAGE_CHANGED:"+pid)
        if pid==FLAGGED:
            require(abs(z-10.8)<.00001 and case["native_high_anisotropy"]=="YES"
                    and float(row["absolute_rank_displacement"])==6.0,
                    "ORIGINAL_HIGH_THICKNESS_A10Y_SOURCE_QC_CHANGED")
        else:
            require(case["native_high_anisotropy"]=="NO",
                    "NEW_HIGH_ANISOTROPY_PATIENT_SOURCE_REVIEW_REQUIRED:"+pid)
        out.append(dict(cohort="TCGA_LIHC_native_PV_original_rater1",
            patient_id=pid,source_index_lesion=row["index_tumor"],
            native_throughplane_spacing_mm=z,native_mask_volume_ml=volume,
            original_native_glcm_contrast=native,resampled_3mm_glcm_contrast=new,
            absolute_native_to3mm_glcm_change_pct=pct,
            original_native_patient_rank=float(row["native_rank_average_ties"]),
            resampled_patient_rank=float(row["resampled_rank_average_ties"]),
            absolute_patient_rank_displacement=float(row["absolute_rank_displacement"]),
            source_mask_or_rater="published_original_rater1",
            source_run=41161863748,
            record_posthoc_thick_slice_sensitivity_only="YES" if pid==FLAGGED else "NO",
            source_clinical_eligible="NOT_ASSESSED",MRI_RNA_biological_tests=0,claim_ceiling="S0"))
    nr=[r["original_native_glcm_contrast"] for r in out]
    ns=[r["resampled_3mm_glcm_contrast"] for r in out]
    orig=ranks(nr);new=ranks(ns)
    for r,a,b in zip(out,orig,new):
        require(abs(r["original_native_patient_rank"]-a)<1e-9 and
                abs(r["resampled_patient_rank"]-b)<1e-9 and
                abs(r["absolute_patient_rank_displacement"]-abs(a-b))<1e-9,
                "PATIENT_NATIVE_VS_3MM_RANKS_NOT_RECALCULATED:"+r["patient_id"])
    r14=spearman(nr,ns)
    require(r14 is not None and
            abs(r14-stage49_summary["internal_original_rater1_rank_rho"])<1e-10,
            "STAGE49_ORIGINAL_14_RANK_RHO_SOURCE_DRIFT")
    return out

def external(rows,stage49_summary):
    require(len(rows)==59 and len({r["subject"] for r in rows})==59,
            "EXTERNAL_59_ORIGINAL_SUBJECT_ROSTER_CHANGED")
    out=[]
    for r in sorted(rows,key=lambda x:x["subject"]):
        pid=r["subject"]
        require(r["original_source_run"]=="41221356861" and
                r["claim_ceiling"]=="S0" and r["selected_HCC_lesion"].startswith("L"),
                "EXTERNAL_ORIGINAL_PV_SOURCE_OR_CLAIM_CHANGED:"+pid)
        spacing=[finite(x,True) for x in r["source_voxel_spacing_xyz_mm"].split("|")]
        require(len(spacing)==3,"EXTERNAL_SOURCE_SPACING_TRIPLE_MISSING:"+pid)
        volume=finite(r["source_mask_voxels"],True)*math.prod(spacing)/1000.0
        a=finite(r["original_native25_GLCM_Contrast"],True)
        b=finite(r["resampled_3mm25_GLCM_Contrast"],True)
        pct=100*abs(b-a)/a
        require(abs(pct-abs(float(r["signed_change_pct"])))<.002,
                "EXTERNAL_SOURCE_GLCM_PERCENT_CHANGE_NOT_REPRODUCED:"+pid)
        out.append(dict(cohort="OpenSwissHCC_original_venous_index",
            patient_id=pid,source_index_lesion=r["selected_HCC_lesion"],
            native_throughplane_spacing_mm=spacing[2],native_mask_volume_ml=volume,
            original_native_glcm_contrast=a,resampled_3mm_glcm_contrast=b,
            absolute_native_to3mm_glcm_change_pct=pct,
            original_native_patient_rank=0.0,resampled_patient_rank=0.0,
            absolute_patient_rank_displacement=0.0,
            source_mask_or_rater="published_original_primary",
            source_run=41221356861,
            record_posthoc_thick_slice_sensitivity_only="NO",
            source_clinical_eligible="NOT_ASSESSED",MRI_RNA_biological_tests=0,claim_ceiling="S0"))
    orig=ranks([r["original_native_glcm_contrast"] for r in out])
    dest=ranks([r["resampled_3mm_glcm_contrast"] for r in out])
    for r,x,y in zip(out,orig,dest):
        r["original_native_patient_rank"]=x
        r["resampled_patient_rank"]=y
        r["absolute_patient_rank_displacement"]=abs(y-x)
    rho=spearman([r["original_native_glcm_contrast"] for r in out],
                 [r["resampled_3mm_glcm_contrast"] for r in out])
    require(rho is not None and abs(rho-stage49_summary["external_original_primary_mask_rank_rho"])<1e-10,
            "EXTERNAL_STAGE49_FROZEN_RANK_SOURCE_CHANGED")
    return out

def correlation(rows,a,b):
    av=[float(r[a]) for r in rows];bv=[float(r[b]) for r in rows]
    full=spearman(av,bv)
    loo=[]
    for j in range(len(rows)):
        ca=av[:j]+av[j+1:];cb=bv[:j]+bv[j+1:]
        x=spearman(ca,cb)
        if x is not None:loo.append(x)
    return dict(cohort=rows[0]["cohort"],source_n=len(rows),geometry_parameter=a,
        outcome=b,Spearman_rho=full,
        leave_one_patient_out_rho_low=min(loo) if loo else None,
        leave_one_patient_out_rho_high=max(loo) if loo else None,
        parameter_constant=full is None,
        posthoc_exploratory_only=True,
        clinical_claim_level="S0")

def leave_out(rows,patient):
    reduced=[r for r in rows if r["patient_id"]!=patient]
    require(len(reduced)==len(rows)-1,"LEAVE_ONE_OUT_DID_NOT_REMOVE_EXACTLY_ONE")
    return reduced

def build(stage49_csv,stage49_json):
    s49=json.loads(Path(stage49_json).read_text())
    a=internal(records(stage49_csv),records(INTERNAL),s49)
    b=external(records(EXTERNAL),s49)
    require(len(a)==14 and len(b)==59,"STAGE50_COHORT_DENOMINATOR_DRIFT")
    main14=s49["internal_original_rater1_rank_rho"]
    main59=s49["external_original_primary_mask_rank_rho"]
    reduced=leave_out(a,FLAGGED)
    no_high=spearman([r["original_native_glcm_contrast"] for r in reduced],
                     [r["resampled_3mm_glcm_contrast"] for r in reduced])
    require(no_high is not None,"POSTHOC_A10Y_LOO_SPEARMAN_NOT_IDENTIFIABLE")
    require(s49["internal_rater1_leave_one_patient_out_rho_range"][0]-1e-8<=no_high<=
            s49["internal_rater1_leave_one_patient_out_rho_range"][1]+1e-8,
            "A10Y_LOO_NOT_WITHIN_FROZEN_STAGE49_JACKKNIFE")
    z=[r["native_throughplane_spacing_mm"] for r in a]
    vol=[r["native_mask_volume_ml"] for r in a]
    original_median=med([r["absolute_native_to3mm_glcm_change_pct"] for r in a])
    reduced_median=med([r["absolute_native_to3mm_glcm_change_pct"] for r in reduced])
    require(abs(original_median-74.8808)<.005,"ORIGINAL_N14_MEDIAN_DRIFT")
    require(abs(med([r["absolute_native_to3mm_glcm_change_pct"] for r in b])-64.635863)<.005,
            "ORIGINAL_N59_MEDIAN_DRIFT")
    correlations=[correlation(group,x,y) for group in (a,b) for x,y in PAIRS]
    summary=dict(stage="HCC_STAGE50_SOURCE_FROZEN_ACQUISITION_ROI_RANK_INFLUENCE",
      original_stage49_artifact_run_id=41448904879,
      original_stage49_full28_feature_source_run_id=41161863748,
      independent_patients_internal_n=14,
      independent_patients_external_n=59,
      original_14_rater1_full_rho=main14,
      original_external59_primary_mask_full_rho=main59,
      original_14_full_cohort_median_abs_pct=original_median,
      original_external59_full_cohort_median_abs_pct=med([r["absolute_native_to3mm_glcm_change_pct"] for r in b]),
      preidentified_source_high_thickness_case=FLAGGED,
      source_high_thickness_patient_z_mm=10.8,
      original_14_z_mm_median=med(z),
      original_14_other13_z_mm_max=max(r["native_throughplane_spacing_mm"] for r in reduced),
      original_14_native_rater1_roi_volume_ml_median=med(vol),
      source_A10Y_native_rater1_roi_volume_ml=next(r["native_mask_volume_ml"] for r in a if r["patient_id"]==FLAGGED),
      source_A10Y_abs_patient_rank_displacement=6,
      internal_13_no_A10Y_original_native_rater1_Spearman_rho=no_high,
      internal_13_no_A10Y_median_abs_change_pct=reduced_median,
      change_in_rho_after_A10Y_removal=no_high-main14,
      change_in_median_abs_change_pct_after_A10Y_removal=reduced_median-original_median,
      internal_external_source_provenance_independent=True,
      correlations_reported_posthoc_exploratory=True,
      high_thickness_case_is_posthoc_sensitivity_not_default_exclusion=True,
      all14_primary_technical_patients_retained=True,
      statistical_significance_pvalues_tested=False,
      multiplicity_adjusted_discovery_claims=False,
      external_roi_physical_volume_derived_from_mask_voxel_count_and_native_spacing=True,
      no_original_image_download_or_reextraction=True,
      same_acquisition_or_segmentation_protocol_between_cohorts_proven=False,
      scanner_causal_effect_tested=False,
      actual_MRI_test_retest_scans_verified=0,
      no_new_radiologist_index_lesion_review=True,
      MRI_before_HCC_treatment_verified_n=0,
      exact_MRI_index_lesion_to_RNA_aliquot_verified_n=0,
      clinical_eligible_n="NOT_ASSESSED",
      MRI_RNA_biological_tests=0,
      claim_ceiling="S0",
      thesis_direction="CONDITIONAL_GO",
      thesis_submission="HOLD",
      remaining_M1="MECHANISM_AND_MEASUREMENT_NON_EQUIVALENCE_INTERPRETATION_REVIEW",
      remaining_M2="INDEPENDENT_ABDOMINAL_ROI_REVIEW_OR_METHODS_ONLY_LIMITATION",
      remaining_M3="FULL_TEXT_HCC_METHODS_NOVELTY_REVIEW")
    require(sum(r["record_posthoc_thick_slice_sensitivity_only"]=="YES" for r in a)==1,
            "UNEXPECTED_NUMBER_OF_HIGH_SLICE_EXAMPLES")
    return a+b,correlations,summary

def save(out,patients,correlations,summary):
    out.mkdir(parents=True,exist_ok=True)
    with (out/"stage50_frozen73_patient_geometry_roi_rank.csv").open("w",newline="",encoding="utf8") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();w.writerows(patients)
    with (out/"stage50_geometry_roi_spearman_descriptive_correlations.csv").open(
        "w",newline="",encoding="utf8") as f:
        w=csv.DictWriter(f,fieldnames=CORR_FIELDS);w.writeheader();w.writerows(correlations)
    (out/"stage50_A10Y_rank_influence_and_roi_volume_summary.json").write_text(
        json.dumps(summary,indent=2)+"\n",encoding="utf8")
    lines=["# HCC Stage50: HCC MRI native acquisition/ROI volume vs preprocessing rank sensitivity",
      "", "**Source-verified computational study only; POST-RESULTS exploratory and not patient treatment biology.**",
      "","- Internal original native PV reader1: n=14, full Spearman rho **"+
          f'{summary["original_14_rater1_full_rho"]:.6f}'+"**, magnitude change median **"+
          f'{summary["original_14_full_cohort_median_abs_pct"]:.3f}%**.',
      "- External OpenSwissHCC original venous primary: n=59, source Spearman rho **"+
          f'{summary["original_external59_primary_mask_full_rho"]:.6f}'+"**, magnitude change median **"+
          f'{summary["original_external59_full_cohort_median_abs_pct"]:.3f}%**.",
      "- Original TCGA-G3? NO: highest source through-plane thickness is TCGA-BC-A10Y 10.8mm, original index tumor 3;",
      "  other 13 patients have z ≤ "+f'{summary["original_14_other13_z_mm_max"]:.2f}'+"mm.",
      "- A10Y native ROI volume "+f'{summary["source_A10Y_native_rater1_roi_volume_ml"]:.2f}'+"mL;",
      "  original ranks shift 6 positions.",
      "- **Posthoc sensitivity ONLY**: after recalculating n13 ranks excluding A10Y,",
      "  Spearman rho **"+f'{summary["internal_13_no_A10Y_original_native_rater1_Spearman_rho"]:.6f}'+"**",
      "  compared with full n14 "+f'{summary["original_14_rater1_full_rho"]:.6f}'+";",
      "  n13 magnitude-change median **"+
        f'{summary["internal_13_no_A10Y_median_abs_change_pct"]:.3f}%**.",
      "- Recalculated source cohorts' Spearman geometry/ROI associations below are descriptive",
      "  and **not** preplanned tests, do not assign p-values or causal interpretations.",
      "","| Cohort | Geometry parameter | Outcome | Spearman rho |",
      "|---|---|---|---:|"]
    for r in correlations:
        lines.append("| "+r["cohort"]+" | "+r["geometry_parameter"]+
          " | "+r["outcome"]+" | "+("not defined (constant)" if r["Spearman_rho"] is None else
          f'{r["Spearman_rho"]:.3f}')+" |")
    lines+=["","**Caution:** source ROI image and native imaging settings are not identical",
      "between independent cohorts; native voxel-count-derived lesion volume is a measurement",
      "not independent pathology volume. The n14 A10Y exclusion is sensitivity analysis only,",
      "not preapproved exclusion nor a scanner-quality or radiology diagnosis.",
      "Clinical MRI before treatment NOT_ASSESSED, MRI-index tissue-to-RNA aliquot NOT_ASSESSED;",
      "biological analyses 0/12, clinical eligibility NOT_ASSESSED, S0."]
    text="\n".join(lines)+"\n"
    (out/"stage50_HCC_MRI_acquisition_ROI_rank_influence_report.md").write_text(text,encoding="utf8")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"],"a") as f:f.write(text)
    print("HCC_STAGE50_FROZEN_73_SOURCE_GEOMETRY_RANK_INFLUENCE",
          json.dumps(summary,sort_keys=True),flush=True)
    print("HCC_STAGE50_CORRELATIONS",json.dumps(correlations,sort_keys=True),flush=True)

def offline():
    assert abs(spearman([1,2,3,4],[4,3,2,1])+1)<1e-12
    assert spearman([1]*8,list(range(8))) is None
    assert len(PAIRS)==4 and len(FIELDS)>10 and FLAGGED.startswith("TCGA-")
    print("HCC_STAGE50_NO_INVENTED_CLINICAL_PVALUES_NEGATIVE_FIXTURE_PASS")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--stage49-csv",type=Path)
    p.add_argument("--stage49-json",type=Path)
    p.add_argument("--out-dir",type=Path,default=Path("artifacts/hcc_stage50_geometry"))
    p.add_argument("--offline-test",action="store_true")
    a=p.parse_args()
    offline()
    if a.offline_test:return
    require(a.stage49_csv and a.stage49_json and
            a.stage49_csv.is_file() and a.stage49_json.is_file(),
            "STAGE49_FROZEN_ORIGINAL_SOURCE_ARTIFACT_REQUIRED")
    save(a.out_dir,*build(a.stage49_csv,a.stage49_json))

if __name__=="__main__":
    main()
