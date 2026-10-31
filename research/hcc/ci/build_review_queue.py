#!/usr/bin/env python3
"""Prioritized manual CT/ROI review queue for HCC radiogenomics.

Only public metadata. No automatic inclusion, no tumor mask inference.
"""
import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

USEFUL_PHASES={"explicit_pv_text_candidate":0,"generic_venous_text_candidate":1,
               "unclassified_text_candidate":2,"arterial_text_candidate":3}
FIELDS=("patient_id","review_priority","review_reason","rna_primary_tumor_file_linked",
        "phase_screen","explicit_pv_series","generic_venous_series",
        "ct_linked_liver_seg_series","candidate_ct_series_uids",
        "candidate_ct_series_descriptions","candidate_ct_image_counts",
        "tumor_roi_status","pretreatment_ct_status","ct_phase_status",
        "qualified_radiogenomics_status")


def load(path,required):
    with Path(path).open(encoding="utf-8-sig",newline="") as f:
        r=csv.DictReader(f)
        if not r.fieldnames or not set(required).issubset(r.fieldnames):
            raise ValueError(f"Missing columns in {path}: {required}")
        return list(r)


def single(rows,key):
    mapping={}
    for x in rows:
        name=x[key]
        if name in mapping:
            raise ValueError(f"Duplicate patient: {name}")
        mapping[name]=x
    return mapping


def number(value):
    try:
        return max(0,int(value))
    except (TypeError,ValueError):
        return 0


def choose_rank(explicit_pv,generic_venous,liver):
    if explicit_pv and liver: return 1,"explicit PV series; CT-matched liver organ mask"
    if explicit_pv: return 2,"explicit PV series; tumor ROI not provided"
    if generic_venous and liver: return 3,"generic venous label; CT-matched liver mask"
    if generic_venous: return 4,"generic venous label; tumor ROI not provided"
    if liver: return 5,"CT-matched liver mask; CT phase unclassified"
    return 6,"CT phase unclassified; no CT-matched liver mask"


def build(phase,roi,rna,series):
    p=single(phase,"patient_id")
    i=single(roi,"patient_id")
    r=single(rna,"patient_id")
    if set(p)!=set(i) or set(p)!=set(r):
        raise ValueError("Patient crosswalk keys differ among CT, IDC, RNA files")
    by_patient=defaultdict(list)
    for s in series:
        if s["PatientID"] in p and s["phase_text_prescreen"] in USEFUL_PHASES:
            by_patient[s["PatientID"]].append(s)
    output=[]
    for pid,ct in p.items():
        iv=i[pid]
        rv=r[pid]
        if rv["rna_lineage_status"]!="TUMOR_RNA_BARCODE_LINK_CONFIRMED":
            raise ValueError(f"RNA file-to-tumor linkage unqualified: {pid}")
        pv=number(ct.get("explicit_pv_series"))
        v=number(ct.get("generic_venous_series"))
        liver=number(iv.get("liver_seg_references_tcia_ct"))
        rank,why=choose_rank(pv,v,liver)
        options=sorted(by_patient[pid],key=lambda s:(
            USEFUL_PHASES.get(s["phase_text_prescreen"],99),
            -number(s.get("ImageCount")),str(s.get("SeriesInstanceUID"))))[:3]
        output.append({
            "patient_id":pid,"review_priority":f"P{rank}","review_reason":why,
            "rna_primary_tumor_file_linked":"YES",
            "phase_screen":ct["phase_screen"],
            "explicit_pv_series":pv,"generic_venous_series":v,
            "ct_linked_liver_seg_series":liver,
            "candidate_ct_series_uids":"|".join(s["SeriesInstanceUID"] for s in options),
            "candidate_ct_series_descriptions":"|".join(str(s.get("SeriesDescription") or "") for s in options),
            "candidate_ct_image_counts":"|".join(str(s.get("ImageCount") or "") for s in options),
            "tumor_roi_status":"NOT_VERIFIED",
            "pretreatment_ct_status":"NOT_VERIFIED",
            "ct_phase_status":"TEXT_PRESCREEN_ONLY",
            "qualified_radiogenomics_status":"NOT_ASSESSED",
        })
    output.sort(key=lambda row:(number(row["review_priority"][1:]),row["patient_id"]))
    counts=Counter(row["review_priority"] for row in output)
    summary={
        "status":"MANUAL_REVIEW_QUEUE_READY",
        "patients":len(output),
        "priority_counts":dict(sorted(counts.items())),
        "final_tumor_roi_verified_patients":0,
        "eligible_radiogenomics_patients":"NOT_ASSESSED",
        "note":"P1-P6 are review ordering heuristics, not statistical eligibility or clinical CT-phase evidence."}
    return output,summary


def offline_test():
    phase=[{"patient_id":"TCGA-AA-0001","phase_screen":"EXPLICIT_PV_METADATA_CANDIDATE",
            "explicit_pv_series":"1","generic_venous_series":"0"}]
    roi=[{"patient_id":"TCGA-AA-0001","liver_seg_references_tcia_ct":"2"}]
    rna=[{"patient_id":"TCGA-AA-0001","rna_lineage_status":"TUMOR_RNA_BARCODE_LINK_CONFIRMED"}]
    series=[{"PatientID":"TCGA-AA-0001","phase_text_prescreen":"explicit_pv_text_candidate",
             "SeriesInstanceUID":"S1","ImageCount":"98","SeriesDescription":"PORTAL"}]
    out,status=build(phase,roi,rna,series)
    assert out[0]["review_priority"]=="P1"
    assert out[0]["tumor_roi_status"]=="NOT_VERIFIED"
    assert status["eligible_radiogenomics_patients"]=="NOT_ASSESSED"
    assert choose_rank(0,0,0)[0]==6
    print("HCC_REVIEW_QUEUE_OFFLINE_TEST_PASS")


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--output",default="artifacts/hcc_tcia")
    ap.add_argument("--offline-test",action="store_true")
    args=ap.parse_args()
    if args.offline_test:
        offline_test()
        return
    root=Path(args.output)
    phase=load(root/"tcga_ct_phase_patient_prescreen.csv",{"patient_id","phase_screen","explicit_pv_series","generic_venous_series"})
    roi=load(root/"tcga_idc_roi_patient_screen.csv",{"patient_id","liver_seg_references_tcia_ct"})
    rna=load(root/"tcga_gdc_rna_patient_lineage.csv",{"patient_id","rna_lineage_status"})
    series=load(root/"tcga_ct_phase_series_prescreen.csv",{"PatientID","phase_text_prescreen","SeriesInstanceUID"})
    rows,summary=build(phase,roi,rna,series)
    with (root/"tcga_hcc_radiogenomics_review_queue.csv").open("w",encoding="utf-8",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    (root/"tcga_hcc_radiogenomics_review_queue_summary.json").write_text(
        json.dumps(summary,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps(summary,ensure_ascii=False))


if __name__=="__main__":
    main()
