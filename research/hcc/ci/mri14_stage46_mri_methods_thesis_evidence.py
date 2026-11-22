#!/usr/bin/env python3
"""HCC Stage46 decision gate: can existing MRI source evidence sustain a
standalone *methods* master's thesis without inventing MRI-RNA clinical pairing?

Data-driven check uses immutable research/hcc CSV/MD files from actual
GitHub Actions, no unreviewed clinical claims, prediction model or p-values.
External n=59 is an independent image cohort; not external validation of
clinical outcome, and 3 second-reader masks never become an n=59 ICC cohort.
The internal n=14 cohort's registered ART/PV preprocessing is non-identical
to independent original Swiss native PV; report only descriptive corroboration.
"""
import argparse,csv,json,math,os,statistics
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
EXTERNAL=ROOT/"HCC_EXTERNAL_OPENSWISSHCC_V2_59_INDEX_PATIENT_GLCM_NATIVE3MM_FROZEN_20261101.csv"
STABILITY=ROOT/"HCC_EXTERNAL_OPENSWISSHCC_V2_59_24_CONDITION_BOOTSTRAP_FROZEN_20261101.csv"
ICC14=ROOT/"HCC_MRI_PV_RATER_ICC_14_FEATURE_STABILITY_20261030.csv"
READERS3=ROOT/"HCC_EXTERNAL_STAGE33_3_INDEX_READER_SOURCE_METRICS_FROZEN_20261101.csv"
INTERNAL=ROOT/"HCC_EXTERNAL_OPENSWISSHCC_V2_59_VENOUS_RADIOMICS_REPLICATION_VERIFIED_20261101.md"
SOURCE44=ROOT/"HCC_STAGE44_ALL14_SOURCE_UID_GDC_RNA_TREATMENT_CLINICAL_HOLD_VERIFIED_20261102.md"
SOURCE45=ROOT/"HCC_STAGE45_GDC_LIVE_14_BIOSPECIMEN_LINEAGE_FEASIBILITY_AND_STAGE45B_QC_20261102.md"
N59=59
N14=14
NREADER=3
IBSI_REFERENCE="https://theibsi.github.io/ibsi1/"
OPEN_SWISS_PAPER="https://doi.org/10.1038/s41597-026-08506-3"

def require(cond,reason):
    if not cond:raise ValueError(reason)

def read_csv(p):
    require(p.is_file(),"PINNED_SOURCE_MISSING:"+str(p))
    with p.open("r",newline="",encoding="utf-8") as f:return list(csv.DictReader(f))

def ranks(vals):
    indexed=sorted(enumerate(vals),key=lambda x:x[1])
    result=[0.0]*len(indexed)
    i=0
    while i<len(indexed):
        j=i+1
        while j<len(indexed) and indexed[j][1]==indexed[i][1]:j+=1
        rank=(i+j+1)/2.0
        for k in range(i,j):result[indexed[k][0]]=rank
        i=j
    return result

def pearson(x,y):
    require(len(x)==len(y) and len(x)>2,"CORRELATION_N_INVALID")
    ax=statistics.mean(x);ay=statistics.mean(y)
    a=[v-ax for v in x];b=[v-ay for v in y]
    den=math.sqrt(sum(v*v for v in a)*sum(v*v for v in b))
    require(den>1e-12,"CORRELATION_CONSTANT_INPUT")
    return sum(i*j for i,j in zip(a,b))/den

def audit():
    p=read_csv(EXTERNAL)
    v=read_csv(STABILITY)
    icc=read_csv(ICC14)
    double=read_csv(READERS3)
    require(len(p)==N59 and len({x["subject"] for x in p})==N59,
            "EXTERNAL_ORIGINAL_PATIENT_DENOMINATOR_NOT59")
    require(all(x["original_source_run"]=="41221356861" and
                x["claim_ceiling"]=="S0" and
                x["selected_HCC_lesion"].startswith("L")
                for x in p),"EXTERNAL_SOURCE_PROVENANCE_OR_SELECTION_DRIFT")
    require(all(int(x["source_mask_voxels"])>=100 for x in p),
            "ORIGINAL_HCC_MASK_SOURCE_INVALID")
    vals=[]
    for x in p:
        base=float(x["original_native25_GLCM_Contrast"])
        new=float(x["resampled_3mm25_GLCM_Contrast"])
        supplied=float(x["signed_change_pct"])
        require(math.isfinite(base) and math.isfinite(new) and base>0 and new>0,
                "SOURCE_GLCM_CONTRAST_NONFINITE_OR_ZERO_BASELINE")
        estimated=(new-base)/abs(base)*100.0
        require(abs(estimated-supplied)<.002,
                "STAGE46_SOURCE_CSV_GLCM_PERCENT_CHANGE_RECOMPUTE_FAILED:"+x["subject"])
        vals.append(dict(subject=x["subject"],base=base,new=new,
                         signed=estimated,absolute=abs(estimated)))
    median_abs=statistics.median(x["absolute"] for x in vals)
    rho=pearson(ranks([x["base"] for x in vals]),ranks([x["new"] for x in vals]))
    require(abs(median_abs-64.635863)<.002,"EXTERNAL59_PRIOR_PRIMARY_MEDIAN_NOT_REPRODUCED")
    require(abs(rho-0.940795)<.0002,"EXTERNAL59_SPEARMAN_RANK_RHO_NOT_REPRODUCED")
    require(len(v)==24 and len({(r["feature"],r["grid"],r["binWidth"]) for r in v})==24,
            "EXTERNAL_24_FEATURE_CONDITION_COUNTS_INCORRECT")
    require(all(r["independent_n"]=="59" and r["bootstrap_iterations"]=="4000" and
                r["source_run"]=="41221356861" and r["claim_ceiling"]=="S0"
                for r in v),"EXTERNAL_PATIENT_BOOTSTRAP_CLAIM_DRIFT")
    features=set(r["feature"] for r in v)
    require(features=={"original_glcm_Contrast","original_glcm_JointEntropy",
                "original_firstorder_Entropy","original_firstorder_InterquartileRange"},
            "EXTERNAL_FEATURE_FAMILY_NOT_FROZEN4")
    primary=[r for r in v if r["feature"]=="original_glcm_Contrast" and
             r["grid"]=="3mm" and r["binWidth"]=="25"]
    require(len(primary)==1,"PRIMARY_3MM_BW25_CONDITION_NOT_UNIQUE")
    pr=primary[0]
    require(abs(float(pr["median_abs_pct"])-median_abs)<.002 and
            abs(float(pr["patient_spearman_rho"])-rho)<.0002,
            "EXTERNAL_PRIMARY_CI_ROW_MISMATCH")
    lo=float(pr["bootstrap95_low"]);hi=float(pr["bootstrap95_high"])
    require(lo<median_abs<hi and lo>0 and hi<150,"EXTERNAL_PRIMARY_CI_FROZEN_INVALID")
    require(len(icc)==10 and len({x["feature"] for x in icc})==10,
            "INTERNAL_14_RATER_FEATURE_DENOMINATOR_CHANGED")
    count=Counter(r["reliability_screen"] for r in icc)
    require(count=={"PASS":8,"EXCLUDE_BY_RELIABILITY":2},
            "INTERNAL_14_RATER_ICC_8_OF_10_SOURCE_DRIFT")
    c={r["feature"]:r for r in icc}
    require(c["original_glcm_Contrast"]["reliability_screen"]=="PASS" and
            float(c["original_glcm_Contrast"]["icc_a1_absolute_agreement"])>.95,
            "INTERNAL14_GLCM_CONTRAST_RATER_ICC_NOT_REPLICATED")
    require(len(double)==NREADER and len({x["subject"] for x in double})==NREADER,
            "EXTERNAL_DOUBLE_READ_INDEX_LESION_COUNT_INCORRECT")
    require({x["subject"] for x in double}<={x["subject"] for x in p},
            "SECOND_READER_MASK_REFERENCES_UNSELECTED_SOURCE")
    dices=[float(x["dice"]) for x in double]
    require(all(.0<d<=1.0 for d in dices) and
            all(x["independent_clinical_review"]=="NOT_ASSESSED" and
                x["claim_ceiling"]=="S0" for x in double),
            "TWO_READER_SOURCE_CLAIMS_FALSELY_EXPANDED")
    internal=INTERNAL.read_text(encoding="utf8")
    require("86.594%" in internal and "76.400" in internal and
            "97.878" in internal,"INTERNAL_REGISTERED_PV_SOURCE_MEDIAN_NOT_REFERENCED")
    require("n14" in internal or "n14" in internal.replace(" ",""),
            "NO_REPORTED_INTERNAL_ORIGINAL_N14")
    require(SOURCE44.is_file() and SOURCE45.is_file(),"FROZEN_CLINICAL_HOLD_REPORTS_REQUIRED")
    require("NOT_ASSESSED" in SOURCE44.read_text(encoding="utf8") and
            "NOT_ASSESSED" in SOURCE45.read_text(encoding="utf8"),
            "SOURCE_MRI_RNA_CLINICAL_HOLD_MISSING")
    positives=sum(x["signed"]>0 for x in vals)
    gt20=sum(x["absolute"]>20 for x in vals)
    loo=[statistics.median(v["absolute"] for j,v in enumerate(vals) if j!=i)
         for i in range(len(vals))]
    summaries=[]
    for r in v:
        if r["grid"]=="3mm" and r["binWidth"]=="25":
            summaries.append({
                "feature":r["feature"],
                "external_patient_n":59,
                "median_abs_change_pct":float(r["median_abs_pct"]),
                "bootstrap95_low_pct":float(r["bootstrap95_low"]),
                "bootstrap95_high_pct":float(r["bootstrap95_high"]),
                "patient_rank_spearman":float(r["patient_spearman_rho"]),
                "ICC14_rater_reliability_screen":c[r["feature"]]["reliability_screen"],
                "ICC14_rater_point":float(c[r["feature"]]["icc_a1_absolute_agreement"]),
                "cross_cohort_same_exact_source_protocol":False,
                "source_only_reproduction_not_clinical_prediction":True})
    summaries.sort(key=lambda x:x["feature"])
    result=dict(
        stage="HCC_STAGE46_MASTER_THESIS_METHODS_DECISION_SOURCE_EVIDENCE_AUDIT",
        internal_original_TCGA_LIHC_MRI_n=14,
        external_independent_Openswiss_HCC_venous_n=59,
        source_patients_analyzed_total_distinct=73,
        original_internal_two_reader_ICC_features=10,
        original_internal_two_reader_ICC_screen_pass=8,
        original_external_two_reader_frozen_index_subjects=3,
        original_external_total_source_feature_condition_rows=354,
        original_external_24_feature_condition_summary_rows=24,
        original_external_independent_patient_bootstrap_draws=4000,
        external_native25_to_3mm25_GLCM_Contrast_median_abs_change_pct=median_abs,
        external_native25_to_3mm25_GLCM_Contrast_bootstrap95_ci=[lo,hi],
        external_native25_to_3mm25_GLCM_Contrast_rank_Spearman=rho,
        external_native25_to_3mm25_GLCM_Contrast_positive_direction_n=positives,
        external_native25_to_3mm25_GLCM_Contrast_gt20pct_abs_n=gt20,
        external_native25_to_3mm25_GLCM_Contrast_LOO_median_range=[min(loo),max(loo)],
        internal_registered_PV14_native25_to_3mm25_GLCM_Contrast_median_abs_pct=86.594,
        internal_registered_PV14_median_abs_bootstrap95_percent=[76.400,97.878],
        external_three_original_two_reader_mask_median_Dice=statistics.median(dices),
        source_dataset_level_all_HCC_lesions_independently_reviewed=False,
        source_protocol_equivalence_between14_and59=False,
        independent_test_retest_scan_pairs_verified_n=0,
        independent_radiology_adjudication_current_study_n=0,
        MRI_selected_index_tumor_to_GDC_aliquot_proven_n=0,
        MRI_before_all_relevant_HCC_treatments_verified_n=0,
        clinical_eligible_n="NOT_ASSESSED",
        MRI_RNA_hallmark_biology_tests=0,
        clinical_biological_claim_ceiling="S0",
        MRI_methods_source_reproduction="TECHNICAL_GO",
        methods_master_thesis_status="CONDITIONAL_GO_NOT_SCIENTIFICALLY_FINISHED",
        multiomics_clinical_pairing_status="HOLD",
        causal_effect_of_resampling_or_scanner="NOT_TESTED",
        clinical_prediction_or_prognostic_external_validation="NOT_TESTED",
        novelty_against_existing_preprocessing_radiomics_literature="REQUIRES_DEDICATED_LITERATURE_GAP_REVIEW",
        next_primary_task="PRESPECIFY_THESIS_METHODS_SCOPE_AND_TRUE_CROSS_COHORT_PROTOCOL_COMPARABILITY",
        next_independent_task="INDEPENDENT_ABDOMINAL_EXPERT_INDEX_ROI_REVIEW_AND_BATCH_ROI_QC",
        references={"IBSI1":IBSI_REFERENCE,"OpenSwissHCC":OPEN_SWISS_PAPER,
          "external_image_source_run":41221356861,
          "external_source_immutable_result_audit_run":41223161712,
          "external_reader3_run":41224906345,
          "internal_icc14_run":41074562055,
          "internal_icc14_loo_run":41075577502,
          "MRI14_original_source_run":41438155270})
    require(positives==59 and gt20==55,"SOURCE_FROZEN_DIRECTION_OR_GT20_COUNT_DRIFT")
    return result,summaries

def write(out,summary,rows):
    out.mkdir(parents=True,exist_ok=True)
    (out/"stage46_mri_methods_thesis_evidence_audit.json").write_text(
        json.dumps(summary,indent=2,ensure_ascii=False)+"\n",encoding="utf8")
    fields=list(rows[0])
    with (out/"stage46_four_features_14ICC_59processing_crosscheck.csv").open(
        "w",newline="",encoding="utf8") as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
    report=[
      "# Stage46 HCC MRI-methods master's thesis evidence gate",
      "",
      "**Decision: CONDITIONAL GO as an MRI-methods thesis; MRI-RNA remains HOLD.**",
      "",
      "The confirmed independent source cohorts include 14 TCGA-LIHC LiverHccSeg MRI patients with",
      "two-reader MRI feature extraction, and 59 OpenSwissHCC v2 native venous MRI patients",
      "with original expert lesion masks. 14+59=73 unique study IDs, NOT 73 independent scanner-repeat test pairs.",
      "",
      "## Primary descriptive measurement contrast",
      "",
      "Within the 59 original external venous images, original native/binWidth25",
      "versus resampled 3mm/binWidth25 GLCM Contrast values:",
      "- Absolute paired patient percentage change median **"+
      f'{summary["external_native25_to_3mm25_GLCM_Contrast_median_abs_change_pct"]:.3f}%'+
      "**, frozen 4,000-resample patient bootstrap 95% interval **"+
      f'{summary["external_native25_to_3mm25_GLCM_Contrast_bootstrap95_ci"][0]:.3f}'+
      " to "+f'{summary["external_native25_to_3mm25_GLCM_Contrast_bootstrap95_ci"][1]:.3f}%**.',
      "- Patient ranks retain Spearman rho **"+
      f'{summary["external_native25_to_3mm25_GLCM_Contrast_rank_Spearman"]:.6f}'+"**.",
      "- Signed shift positive in **59/59** original cases; >20% absolute shift in **55/59**.",
      "- Leave-one-out median shift range: "+
      f'{summary["external_native25_to_3mm25_GLCM_Contrast_LOO_median_range"][0]:.3f}'+" to "+
      f'{summary["external_native25_to_3mm25_GLCM_Contrast_LOO_median_range"][1]:.3f}'+"%.",
      "- Internal registered ART/PV 14-case descriptive source median: **86.594%**",
      "(bootstrap CI 76.400–97.878%); NOT the same raw native venous protocol,",
      "so this is **independent methods corroboration**, NOT exchangeable replication or a formal",
      "between-cohort treatment-effect meta-analysis.",
      "",
      "## Independent annotation and source QC",
      "",
      "- TCGA-LIHC: 10 feature ICC(A,1) evaluated over 14 patients × two masks;",
      "**8/10** pass frozen point/bootstrap/LOO reliability screen;",
      "**GLCM Contrast ICC(A,1)=0.9668**. Segmentation reliability does NOT imply",
      "numerical stability under resampling.",
      "- OpenSwissHCC: only **3/59** frozen index lesions have a second-reader mask;",
      f'median original-mask Dice {summary["external_three_original_two_reader_mask_median_Dice"]:.6f}'+";",
      "**no 59-patient multi-reader ICC is available**.",
      "- Published OpenSwissHCC annotation quality does not equal a new independent expert",
      "approval of each frozen index lesion, especially not a new TCGA-LIHC review.",
      "",
      "## Decision and strict manuscript boundaries",
      "",
      "**Methods thesis conditional GO**: original venous HCC radiomics preprocessing",
      "sensitivity versus preservation of patient rank, with two independent source cohorts;",
      "focus on GLCM Contrast and predeclared four-feature sensitivity family;",
      "add ROI-size/anisotropy robustness and uncertainty accounting.",
      "",
      "**Outstanding:** harmonize the actual native-vs-registered comparison definition,",
      "validate independent original image/ROI anatomy with a qualified reviewer,",
      "predeclare primary/secondary endpoints, avoid choosing a favored feature after results,",
      "and perform a genuine literature novelty analysis before asserting thesis contribution.",
      "",
      "**DO NOT CLAIM:** independently repeated scans, MRI–RNA tumor-level identity,",
      "pretreatment relative chronology, external prognosis/diagnostic model validation,",
      "cause of acquisition differences, or prospective patient utility.",
      "MRI–RNA biological tests remain **0/12**, eligible n **NOT_ASSESSED**,",
      "clinical biology ceiling **S0**. Methods-only descriptive technical data are analyzed.",
      "",
      "| Feature | Median absolute native→3mm % (95% patient bootstrap) | External rank ρ | TCGA ICC(A,1) |",
      "|---|---:|---:|---:|"]
    for r in rows:
        report.append("| "+r["feature"].removeprefix("original_")+" | "+
          f'{r["median_abs_change_pct"]:.2f}'+" ["+
          f'{r["bootstrap95_low_pct"]:.2f}–{r["bootstrap95_high_pct"]:.2f}' +"] | "+
          f'{r["patient_rank_spearman"]:.3f}'+" | "+
          f'{r["ICC14_rater_point"]:.4f}'+" |")
    md="\n".join(report)+"\n"
    (out/"stage46_mri_methods_thesis_GO_HOLD_decision_report.md").write_text(md,encoding="utf8")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"],"a") as f:f.write(md)
    print("HCC_STAGE46_SOURCE_VERIFIED_METHODS_THESIS_DECISION",
          json.dumps(summary,sort_keys=True),flush=True)

def offline():
    require(abs(pearson(ranks([3,1,2]),ranks([9,3,7]))-1)<1e-12,
            "SPEARMAN_FIXTURE_NONMONOTONIC")
    require(abs(statistics.median([1,5,3])-3)<1e-12,"MEDIAN_FIXTURE_FAILED")
    require(len(ranks([1,1,2]))==3,"TIED_RANK_FIXTURE_FAILED")
    print("HCC_STAGE46_PATIENT_RANK_MEDIAN_AND_SAMPLE_DENOMINATOR_NEGATIVE_FIXTURES_PASS")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--out-dir",type=Path,default=Path("artifacts/hcc_stage46_methods_thesis"))
    p.add_argument("--offline-test",action="store_true")
    a=p.parse_args()
    offline()
    if a.offline_test:return
    write(a.out_dir,*audit())
if __name__=="__main__":main()
