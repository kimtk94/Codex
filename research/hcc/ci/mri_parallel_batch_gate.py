#!/usr/bin/env python3
"""HCC 14 MRI/RNA technical cohort: parallel GitHub Action evidence batch integrator.

Supports:
  --mode source   : independently verify immutable ROI/GDC RNA/Hallmark/ICC identities.
  --mode assemble : join artifacts from clinical, purity and source jobs into
                    one evidence queue and machine-readable GO/HOLD/STOP summary.
  --offline-test  : no-network regression and negative-path guards.

Hard exclusions:
* This script cannot promote a subject to clinical eligibility.
* No MRI-RNA feature-vs-pathway statistics, p-values or FDR are computed.
* GDC relative dates must not be joined to shifted TCIA acquisition dates.
"""
import argparse
import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path("research/hcc")
ROI=ROOT/"HCC_MRI_14_PREOUTCOME_INDEX_LESION_SELECTION_20261030.csv"
RNA=ROOT/"HCC_MRI_14_GDC_PRIMARY_TUMOR_RNA_FILE_MANIFEST_20261030.csv"
SCORE=ROOT/"HCC_MRI_14_MSIGDB_HALLMARK_RANK_SCORE_20261031.csv"
ICC=ROOT/"HCC_MRI_PV_RATER_ICC_14_FEATURE_STABILITY_20261030.csv"
SAP=ROOT/"HCC_MRI_RNA_PREOUTCOME_HALLMARK_SAP_V1.md"

REFINED="artifacts/hcc_batch_clinical/hcc_mri14_treatment_site_refined_review_queue.csv"
PURITY="artifacts/hcc_batch_purity/hcc_mri_14_absolute_vs_cpe_purity_review.csv"
SOURCE="artifacts/hcc_batch_source/hcc_mri14_frozen_source_identity.csv"
PUBLICATION="artifacts/hcc_batch_publication/hcc_mri14_published_expert_reader_metadata_crosswalk.csv"
ACQUISITION="artifacts/hcc_batch_acquisition/hcc_mri14_acquisition_native_spacing_qc.csv"

HALLMARK=(
 "HALLMARK_HYPOXIA","HALLMARK_ANGIOGENESIS",
 "HALLMARK_EPITHELIAL_MESENCHYMAL_TRANSITION","HALLMARK_GLYCOLYSIS",
)
PRIMARY_FEATURES=(
 "original_firstorder_Entropy",
 "original_glcm_Contrast",
 "original_firstorder_InterquartileRange",
)
FIELDS=(
 "patient_id","representative_tumor_number","selected_roi_pixel_qc_run",
 "same_primary_tumor_rna_specimen_barcode","gdc_rna_file_id",
 "gene_set_score_source_qc","clinical_review_priority",
 "hcc_context_dated_treatment_records","other_anatomic_site_dated_records",
 "abs_dna_purity_proxy","historical_cpe","purity_review_priority",
 "purity_proxy_difference_over_0_20",
 "published_expert_readers_source","published_hcc_dice_metric",
 "pv_slice_thickness_mm","pv_z_to_inplane_ratio","pv_native_anisotropy_flag",
 "published_patient_level_field_strength_t","scanner_vendor_status",
 "mri_pretherapy_adjudication","same_hcc_lesion_mri_tissue_adjudication",
 "qualified_roi_radiologist_review","exact_star_rna_aliquot_purity",
 "clinical_eligibility","mri_rna_association_performed",
)

def load(path, key="patient_id",expected=14):
    with Path(path).open(encoding="utf-8-sig",newline="") as f:
        rows=list(csv.DictReader(f))
    if len(rows)!=expected:
        raise ValueError(f"{path}: expected {expected} records, got {len(rows)}")
    ids=[r[key] for r in rows]
    if len(set(ids))!=len(ids):
        raise ValueError(f"{path}: nonunique {key}")
    return {r[key]:r for r in rows}

def audit_identity():
    masks=load(ROI)
    rna=load(RNA)
    scores=load(SCORE)
    if set(masks)!=set(rna) or set(masks)!=set(scores):
        raise ValueError("Frozen MRI/RNA/Hallmark patient sets do not match")
    with ICC.open(encoding="utf-8-sig",newline="") as f:
        stable=list(csv.DictReader(f))
    if len(stable)!=10 or len({r["feature"] for r in stable})!=10:
        raise ValueError("Expected exactly ten independently verified MRI ICC features")
    trusted={r["feature"] for r in stable if r["reliability_screen"]=="PASS"}
    if len(trusted)!=8 or not set(PRIMARY_FEATURES).issubset(trusted):
        raise ValueError("Frozen 8 reader-robust radiomics features changed")
    sap=SAP.read_text(encoding="utf-8")
    for token in (*PRIMARY_FEATURES,*HALLMARK,"12 primary"):
        if token not in sap:
            raise ValueError("Pre-outcome SAP not anchored to frozen hypothesis family: "+token)
    out=[]
    for pid in sorted(masks):
        m,r,s=masks[pid],rna[pid],scores[pid]
        if m["segmentation_qc_status"]!="PASS_GEOMETRY_WITH_REVIEW_FLAGS" or not m["pv_selected_roi_pixel_qc_run"].isdigit():
            raise ValueError("One image ROI lacks technical source QC")
        if any(m.get(k)!="NOT_ASSESSED" for k in
               ("expert_review","pretreatment_verified","eligible_radiogenomics")):
            raise ValueError("Unsupported MRI clinical/ROI eligibility promoted")
        if not (r["aliquot_barcode"].startswith(pid+"-01")
            and s["gdc_file_md5_check"]=="PASS"
            and s["clinical_eligibility"]=="NOT_ASSESSED"
            and s["gene_set_version"]=="MSIGDB_HALLMARK_v2025.1.Hs"):
            raise ValueError("RNA specimen/GDC QC or status drift")
        if r["aliquot_barcode"][:16]!=pid+"-01A":
            raise ValueError("Expected exact tumor specimen barcode")
        if int(s["all_gene_ids"])!=60660 or int(s["rank_universe_symbols"])!=19938:
            raise ValueError("GDC RNA frozen gene universe changed")
        for marker in HALLMARK:
            v=float(s[marker])
            if not -0.5<=v<=0.5:raise ValueError("RNA score outside frozen rank scale")
        if pid=="TCGA-BC-A10Y" and m["representative_tumor_number"]!="3":
            raise ValueError("Multilesion A10Y incorrectly reverted to tumor1")
        out.append({
            "patient_id":pid,
            "representative_tumor_number":m["representative_tumor_number"],
            "selected_roi_pixel_qc_run":m["pv_selected_roi_pixel_qc_run"],
            "same_primary_tumor_rna_specimen_barcode":r["aliquot_barcode"][:16],
            "gdc_rna_file_id":r["gdc_file_id"],
            "gene_set_score_source_qc":"PASS_TECHNICAL",
            "mri_pretherapy_adjudication":"NOT_VERIFIED",
            "same_hcc_lesion_mri_tissue_adjudication":"NOT_VERIFIED",
            "qualified_roi_radiologist_review":"NOT_ASSESSED",
            "exact_star_rna_aliquot_purity":"NOT_VERIFIED",
            "clinical_eligibility":"HOLD_UNRESOLVED_NOT_EXCLUDED",
            "mri_rna_association_performed":"NO",
        })
    return out,{
        "status":"PASS_FROZEN_SOURCE_IDENTITIES_NOT_ELIGIBILITY",
        "candidates":14,"rna_primary_tumor_specimen_match":14,
        "selected_index_roi_qc_technical":14,
        "reliable_reader_features":len(trusted),
        "primary_hypotheses":len(PRIMARY_FEATURES)*len(HALLMARK),
        "radiologist_approved_roi":"NOT_ASSESSED",
        "mri_tissue_pretherapy_proven":"NOT_VERIFIED",
        "eligible_n":"NOT_ASSESSED",
        "source_sha256":{str(p):hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in (ROI,RNA,SCORE,ICC,SAP)},
        "mri_rna_correlations_computed":False,
        "claim_ceiling":"S0",
    }

def join_evidence(clinical,purity,source,publication,acquisition):
    if (set(clinical)!=set(purity) or set(clinical)!=set(source)
        or set(clinical)!=set(publication) or set(clinical)!=set(acquisition)):
        raise ValueError("Parallel jobs have different 14-patient denominators")
    rows=[]
    for pid in sorted(source):
        c,p,s,pub,acq=clinical[pid],purity[pid],source[pid],publication[pid],acquisition[pid]
        if (acq["final_clinical_eligibility"]!="HOLD_UNRESOLVED_NOT_EXCLUDED"
           or acq["exact_PV_series_magnetic_field_strength"]!="NOT_VERIFIED"
           or acq["metadata_to_exact_PV_series_link"]!="NOT_VERIFIED"
           or acq["selected_index_tumor_review"]!="NOT_ASSESSED"
           or acq["patient_mri_pretreatment"]!="NOT_VERIFIED"
           or acq["selected_tumor_number"]!=s["representative_tumor_number"]):
            raise ValueError("Acquisition metadata was misread as same-PV-series or clinical validation")
        if not float(acq["voxel_spacing_z_mm"])>0:
            raise ValueError("Invalid native acquisition spacing")
        if (pub["clinical_eligibility"]!="HOLD_UNRESOLVED_NOT_EXCLUDED" or
            pub["patient_specific_pretreatment_mri_verified"]!="NOT_VERIFIED" or
            pub["selected_roi_expert_review_reconfirmed"]!="NOT_ASSESSED" or
            pub["mri_to_exact_rna_lesion_match"]!="NOT_VERIFIED"):
            raise ValueError("Published radiologist evidence was misread as clinical eligibility")
        if (pub["official_published_hcc_dice_present"]!="YES" or
            pub["selected_index_tumor_number"]!=s["representative_tumor_number"] or
            pub["official_expert_readers_in_publication"]!="TWO_BOARD_CERTIFIED_ABDOMINAL_RADIOLOGISTS_SOURCE_DATASET"):
            raise ValueError("Official published tumor reader/selected index lesion evidence is missing")
        if c["clinical_eligibility"]!="HOLD_UNRESOLVED_NOT_EXCLUDED":
            raise ValueError("Clinical job promoted or excluded patient without reviewer")
        if (p["eligible"]!="NOT_ASSESSED" or
            p["mri_pretherapy"]!="NOT_VERIFIED" or
            p["exact_rna_aliquot_purity"]!="NOT_VERIFIED"):
            raise ValueError("Purity proxy job promoted eligibility or RNA aliquot truth")
        if s["clinical_eligibility"]!="HOLD_UNRESOLVED_NOT_EXCLUDED" or s["mri_rna_association_performed"]!="NO":
            raise ValueError("Source identity improperly authorizes biological testing")
        if p["specimen_barcode"]!=s["same_primary_tumor_rna_specimen_barcode"]:
            raise ValueError("PanCanAtlas and GDC sample barcode mismatch")
        result=dict(s)
        result.update({
            "clinical_review_priority":c["priority_refined"],
            "hcc_context_dated_treatment_records":c["hcc_diagnosis_context_dated_yes_records"],
            "other_anatomic_site_dated_records":c["different_anatomic_site_records"],
            "abs_dna_purity_proxy":p["absolute_dna_purity"],
            "historical_cpe":p["historical_cpe"],
            "purity_review_priority":p["priority"],
            "purity_proxy_difference_over_0_20":p["difference_abs_gt_0_20"],
            "published_expert_readers_source":pub["official_expert_readers_in_publication"],
            "published_hcc_dice_metric":pub["official_published_hcc_dice_present"],
            "pv_slice_thickness_mm":acq["voxel_spacing_z_mm"],
            "pv_z_to_inplane_ratio":acq["z_to_inplane_ratio"],
            "pv_native_anisotropy_flag":acq["native_spacing_flag"],
            "published_patient_level_field_strength_t":acq["study_field_strength_values_t"],
            "scanner_vendor_status":acq["scanner_manufacturer"],
        })
        rows.append(result)
    level=Counter(r["clinical_review_priority"].split("_")[0] for r in rows)
    if level!={"P0":4,"P1":5,"P2":5}:
        raise ValueError("Clinical source-category outcome shifted unexpectedly")
    if sum(r["purity_proxy_difference_over_0_20"]=="YES" for r in rows)<1:
        raise ValueError("Unexplained published DNA-vs-CPE discrepancy vanished")
    if next(r for r in rows if r["patient_id"]=="TCGA-BC-A5W4")["clinical_review_priority"]!="P1_OTHER_ANATOMIC_SITE_DATED_TREATMENT_REVIEW":
        raise ValueError("Non-liver operation incorrectly promoted to HCC-treatment")
    combined={
        "status":"PASS_BATCH_TECHNICAL_EVIDENCE_CONSISTENCY",
        "checked_at_utc":datetime.now(timezone.utc).isoformat(),
        "technical_candidate_count":14,
        "clinical_review_priority_counts":dict(level),
        "n_patients_with_purity_difference_gt_0_20":
            sum(r["purity_proxy_difference_over_0_20"]=="YES" for r in rows),
        "n_absolute_dna_proxy_present":sum(bool(r["abs_dna_purity_proxy"]) for r in rows),
        "n_historical_cpe_present":sum(bool(r["historical_cpe"]) for r in rows),
        "n_official_source_14_reader_metric_confirmed":sum(r["published_hcc_dice_metric"]=="YES" for r in rows),
        "n_native_high_anisotropy_patients":sum(r["pv_native_anisotropy_flag"]=="HIGH_THROUGHPLANE_ANISOTROPY_REVIEW" for r in rows),
        "native_high_anisotropy_patients":[r["patient_id"] for r in rows if r["pv_native_anisotropy_flag"]=="HIGH_THROUGHPLANE_ANISOTROPY_REVIEW"],
        "source_verified_exact_PV_scanner_vendor_patients":0,
        "n_independently_reapproved_mri_to_rna_same_lesion":0,
        "patients_with_overlapping_treatment_p0_and_purity_p0":[
            r["patient_id"] for r in rows if r["clinical_review_priority"].startswith("P0")
            and r["purity_review_priority"].startswith("P0")],
        "hcc14_temporal_gate":"PARTIAL_HOLD",
        "hcc16_rna_purity_gate":"PARTIAL_HOLD",
        "hcc17_final_paired_n_gate":"PENDING_HOLD",
        "hcc20_mri_rna_association_gate":"PENDING_DO_NOT_RUN",
        "final_eligible_n":"NOT_ASSESSED",
        "clinical_excluded_n":"NOT_ASSESSED",
        "unresolved_n":14,
        "maximum_claim":"S0",
        "predefined_min_eligible_n_for_12_tests":10,
        "hypothetical_after_excluding_all_four_p0_max_n":10,
        "hypothetical_after_excluding_four_p0_and_one_additional_max_n":9,
        "scenario_caution":"These are hypothetical denominators, not actual exclusions or verified eligible counts.",
        "go_hold_stop":{
            "technical_crosssource_qc":"GO",
            "clinical_mri_tissue_eligibility":"HOLD",
            "primary_12_association_tests":"STOP_UNTIL_QUALIFIED"
        },
        "mri_rna_correlations_computed":False,
        "note":"This batch verifies known public-derived evidence only. It cannot reconstruct true MRI scan-to-treatment timing or clinician lesion identity; no p-values calculated.",
    }
    return rows,combined

def save_csv(path,rows,fields):
    with Path(path).open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore")
        w.writeheader();w.writerows(rows)

def offline_test():
    r,s=audit_identity()
    assert len(r)==14 and s["primary_hypotheses"]==12
    assert next(x for x in r if x["patient_id"]=="TCGA-BC-A10Y")["representative_tumor_number"]=="3"
    # Negative test cannot use a shortened denominator.
    try:join_evidence({"x":{}},{},{"y":{}},{},{})
    except ValueError:pass
    else:raise AssertionError("Cross-job source mismatch was not rejected")
    assert all(x["clinical_eligibility"]=="HOLD_UNRESOLVED_NOT_EXCLUDED" for x in r)
    print("HCC_PARALLEL_BATCH_FROZEN_SOURCE_AND_FAIL_CLOSED_OFFLINE_PASS")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--mode",choices=("source","assemble"),default="source")
    p.add_argument("--offline-test",action="store_true")
    p.add_argument("--out-dir",default="artifacts/hcc_batch_source")
    p.add_argument("--clinical",default=REFINED)
    p.add_argument("--purity",default=PURITY)
    p.add_argument("--source",default=SOURCE)
    p.add_argument("--publication",default=PUBLICATION)
    p.add_argument("--acquisition",default=ACQUISITION)
    args=p.parse_args()
    if args.offline_test:return offline_test()
    out=Path(args.out_dir);out.mkdir(parents=True,exist_ok=True)
    if args.mode=="source":
        rows,summary=audit_identity()
        save_csv(out/"hcc_mri14_frozen_source_identity.csv",rows,list(rows[0]))
        name="hcc_mri14_source_identity_summary.json"
    else:
        rows,summary=join_evidence(load(args.clinical),load(args.purity),load(args.source),load(args.publication),load(args.acquisition))
        save_csv(out/"hcc_mri14_joint_clinical_purity_image_rna_gate.csv",rows,FIELDS)
        name="hcc_batch_multi_job_readiness_summary.json"
    (out/name).write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(summary,ensure_ascii=False))

if __name__=="__main__":
    main()
