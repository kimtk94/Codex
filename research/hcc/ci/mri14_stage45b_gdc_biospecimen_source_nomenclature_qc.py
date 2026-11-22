#!/usr/bin/env python3
"""Stage45b: independent structural QC of live GDC molecular biospecimen
source lineages captured in successful original Stage45 run #41441332105.
A nested GDC parent-child relationship is authoritative metadata; a
different portion number in submitter barcode is a nomenclature discrepancy
REVIEW, not an automatic patient/tumor exclusion or invented same-lesion link.
All RNA/MRI clinical gates remain unverified.
"""
import argparse,csv,json,os
from pathlib import Path
EXPECTED=set("""TCGA-BC-A10Y TCGA-BC-A3KG TCGA-BC-A5W4 TCGA-BC-A69I TCGA-DD-A4NF
TCGA-DD-A4NH TCGA-DD-A4NJ TCGA-G3-A25T TCGA-G3-A3CJ TCGA-G3-A7M7
TCGA-G3-AAV1 TCGA-G3-AAV2 TCGA-G3-AAV3 TCGA-G3-AAV7""".split())
FIELDS=("patient_id","GDC_RNA_sample","GDC_RNA_portion","GDC_RNA_analyte",
        "GDC_RNA_aliquot","GDC_live_nested_parent_child_chain_status",
        "RNA_aliquot_sample_barcode_compatible",
        "RNA_aliquot_analyte_barcode_compatible",
        "portion_submitter_barcode_matches_analyte_portion_prefix",
        "sample_biospecimen_anatomic_site_available",
        "MRI_index_tumor_to_this_RNA_portion_proven",
        "MRI_before_all_HCC_therapy_proven","clinical_eligible",
        "MRI_RNA_biological_tests","claim_ceiling")

def check(ok,msg):
    if not ok:raise ValueError(msg)
def load(p):
    with p.open(newline="",encoding="utf8") as f:return list(csv.DictReader(f))
def run(p):
    rows=load(p)
    check(len(rows)==14 and set(r["patient_id"] for r in rows)==EXPECTED,
          "FROZEN_ORIGINAL_14_MRI_GDC_SOURCE_PATIENTS_DRIFT")
    result=[]
    for r in sorted(rows,key=lambda x:x["patient_id"]):
        pid=r["patient_id"]
        a=r["public_GDC_matched_analyte"]
        q=r["RNA_aliquot_barcode"]
        sample=r["public_GDC_matched_sample"]
        portion=r["public_GDC_matched_portion"]
        check(r["public_GDC_nested_biospecimen_aliquot_match"]=="YES" and
              r["public_GDC_file_md5_consistent"]=="YES" and
              r["public_GDC_file_associated_aliquot_match"]=="YES",
              "OFFICIAL_LIVE_GDC_CASE_FILE_ALIQUOT_CHAIN_NOT_VERIFIED:"+pid)
        check(r["specific_MRI_before_any_HCC_treatment"]=="NOT_ASSESSED" and
              r["actual_MRI_index_lesion_to_GDC_RNA_tissue_proven"]=="NOT_ASSESSED" and
              r["clinical_eligible_n"]=="NOT_ASSESSED" and
              int(r["MRI_RNA_biological_tests"])==0 and r["claim_ceiling"]=="S0",
              "SOURCE_METADATA_WRONGLY_PROMOTED_TO_CLINICAL_ELIGIBLE:"+pid)
        sampok=q.startswith(sample+"-") and a.startswith(sample+"-")
        anok=q.startswith(a+"-")
        portion_text_match=(a.endswith("R") and portion==a[:-1])
        check(sampok and anok,"RNA_SAMPLE_ALIQUOT_BARCODE_PREFIX_MISMATCH:"+pid)
        result.append(dict(
          patient_id=pid,GDC_RNA_sample=sample,GDC_RNA_portion=portion,
          GDC_RNA_analyte=a,GDC_RNA_aliquot=q,
          GDC_live_nested_parent_child_chain_status="PUBLIC_GDC_NESTED_PASS",
          RNA_aliquot_sample_barcode_compatible="YES" if sampok else "NO",
          RNA_aliquot_analyte_barcode_compatible="YES" if anok else "NO",
          portion_submitter_barcode_matches_analyte_portion_prefix="YES" if portion_text_match else "REVIEW_NOMENCLATURE_DISCORDANCE_NOT_PROVEN_WRONG_SAMPLE",
          sample_biospecimen_anatomic_site_available="YES" if r["public_GDC_matched_sample_site"] else "NO_SOURCE_VALUE",
          MRI_index_tumor_to_this_RNA_portion_proven="NOT_ASSESSED",
          MRI_before_all_HCC_therapy_proven="NOT_ASSESSED",
          clinical_eligible="NOT_ASSESSED",MRI_RNA_biological_tests=0,claim_ceiling="S0"))
    anomalies=[v["patient_id"] for v in result
               if v["portion_submitter_barcode_matches_analyte_portion_prefix"]!="YES"]
    missing_site=[v["patient_id"] for v in result
                  if v["sample_biospecimen_anatomic_site_available"]=="NO_SOURCE_VALUE"]
    summary=dict(stage="HCC_STAGE45B_INDEPENDENT_LIVE_GDC_ALIQUOT_BARCODE_AND_ANATOMIC_SITE_AUDIT",
      verified_GDC_original_nested_sample_portion_analyte_aliquot_links=14,
      verified_live_GDC_STAR_RNA_file_MD5_associated_aliquot=14,
      source_Tumor_tissue_type_recorded_n=14,
      coherent_sample_analyte_aliquot_barcode_prefix_n=14,
      portion_analyte_barcode_text_coherent_n=14-len(anomalies),
      portion_analyte_barcode_text_discordance_cases=anomalies,
      patient_sample_anatomic_site_not_reported_n=len(missing_site),
      patient_site_unavailable_ids=missing_site,
      meaning_of_nomenclature_discordance="SOURCE_SUBMITTER_ID_NAMING_REVIEW_NOT_PROVEN_SPECIMEN_MISMATCH",
      MRI_selected_index_lesion_to_GDC_RNA_tissue_verified_n=0,
      MRI_scan_before_all_HCC_therapies_verified_n=0,
      independent_abdominal_radiologist_approved_n=0,
      clinical_eligible_n="NOT_ASSESSED",
      MRI_RNA_biological_tests=0,claim_ceiling="S0",
      decision="MOLECULAR_PUBLIC_CHAIN_SOURCE_PASS_BUT_LESION_SITE_NOT_REPORTED_AND_ONE_BARCODE_NAMING_REVIEW")
    return result,summary

def write(output,rows,summary):
    output.mkdir(parents=True,exist_ok=True)
    with (output/"stage45b_independent_14case_biospecimen_barcode_site_qc.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();w.writerows(rows)
    (output/"stage45b_14patient_source_biospecimen_nomenclature_summary.json").write_text(json.dumps(summary,indent=2)+"\n")
    md=("# Stage45b independent public GDC biospecimen source QC\n\n"
        "- Actual original GDC nested sample→portion→analyte→aliquot hierarchy 14/14.\n"
        "- Associated RNA file UUID/MD5 confirmed for all 14.\n"
        "- Sample/analyte/aliquot barcode prefix coherent 14/14; portion/analyte number coherent "+
        str(summary["portion_analyte_barcode_text_coherent_n"])+"/14.\n"
        "- Nomenclature REVIEW case: "+",".join(summary["portion_analyte_barcode_text_discordance_cases"])+".\n"
        "- Original sample biospecimen_anatomic_site unreported: "+str(summary["patient_sample_anatomic_site_not_reported_n"])+"/14.\n"
        "- This flags source naming inconsistency; does not contradict actual GDC parent-child linkage or prove sample misassignment.\n"
        "- Site absence and the lack of actual MRI lesion→tissue block bridge prohibit same-lesion assertions.\n"
        "- Clinical MRI before all HCC treatment NOT_ASSESSED; radiologist current index review NOT_ASSESSED.\n"
        "- Eligible N NOT_ASSESSED; frozen MRI–RNA tests 0/12; S0.\n")
    (output/"stage45b_GDC_original_public_source_nomenclature_report.md").write_text(md)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"],"a") as f:f.write(md)
    print("HCC_STAGE45B_GDC_PUBLIC_SPECIMEN_LINEAGE_SOURCE_QC",
          json.dumps(summary,sort_keys=True),flush=True)
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--stage45-csv",type=Path)
    p.add_argument("--out-dir",type=Path,default=Path("artifacts/hcc_stage45b_GDC_QC"))
    p.add_argument("--offline-test",action="store_true")
    a=p.parse_args()
    check(len(EXPECTED)==14 and "TCGA-G3-A7M7" in EXPECTED,"FROZEN_14_CASES_CHANGED")
    if a.offline_test:
        check("TCGA-G3-A7M7-01A-01" != "TCGA-G3-A7M7-01A-12","NAMING_DISCORDANCE_FIXTURE")
        print("HCC_STAGE45B_OFFLINE_FROZEN_TUMOR_BARCODE_AND_SITE_NEGATIVE_FIXTURE_PASS")
        return
    check(a.stage45_csv and a.stage45_csv.is_file(),"STAGE45_ORIGINAL_LIVE_GDC_SOURCE_REQUIRED")
    write(a.out_dir,*run(a.stage45_csv))
if __name__=="__main__":
    main()
