#!/usr/bin/env python3
"""HCC Stage43 independent all14 full3D source evidence audit.

Read pinned Stage41 run #41431710438 (two patient artifacts) and pinned
Stage43 run #41436023580 (twelve patient artifacts), WITHOUT downloading
original DICOM or NIfTI again. Every full-resolution slice CSV, per-case
original image UID/CRC, claim ceiling and clinical HOLD must agree.
Technical PV source image matches NEVER qualify MRI-RNA tissue or treatment.
"""
import argparse,csv,json,os
from pathlib import Path

ORIGINAL2=("TCGA-BC-A3KG","TCGA-BC-A69I")
SOURCE12=("TCGA-BC-A10Y","TCGA-BC-A5W4","TCGA-DD-A4NF",
          "TCGA-DD-A4NH","TCGA-DD-A4NJ","TCGA-G3-A25T",
          "TCGA-G3-A3CJ","TCGA-G3-A7M7","TCGA-G3-AAV1",
          "TCGA-G3-AAV2","TCGA-G3-AAV3","TCGA-G3-AAV7")
ALL=ORIGINAL2+SOURCE12

def check(ok,msg):
    if not ok:raise ValueError(msg)

def read(path):
    check(path.is_file(),"MISSING_IMMUTABLE_SOURCE_ARTIFACT:"+str(path))
    return json.loads(path.read_text(encoding="utf8"))

def rows(path):
    check(path.is_file(),"MISSING_PER_SLICE_PIXEL_SOURCE_CSV:"+str(path))
    with path.open(newline="",encoding="utf8") as f:
        return list(csv.DictReader(f))

def audit(original_root,source12_root):
    results=[]
    for pid in ALL:
        if pid in ORIGINAL2:
            folder=original_root/("hcc-stage41-real-fullstack-"+pid)
        else:
            folder=source12_root/("hcc-stage43-original-fullstack-"+pid)
            gate=read(folder/"stage43_source_case_gate.json")
            check(gate["patient_id"]==pid and bool(gate["source_3d_stack_validated"]),
                  "SOURCE_43_3D_CANDIDATE_NOT_PASSED:"+pid)
            check(gate["clinically_eligible"]=="NOT_ASSESSED" and
                  gate["MRI_before_HCC_treatment"]=="NOT_ASSESSED" and
                  gate["sampled_RNA_same_MRI_index_lesion"]=="NOT_ASSESSED" and
                  gate["MRI_RNA_biology_tests"]==0 and gate["claim_ceiling"]=="S0",
                  "STAGE43_CASE_UNSUPPORTED_CLINICAL_PROMOTION:"+pid)
        j=read(folder/"stage41_full_source_DICOM_PV_3d_summary.json")
        ss=rows(folder/"stage41_original_all_DICOM_slice_fullresolution.csv")
        check(j["patient_id"]==pid and j["technical_source_imaging_verdict"]==
              "STRONG_FULL_3D_PIXELS_AND_LPS_RAS_AFFINE_TECHNICAL_MATCH",
              "ORIGINAL_SOURCE_3D_TECHNICAL_MATCH_UNVERIFIED:"+pid)
        count=int(j["original_DICOM_CRC_verified_instances"])
        check(count==int(j["original_DICOM_unique_SOP_instances"])==
              int(j["full_resolution_slices_compared"])==
              int(j["native_PV_shape_xyz"][2])==len(ss) and count>0,
              "SOURCE_FULL3D_SLICE_COUNT_OR_SOP_CRC_MISMATCH:"+pid)
        check(j["independent_radiologist_review"]=="NOT_ASSESSED" and
              j["original_MRI_before_HCC_treatment_episode"]=="NOT_ASSESSED" and
              j["original_RNA_same_imaged_index_lesion"]=="NOT_ASSESSED" and
              j["clinical_eligible"]=="NOT_ASSESSED" and
              j["MRI_RNA_biology_tests"]==0 and j["claim_ceiling"]=="S0",
              "SOURCE_3D_DATA_WRONGLY_PROMOTED_TO_CLINICAL_ELIGIBLE:"+pid)
        check(bool(j["source_dicom_series_uid"]) and
              bool(j["source_pv_sha256"]) and len(j["source_pv_sha256"])==64,
              "MISSING_SOURCE_SERIES_UID_OR_SHA256:"+pid)
        scores=[float(s["pearson"]) for s in ss]
        errs=[float(s["normalized_linear_fit_rmse"]) for s in ss]
        check(min(scores)>.9999 and max(errs)<.016 and
              float(j["maximum_LPS_RAS_physical_coordinate_error_mm"])<2.0,
              "FULL3D_PIXEL_OR_LPS_RAS_GEOMETRY_NOT_PASS:"+pid)
        check(abs(min(scores)-float(j["fullres_min_pearson"]))<1e-6,
              "FULL3D_SOURCE_CSV_VS_JSON_PEARSON_MISMATCH:"+pid)
        check(len({s["SOPInstanceUID"] for s in ss})==count,
              "FULL3D_SOURCE_CSV_DUPLICATE_SOPS:"+pid)
        result=dict(patient_id=pid,
            source_run_id=41431710438 if pid in ORIGINAL2 else 41436023580,
            source_dicom_series_uid=j["source_dicom_series_uid"],
            source_nifti_sha256=j["source_pv_sha256"],
            DICOM_crc_verified_unique_slices=count,
            native_PV_NIfTI_shape="x".join(map(str,j["native_PV_shape_xyz"])),
            fullres_min_pixel_pearson=min(scores),
            max_normalized_intensity_fit_rmse=max(errs),
            max_DICOM_LPS_to_NIfTI_RAS_error_mm=j["maximum_LPS_RAS_physical_coordinate_error_mm"],
            technical_source_PV_3d_match="PASS",
            MRI_before_HCC_therapy="NOT_ASSESSED",
            exact_MRI_index_lesion_GDC_RNA_aliquot="NOT_ASSESSED",
            independent_abdominal_radiologist="NOT_ASSESSED",
            clinical_eligible="NOT_ASSESSED",MRI_RNA_tests=0,claim_ceiling="S0")
        results.append(result)
        print("HCC_STAGE43_ALL14_CASE_SOURCE_RECONCILED",pid,count,
              result["fullres_min_pixel_pearson"],
              result["max_DICOM_LPS_to_NIfTI_RAS_error_mm"],flush=True)
    check(len(results)==14 and len({x["patient_id"] for x in results})==14,
          "ORIGINAL_14_PATIENT_COHORT_INCOMPLETE")
    check(len({x["source_dicom_series_uid"] for x in results})==14,
          "DUPLICATE_SOURCE_SERIES_UID_ACROSS_PATIENTS")
    s=dict(
      stage="HCC_STAGE43_FINAL_INDEPENDENT_14_CASE_ORIGINAL_PV_DICOM_3D_SOURCE_RECONCILIATION",
      original_frozen_tcga_mri_patients=14,
      first_stage41_original_full3d_verified_n=2,
      newly_stage43_original_full3d_verified_n=12,
      original_pv_nifti_dicom_3d_technical_source_verified_n=14,
      source_DICOM_CRC_verified_fullresolution_slices=sum(x["DICOM_crc_verified_unique_slices"] for x in results),
      source_fullresolution_Pearson_min=min(x["fullres_min_pixel_pearson"] for x in results),
      maximum_source_LPS_NIfTI_RAS_physical_error_mm=max(x["max_DICOM_LPS_to_NIfTI_RAS_error_mm"] for x in results),
      full_source_zip_MD5_independently_verified=False,
      full_source_DICOM_NIfTI_bitwise_equality_demonstrated=False,
      independent_qualified_radiologist_approved_n=0,
      MRI_before_HCC_treatment_authoritative_episode_verified_n=0,
      exact_MRI_index_lesion_to_GDC_RNA_portion_proven_n=0,
      clinical_eligible_n="NOT_ASSESSED",MRI_RNA_biological_tests=0,claim_ceiling="S0",
      clinical_radiogenomics_gate="HOLD",source_original_MRI_PV_technical_gate="GO")
    return results,s

def write(out,items,summary):
    out.mkdir(parents=True,exist_ok=True)
    with (out/"stage43_full14_PV_DICOM_3d_source_patient_evidence.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(items[0]));w.writeheader();w.writerows(items)
    (out/"stage43_full14_PV_DICOM_3d_source_evidence_summary.json").write_text(
        json.dumps(summary,indent=2)+"\n",encoding="utf8")
    lines=[
      "# HCC Stage43 — 14/14 original PV DICOM–NIfTI full-3D technical source evidence",
      "",
      "Independent frozen GitHub source artifacts: Stage41 run 41431710438 (2 cases),",
      "Stage43 run 41436023580 (12 cases). No original MRI image was re-downloaded in this audit.",
      "",
      "- All original PV source-series technical 3D links: **14/14 PASS**.",
      "- Source full-resolution DICOM CRC-verified slices: **"+
        str(summary["source_DICOM_CRC_verified_fullresolution_slices"])+"**.",
      "- Global minimum per-slice fullresolution Pearson: **"+
        str(summary["source_fullresolution_Pearson_min"])+"**.",
      "- Global maximum LPS-to-RAS physical coordinate error: **"+
        str(summary["maximum_source_LPS_NIfTI_RAS_physical_error_mm"])+" mm**.",
      "- **Clinical MRI treatment and identical tumor RNA evidence: NOT_ASSESSED.**",
      "- Qualified independent radiology: NOT_ASSESSED.",
      "- Clinical eligible n: NOT_ASSESSED; biological tests **0/12**, ceiling **S0**.",
      "", "| Patient | Source slices | Min Pearson | Max spatial error (mm) |",
      "|---|---:|---:|---:|"]
    for p in items:
        lines.append("| "+p["patient_id"]+" | "+
           str(p["DICOM_crc_verified_unique_slices"])+" | "+
           str(p["fullres_min_pixel_pearson"])+" | "+
           str(p["max_DICOM_LPS_to_NIfTI_RAS_error_mm"])+" |")
    md="\n".join(lines)+"\n"
    (out/"stage43_full14_original_source_3d_technical_verification_report.md").write_text(md,encoding="utf8")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"],"a") as f:f.write(md)
    print("HCC_STAGE43_FINAL_FROZEN_14_SOURCE_EVIDENCE",json.dumps(summary,sort_keys=True),flush=True)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--stage41-artifact-root",type=Path)
    p.add_argument("--stage43-artifact-root",type=Path)
    p.add_argument("--out-dir",type=Path,default=Path("artifacts/hcc_stage43_14_evidence"))
    p.add_argument("--offline-test",action="store_true")
    a=p.parse_args()
    check(len(ALL)==14 and len(set(ALL))==14 and len(SOURCE12)==12,
          "FROZEN_14_MRI_SOURCE_PATIENT_ROSTER_CHANGED")
    if a.offline_test:
        print("HCC_STAGE43_FROZEN_14_ORIGINAL_SOURCE_ROSTER_OFFLINE_PASS")
        return
    check(a.stage41_artifact_root and a.stage43_artifact_root,
          "STAGE41_AND_STAGE43_IMMUTABLE_SOURCE_EVIDENCE_REQUIRED")
    write(a.out_dir,*audit(a.stage41_artifact_root,a.stage43_artifact_root))
if __name__=="__main__":
    main()
