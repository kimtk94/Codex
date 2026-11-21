#!/usr/bin/env python3
"""HCC Stage43 12 remaining original DICOM full3D source validations.

Consumes frozen Stage42 source-pixel 12-case aggregate and delegates numerical
full-DICOM-stack source matching to independently verified Stage41 code.
Never promotes clinical patient eligibility or MRI-RNA biological inference.
"""
import argparse,csv,json,os
from pathlib import Path
from mri14_stage42_remaining_source_pixel_candidates import REMAINING
import hcc_stage41_fullstack_original_source as full

def must(b,msg):
    if not b:raise ValueError(msg)

def source_rows(path):
    with path.open(newline="",encoding="utf8") as f:return list(csv.DictReader(f))

def selected(path,pid):
    rows=source_rows(path)
    must(len(rows)==12 and set(x["patient_id"] for x in rows)==set(REMAINING),
         "STAGE42_IMMUTABLE_12PATIENT_PRIORITY_CHANGED")
    r=next(x for x in rows if x["patient_id"]==pid)
    must(r["clinical_eligible_n"]=="NOT_ASSESSED","STAGE42_CLINICAL_GATING_CHANGED")
    return r

def run(pid,pinned,out):
    must(pid in REMAINING and len(REMAINING)==12,"STAGE43_CASE_SCOPE_CHANGED")
    r=selected(pinned,pid)
    strong=r["source_pixel_pattern_decision"]=="ONE_UNIQUE_STRONG_PATTERN_CANDIDATE_FULL_STACK_REQUIRED"
    out.mkdir(parents=True,exist_ok=True)
    if strong:
        uid=r["unique_candidate_series_uid"];folder=r["unique_candidate_source_directory"]
        must(uid and folder and int(r["strong_source_pixel_pattern_candidates"])==1,
             "STAGE42_PIXEL_CANDIDATE_NOT_UNIQUE")
        full.PILOT=REMAINING
        def choose(path,selected_pid):
            must(selected_pid==pid and path==pinned,"STAGE43_SOURCE_PROVENANCE_CHANGE")
            return {"source_directory":folder,"SeriesInstanceUID":uid}
        full.choose=choose
        full.run(pid,pinned,out)
        original=json.loads((out/"stage41_full_source_DICOM_PV_3d_summary.json").read_text())
        verdict=original["technical_source_imaging_verdict"]
        confirmed=verdict=="STRONG_FULL_3D_PIXELS_AND_LPS_RAS_AFFINE_TECHNICAL_MATCH"
        n=original["full_resolution_slices_compared"]
        pmin=original["fullres_min_pearson"];wmax=original["maximum_LPS_RAS_physical_coordinate_error_mm"]
    else:
        confirmed=False;verdict="HOLD_STAGE42_STRONG_SOURCE_CANDIDATE_NOT_UNIQUE_OR_ABSENT"
        uid="";folder="";n=0;pmin=None;wmax=None
    result=dict(stage="HCC_STAGE43_FROZEN_REMAINING_12_FULL_3D_ORIGINAL_SOURCE",
      patient_id=pid,stage42_source_decision=r["source_pixel_pattern_decision"],
      source_DICOM_series_uid=uid,
      source_DICOM_directory=folder,
      source_3d_stack_validated=confirmed,
      source_3d_stack_verdict=verdict,
      original_DICOM_slices_fullres_compared=n,
      minimum_original_DICOM_PV_fullres_Pearson=pmin,
      maximum_source_LPS_to_NIfTI_RAS_error_mm=wmax,
      MRI_before_HCC_treatment="NOT_ASSESSED",
      sampled_RNA_same_MRI_index_lesion="NOT_ASSESSED",
      independent_abdominal_radiology="NOT_ASSESSED",
      clinically_eligible="NOT_ASSESSED",MRI_RNA_biology_tests=0,claim_ceiling="S0")
    (out/"stage43_source_case_gate.json").write_text(json.dumps(result,indent=2)+"\n")
    print("HCC_STAGE43_CASE_FULL3D_GATE",json.dumps(result,sort_keys=True),flush=True)

def aggregate(root,out):
    reports=[]
    for pid in REMAINING:
        path=root/("hcc-stage43-original-fullstack-"+pid)/"stage43_source_case_gate.json"
        must(path.is_file(),"STAGE43_MISSING_PATIENT:"+pid)
        r=json.loads(path.read_text())
        must(r["patient_id"]==pid and r["clinically_eligible"]=="NOT_ASSESSED" and
             r["MRI_before_HCC_treatment"]=="NOT_ASSESSED" and
             r["sampled_RNA_same_MRI_index_lesion"]=="NOT_ASSESSED" and
             r["MRI_RNA_biology_tests"]==0 and r["claim_ceiling"]=="S0",
             "STAGE43_SOURCE_CLAIM_PROMOTION")
        reports.append(r)
    passed=sum(bool(r["source_3d_stack_validated"]) for r in reports)
    s=dict(stage="HCC_STAGE43_FROZEN12_COMPLETE_SOURCE_STACK",stage41_earlier_source_full3d_n=2,
           stage43_remaining_case_jobs=12,stage43_full3d_source_technical_pass_n=passed,
           stage43_source_technical_HOLD_n=12-passed,all14_full3d_source_technical_pass_n=2+passed,
           clinically_eligible="NOT_ASSESSED",independent_radiology_approved=0,
           MRI_before_HCC_treatment_source_proven_n=0,
           MRI_index_tumor_RNA_sample_source_proven_n=0,
           MRI_RNA_biological_tests=0,claim_ceiling="S0")
    out.mkdir(parents=True,exist_ok=True)
    (out/"stage43_complete_original_DICOM_source_14patient_summary.json").write_text(json.dumps(s,indent=2)+"\n")
    with (out/"stage43_frozen12_source_full3d_patient_gate.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(reports[0]));w.writeheader();w.writerows(reports)
    if os.getenv("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"],"a") as f:
            f.write("# Stage43 original PV DICOM source 12-case results\n\n"+json.dumps(s,indent=2)+"\n")
    print("HCC_STAGE43_SOURCE_FROZEN_12_3D_AGGREGATE",json.dumps(s,sort_keys=True),flush=True)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--patient",choices=REMAINING)
    p.add_argument("--stage42-csv",type=Path)
    p.add_argument("--aggregate",action="store_true")
    p.add_argument("--shard-root",type=Path)
    p.add_argument("--out-dir",type=Path,default=Path("artifacts/hcc_stage43_fullstack"))
    p.add_argument("--offline-test",action="store_true")
    a=p.parse_args()
    must(len(REMAINING)==12,"SOURCE_FROZEN12_CHANGED")
    if a.offline_test:
        full.offline_test()
        print("HCC_STAGE43_TWELVE_CASES_ORIGINAL_CLINICAL_HOLD_FIXTURE_PASS");return
    if a.aggregate:
        must(a.shard_root is not None,"STAGE43_MISSING_INPUTS")
        aggregate(a.shard_root,a.out_dir)
    else:
        must(a.patient and a.stage42_csv and a.stage42_csv.is_file(),
             "STAGE43_STAGE42_FROZEN_SOURCE_REQUIRED")
        run(a.patient,a.stage42_csv,a.out_dir)
if __name__=="__main__":main()
