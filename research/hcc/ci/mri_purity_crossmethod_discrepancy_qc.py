#!/usr/bin/env python3
"""Public HCC 14 specimen-level ABSOLUTE vs historical consensus purity QC.

This compares *different methods and potential portion/analyte differences*,
not repeated measurements of the identical STAR RNA aliquot. Flags methods
differing by >0.20, missingness and low values, but cannot exclude a patient
or manufacture qualified MRI–RNA sample counts.
"""
import argparse,csv,json,statistics
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path

ABS="research/hcc/HCC_MRI_14_PANCAN_ABSOLUTE_PURITY_PROXY_20261031.csv"
CPE="research/hcc/HCC_MRI_14_ARAN2015_CPE_REFERENCE_PURITY_20261031.csv"
FIELDS=("patient_id","specimen_barcode","absolute_dna_purity","historical_cpe",
        "historical_estimate","historical_lump","historical_ihc",
        "dna_minus_cpe","difference_abs_gt_0_20","absolute_low_lt_0_50",
        "cpe_low_lt_0_50","priority","measurement_provenance",
        "mri_pretherapy","exact_rna_aliquot_purity","eligible")


def load(path):
    with Path(path).open(encoding="utf-8",newline="") as h:
        rows=list(csv.DictReader(h))
    if len(rows)!=14 or len({r["patient_id"] for r in rows})!=14:
        raise ValueError("Expected 14 unique specimens")
    return {r["patient_id"]:r for r in rows}


def num(v):
    return float(v) if str(v).strip() else None


def join(a,b):
    if set(a)!=set(b):
        raise ValueError("ABS/CPE patient list mismatched")
    rows=[]
    for pid in sorted(a):
        x=a[pid];y=b[pid]
        if x["rna_primary_tumor_specimen_16char"]!=y["old_reference_tcga_sample_barcode"]:
            raise ValueError("ABS/CPE 16-character specimen does not agree")
        if x["clinical_eligibility"]!="NOT_ASSESSED" or y["clinical_eligibility"]!="NOT_ASSESSED":
            raise ValueError("Clinical eligibility promoted by measurement table")
        d=num(x["absolute_purity_proxy"]);v=num(y["consensus_cpe"])
        if v is None or not (0<=v<=1):
            raise ValueError("Missing/out-of-range historical CPE")
        if d is not None and not 0<=d<=1:
            raise ValueError("Invalid ABSOLUTE proxy")
        delta=None if d is None else d-v
        bad_delta=delta is not None and abs(delta)>0.20
        low_d=d is not None and d<.50
        low_v=v<.50
        priority=("P0_METHOD_DISCORDANT_ABS_GT_0_20" if bad_delta
                  else "P0_BOTH_LOW_PURITY_PROXIES" if low_d and low_v
                  else "P1_MISSING_DNA_ABSOLUTE" if d is None
                  else "P1_LOW_ONE_METHOD" if low_d or low_v
                  else "P2_CROSS_METHOD_REVIEW")
        rows.append({
            "patient_id":pid,
            "specimen_barcode":x["rna_primary_tumor_specimen_16char"],
            "absolute_dna_purity":"" if d is None else d,
            "historical_cpe":v,
            "historical_estimate":y["old_reference_estimate"],
            "historical_lump":y["old_reference_lump"],
            "historical_ihc":y["old_reference_ihc"],
            "dna_minus_cpe":"" if delta is None else round(delta,6),
            "difference_abs_gt_0_20":"YES" if bad_delta else "NO",
            "absolute_low_lt_0_50":"YES" if low_d else "NO",
            "cpe_low_lt_0_50":"YES" if low_v else "NO",
            "priority":priority,
            "measurement_provenance":"DISTINCT_STUDIES_METHODS_DNA_VS_OLD_RNA_V2_NOT_EXACT_STAR_ALIQUOT",
            "mri_pretherapy":"NOT_VERIFIED",
            "exact_rna_aliquot_purity":"NOT_VERIFIED",
            "eligible":"NOT_ASSESSED"
        })
    return rows


def offline_test():
    a=load(ABS);b=load(CPE);rows=join(a,b)
    p={r["patient_id"]:r for r in rows}
    assert p["TCGA-G3-A3CJ"]["difference_abs_gt_0_20"]=="YES"
    assert p["TCGA-G3-A3CJ"]["priority"]=="P0_METHOD_DISCORDANT_ABS_GT_0_20"
    assert p["TCGA-DD-A4NJ"]["priority"]=="P1_MISSING_DNA_ABSOLUTE"
    assert len(rows)==14
    assert all(x["eligible"]=="NOT_ASSESSED" for x in rows)
    broken=dict(b)
    broken["TCGA-G3-A3CJ"]={**broken["TCGA-G3-A3CJ"],
                             "old_reference_tcga_sample_barcode":"TCGA-G3-A3CJ-02A"}
    try:join(a,broken)
    except ValueError:pass
    else:raise AssertionError("Specimen mismatch accepted")
    print("HCC_PURITY_CROSS_METHOD_SPECIMEN_ID_QC_OFFLINE_PASS")


def main():
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("--offline-test",action="store_true")
    p.add_argument("--out-dir",default="artifacts/hcc_purity_comparison")
    args=p.parse_args()
    if args.offline_test:return offline_test()
    rows=join(load(ABS),load(CPE))
    root=Path(args.out_dir);root.mkdir(parents=True,exist_ok=True)
    with (root/"hcc_mri_14_absolute_vs_cpe_purity_review.csv").open(
           "w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();w.writerows(rows)
    a=[float(x["absolute_dna_purity"]) for x in rows if x["absolute_dna_purity"]!=""]
    c=[float(x["historical_cpe"]) for x in rows]
    info={
        "status":"PASS_TWO_PUBLIC_PURITY_REFERENCES_CROSSWALK_REVIEW_ONLY",
        "generated_utc":datetime.now(timezone.utc).isoformat(),
        "n_frozen_tcga_mri_rna_candidates":len(rows),
        "n_same_specimen_absolute_dna_proxy":len(a),
        "n_same_specimen_historical_cpe_reference":len(c),
        "median_dna_purity_proxy":statistics.median(a),
        "median_historical_cpe":statistics.median(c),
        "n_absolute_below_0_50":sum(x<0.5 for x in a),
        "n_cpe_below_0_50":sum(x<0.5 for x in c),
        "n_abs_difference_over_0_20":sum(x["difference_abs_gt_0_20"]=="YES" for x in rows),
        "status_counts":dict(Counter(x["priority"] for x in rows)),
        "highest_discordance":[
            {"patient_id":x["patient_id"],"absolute":x["absolute_dna_purity"],
             "cpe":x["historical_cpe"],"delta":x["dna_minus_cpe"]}
            for x in rows if x["difference_abs_gt_0_20"]=="YES"],
        "pretherapy_mri_verified":0,
        "exact_star_rna_aliquot_purity_verified":0,
        "clinically_eligible_paired_n":"NOT_ASSESSED",
        "mri_rna_associations_run":False,
        "claim_ceiling":"S0",
        "warning":"Cross-method discrepancy may reflect biology, source aliquot/portion or model; no automatic exclusion or selection of preferred estimate."
    }
    (root/"hcc_mri_purity_crossmethod_qc_summary.json").write_text(
        json.dumps(info,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(info,ensure_ascii=False))
if __name__=="__main__":main()
