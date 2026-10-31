#!/usr/bin/env python3
"""Detect clinical/purity case-level drift vs first verified five-job HCC batch.

This is a *technical* baseline, not a clinical eligibility approval.
Missing cases, changed priority, newly asserted eligibility or claimed MRI–
RNA association is a strict CI FAILURE and requires human/source review.
"""
import argparse,csv,json
from datetime import datetime,timezone
from pathlib import Path

BASE="research/hcc/HCC_TECHNICAL_SNAPSHOT_BASELINE_20261031.json"
JOINT="artifacts/hcc_batch_final/hcc_mri14_joint_clinical_purity_image_rna_gate.csv"
SUMMARY="artifacts/hcc_batch_final/hcc_batch_multi_job_readiness_summary.json"


def inspect(base,rows,summary):
    expected=base["frozen"]
    observed={}
    errors=[]
    for r in rows:
        pid=r.get("patient_id","")
        if pid in observed:
            errors.append({"patient_id":pid,"field":"patient_id","error":"DUPLICATE"})
        observed[pid]=[
            r.get("clinical_review_priority","").split("_")[0],
            r.get("purity_review_priority","").split("_")[0],
            r.get("purity_proxy_difference_over_0_20","")
        ]
        for field,value in (
            ("clinical_eligibility","HOLD_UNRESOLVED_NOT_EXCLUDED"),
            ("mri_rna_association_performed","NO"),
            ("mri_pretherapy_adjudication","NOT_VERIFIED"),
            ("same_hcc_lesion_mri_tissue_adjudication","NOT_VERIFIED"),
        ):
            if r.get(field)!=value:
                errors.append({"patient_id":pid,"field":field,"expected":value,
                               "current":r.get(field),"type":"UNAUTHORIZED_PROMOTION_OR_MISSING"})
    # The frozen A10Y 10.8 mm outlier must not silently disappear.
    for r in rows:
        if r.get("pv_native_anisotropy_flag"):
            wanted=("HIGH_THROUGHPLANE_ANISOTROPY_REVIEW" if r.get("patient_id")=="TCGA-BC-A10Y"
                    else "NONISOTROPIC_NATIVE_MRI_REVIEW")
            if r["pv_native_anisotropy_flag"]!=wanted:
                errors.append({"patient_id":r.get("patient_id"),"field":"pv_native_anisotropy_flag",
                               "baseline":wanted,"observed":r["pv_native_anisotropy_flag"],
                               "type":"ACQUISITION_SOURCE_DRIFT"})
    for pid in sorted(set(expected)|set(observed)):
        old=expected.get(pid);new=observed.get(pid)
        if old!=new:
            errors.append({"patient_id":pid,"field":"priority_and_purity_baseline",
                           "baseline":old,"observed":new,"type":"PATIENT_SOURCE_DRIFT"})
    for key,v in base["expected_gate_states"].items():
        if summary.get(key)!=v:
            errors.append({"field":key,"baseline":v,"observed":summary.get(key),
                           "type":"GATE_STATUS_CHANGE_REQUIRES_REVIEW"})
    constants={
        "technical_candidate_count":14,
        "unresolved_n":14,
        "n_official_source_14_reader_metric_confirmed":14,
        "n_native_high_anisotropy_patients":1,
        "source_verified_exact_PV_scanner_vendor_patients":0,
        "maximum_claim":"S0",
        "mri_rna_correlations_computed":False,
        "final_eligible_n":"NOT_ASSESSED",
        "clinical_excluded_n":"NOT_ASSESSED",
    }
    for key,val in constants.items():
        if summary.get(key)!=val:
            errors.append({"field":key,"baseline":val,"observed":summary.get(key),
                           "type":"CLAIM_OR_DENOMINATOR_GUARD"})
    if summary.get("status")!="PASS_BATCH_TECHNICAL_EVIDENCE_CONSISTENCY":
        errors.append({"field":"status","type":"UPSTREAM_GATE_NOT_PASS"})
    return {
        "status":"PASS_NO_UNREVIEWED_SOURCE_DRIFT" if not errors else "REVIEW_REQUIRED_SOURCE_DRIFT",
        "generated_utc":datetime.now(timezone.utc).isoformat(),
        "source_baseline_run_id":base.get("source_run_id"),
        "baseline_cases":len(expected),
        "observed_cases":len(observed),
        "n_drift_or_guard_flags":len(errors),
        "drift_and_guard_flags":errors,
        "mri_rna_associations_performed":False,
        "clinical_eligible_n":"NOT_ASSESSED",
        "manuscript_claim_ceiling":"S0",
        "note":"Review drift before changing frozen source or eligible cohort: no clinical auto-enrollment.",
    }


def offline_test():
    with open(BASE,encoding="utf-8") as f:baseline=json.load(f)
    assert len(baseline["frozen"])==14
    rows=[]
    for pid,(clinical,purity,drift) in baseline["frozen"].items():
        rows.append({
          "patient_id":pid,"clinical_review_priority":clinical+"_FROZEN_FIXTURE",
          "purity_review_priority":purity+"_FROZEN_FIXTURE",
          "purity_proxy_difference_over_0_20":drift,
          "clinical_eligibility":"HOLD_UNRESOLVED_NOT_EXCLUDED",
          "mri_rna_association_performed":"NO",
          "mri_pretherapy_adjudication":"NOT_VERIFIED",
          "same_hcc_lesion_mri_tissue_adjudication":"NOT_VERIFIED"})
    summary={
        **baseline["expected_gate_states"],
        "technical_candidate_count":14,"unresolved_n":14,
        "n_official_source_14_reader_metric_confirmed":14,
        "n_native_high_anisotropy_patients":1,
        "source_verified_exact_PV_scanner_vendor_patients":0,
        "maximum_claim":"S0","mri_rna_correlations_computed":False,
        "final_eligible_n":"NOT_ASSESSED","clinical_excluded_n":"NOT_ASSESSED",
        "status":"PASS_BATCH_TECHNICAL_EVIDENCE_CONSISTENCY"}
    assert inspect(baseline,rows,summary)["status"]=="PASS_NO_UNREVIEWED_SOURCE_DRIFT"
    rows[0]["clinical_review_priority"]="P2_CHANGED"
    assert inspect(baseline,rows,summary)["status"]=="REVIEW_REQUIRED_SOURCE_DRIFT"
    rows[0]["clinical_review_priority"]="P0_RESTORED"
    rows[0]["clinical_eligibility"]="ELIGIBLE"
    assert inspect(baseline,rows,summary)["status"]=="REVIEW_REQUIRED_SOURCE_DRIFT"
    print("HCC_PARALLEL_SOURCE_DRIFT_GUARDS_OFFLINE_PASS")


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--offline-test",action="store_true")
    ap.add_argument("--baseline",default=BASE)
    ap.add_argument("--joint",default=JOINT)
    ap.add_argument("--summary",default=SUMMARY)
    ap.add_argument("--out-dir",default="artifacts/hcc_batch_final")
    args=ap.parse_args()
    if args.offline_test:return offline_test()
    with open(args.baseline,encoding="utf-8") as f:baseline=json.load(f)
    with open(args.joint,encoding="utf-8",newline="") as f:
        rows=list(csv.DictReader(f))
    with open(args.summary,encoding="utf-8") as f:summary=json.load(f)
    result=inspect(baseline,rows,summary)
    out=Path(args.out_dir);out.mkdir(parents=True,exist_ok=True)
    (out/"hcc_batch_patient_source_drift_report.json").write_text(
        json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:v for k,v in result.items() if k!="drift_and_guard_flags"},ensure_ascii=False))
    if result["status"]!="PASS_NO_UNREVIEWED_SOURCE_DRIFT":
        raise SystemExit("Patient source evidence drift or clinical promotion: manual review required")


if __name__=="__main__":main()
