#!/usr/bin/env python3
"""HCC same-series CT-phase/liver-SEG joint audit and actionable manual-review table.

Patient having both a PV-labelled CT and some liver SEG does NOT establish
that the liver SEG references that *PV CT*. Clinical image/ROI assessment is
not performed and tumor ROI is always unverified.
"""
import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

CT_FIELDS = ("PatientID","StudyInstanceUID","SeriesInstanceUID",
             "SeriesDescription","ImageCount","phase_text_prescreen")
SEG_FIELDS = ("patient_id","segmentation_label_class","references_tcia_ct_series",
              "referenced_tcia_ct_series")
PHASE_RANK = {"explicit_pv_text_candidate": 0, "generic_venous_text_candidate": 1,
              "arterial_text_candidate": 3, "unclassified_text_candidate": 2}
FIELDS = [
    "patient_id","review_tier","review_rationale",
    "selected_ct_series_uid","selected_ct_study_uid","selected_ct_description",
    "selected_ct_image_count","selected_ct_phase_text_label",
    "selected_ct_has_exact_liver_mask",
    "patient_pv_text_ct_series","patient_ct_referenced_liver_seg_series",
    "same_series_pv_text_and_liver_mask_count",
    "same_series_generic_venous_and_liver_mask_count",
    "tumor_mask_verified","phase_verified","pretreatment_verified",
    "rna_primary_tumor_file_linked","radiogenomics_eligible"
]


def read(path, required):
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not set(required).issubset(reader.fieldnames):
            raise ValueError("Missing required columns in "+str(path)+": "+str(required))
        return list(reader)


def number(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def classify_patient(pv_ct, v_ct, liver_ct, same_pv, same_v):
    if same_pv: return ("P1", "explicit PV CT series has exact liver organ SEG reference")
    if pv_ct and liver_ct: return ("P2", "PV CT and liver organ SEG exist only on different CT series")
    if pv_ct: return ("P3", "explicit PV CT; no CT-linked liver organ SEG")
    if same_v: return ("P4", "generic venous CT series has exact liver organ SEG reference")
    if v_ct and liver_ct: return ("P5", "generic venous CT and liver organ SEG exist on other series")
    if v_ct: return ("P6", "generic venous CT without linked liver SEG")
    if liver_ct: return ("P7", "only unclassified/other CT linked to liver organ SEG")
    return ("P8", "no convincing venous CT metadata or exact liver mask")


def audit(ct_rows, seg_rows, rna_rows):
    expected = {r["patient_id"] for r in rna_rows
                if r.get("rna_lineage_status") == "TUMOR_RNA_BARCODE_LINK_CONFIRMED"}
    if not expected:
        raise ValueError("No tumor file-linked RNA cases")
    all_ids={r["patient_id"] for r in rna_rows}
    if expected != all_ids:
        raise ValueError("Unverified RNA patients must not enter series-review queue")
    ct_by = defaultdict(list)
    for row in ct_rows:
        if row["PatientID"] in expected:
            ct_by[row["PatientID"]].append(row)
    liver_by = defaultdict(set)
    seg_seen = set()
    for row in seg_rows:
        if row["patient_id"] not in expected:
            continue
        if (row.get("segmentation_label_class") != "LIVER_ORGAN_SEG_ONLY"
                or row.get("references_tcia_ct_series") != "YES"):
            continue
        key=(row["patient_id"],row.get("seg_series_uid",""))
        if key in seg_seen:
            continue
        seg_seen.add(key)
        for uid in str(row["referenced_tcia_ct_series"]).split("|"):
            if uid:
                liver_by[row["patient_id"]].add(uid)
    rows=[]
    for patient_id in sorted(expected):
        patient_ct = ct_by[patient_id]
        if not patient_ct:
            raise ValueError(f"Missing CT series for matched patient {patient_id}")
        ct_uids={r["SeriesInstanceUID"] for r in patient_ct}
        liver_ct_uids=liver_by[patient_id] & ct_uids
        pv=[r for r in patient_ct if r["phase_text_prescreen"] == "explicit_pv_text_candidate"]
        v=[r for r in patient_ct if r["phase_text_prescreen"] == "generic_venous_text_candidate"]
        same_pv=[r for r in pv if r["SeriesInstanceUID"] in liver_ct_uids]
        same_v=[r for r in v if r["SeriesInstanceUID"] in liver_ct_uids]
        tier,rationale = classify_patient(bool(pv),bool(v),bool(liver_ct_uids),
                                          bool(same_pv),bool(same_v))
        # Prefer phase-labelled CT first. Within the same phase, prefer CT with
        # exact source mask. No automatic clinical quality conclusions.
        ranked=sorted(patient_ct,key=lambda r: (
            PHASE_RANK.get(r["phase_text_prescreen"], 9),
            0 if r["SeriesInstanceUID"] in liver_ct_uids else 1,
            -number(r.get("ImageCount")),
            r["SeriesInstanceUID"],
        ))
        chosen=ranked[0]
        rows.append({
            "patient_id":patient_id, "review_tier":tier,
            "review_rationale":rationale,
            "selected_ct_series_uid":chosen["SeriesInstanceUID"],
            "selected_ct_study_uid":chosen.get("StudyInstanceUID",""),
            "selected_ct_description":chosen.get("SeriesDescription",""),
            "selected_ct_image_count":chosen.get("ImageCount",""),
            "selected_ct_phase_text_label":chosen["phase_text_prescreen"],
            "selected_ct_has_exact_liver_mask":(
                "YES" if chosen["SeriesInstanceUID"] in liver_ct_uids else "NO"),
            "patient_pv_text_ct_series":len(pv),
            "patient_ct_referenced_liver_seg_series":len(liver_ct_uids),
            "same_series_pv_text_and_liver_mask_count":len(same_pv),
            "same_series_generic_venous_and_liver_mask_count":len(same_v),
            "tumor_mask_verified":"NO",
            "phase_verified":"NO",
            "pretreatment_verified":"NO",
            "rna_primary_tumor_file_linked":"YES",
            "radiogenomics_eligible":"NOT_ASSESSED",
        })
    rows.sort(key=lambda r:(int(r["review_tier"][1:]),r["patient_id"]))
    tiers=Counter(row["review_tier"] for row in rows)
    return rows, {
        "status":"PASS_SAME_SERIES_METADATA_QC",
        "patients":len(rows),
        "tier_counts":dict(sorted(tiers.items())),
        "patients_with_same_series_PV_and_liver_mask":sum(
            number(r["same_series_pv_text_and_liver_mask_count"])>0 for r in rows),
        "patients_with_PV_but_liver_mask_on_other_CT_series":tiers["P2"],
        "patients_with_any_liver_mask_CT_series":sum(
            number(r["patient_ct_referenced_liver_seg_series"])>0 for r in rows),
        "verified_tumor_mask_patients":0,
        "eligible_radiogenomics_patients":"NOT_ASSESSED",
        "warning":"PV is a text metadata heuristic; exact organ-mask CT UID is NOT HCC tumor-mask proof.",
    }


def offline_test():
    ct=[{"PatientID":"TCGA-AA-0001","StudyInstanceUID":"ST","SeriesInstanceUID":"PV1",
         "SeriesDescription":"Portal venous","ImageCount":"80",
         "phase_text_prescreen":"explicit_pv_text_candidate"},
        {"PatientID":"TCGA-AA-0001","StudyInstanceUID":"ST","SeriesInstanceUID":"NONPV",
         "SeriesDescription":"Abd","ImageCount":"80",
         "phase_text_prescreen":"unclassified_text_candidate"},
        {"PatientID":"TCGA-BB-0002","StudyInstanceUID":"ST2","SeriesInstanceUID":"PV2",
         "SeriesDescription":"Portal venous","ImageCount":"80",
         "phase_text_prescreen":"explicit_pv_text_candidate"}]
    seg=[{"patient_id":"TCGA-AA-0001","seg_series_uid":"SEG1",
          "segmentation_label_class":"LIVER_ORGAN_SEG_ONLY",
          "references_tcia_ct_series":"YES","referenced_tcia_ct_series":"NONPV"},
         {"patient_id":"TCGA-BB-0002","seg_series_uid":"SEG2",
          "segmentation_label_class":"LIVER_ORGAN_SEG_ONLY",
          "references_tcia_ct_series":"YES","referenced_tcia_ct_series":"PV2"}]
    rna=[{"patient_id":p,"rna_lineage_status":"TUMOR_RNA_BARCODE_LINK_CONFIRMED"}
         for p in ("TCGA-AA-0001","TCGA-BB-0002")]
    rows,info=audit(ct,seg,rna)
    assert info["tier_counts"] == {"P1":1,"P2":1}
    assert info["patients_with_same_series_PV_and_liver_mask"] == 1
    a=next(r for r in rows if r["patient_id"]=="TCGA-AA-0001")
    assert a["review_tier"]=="P2" and a["selected_ct_has_exact_liver_mask"]=="NO"
    assert all(r["radiogenomics_eligible"]=="NOT_ASSESSED" for r in rows)
    print("HCC_SAME_SERIES_CT_ROI_OFFLINE_TEST_PASS")


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",default="artifacts/hcc_tcia")
    parser.add_argument("--offline-test",action="store_true")
    args=parser.parse_args()
    if args.offline_test:
        offline_test()
        return
    root=Path(args.output)
    ct=read(root/"tcga_ct_phase_series_prescreen.csv",CT_FIELDS)
    seg=read(root/"tcga_idc_segmentation_metadata.csv",SEG_FIELDS)
    rna=read(root/"tcga_gdc_rna_patient_lineage.csv",
             ("patient_id","rna_lineage_status"))
    rows,summary=audit(ct,seg,rna)
    with (root/"tcga_hcc_same_series_review_queue.csv").open(
            "w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    (root/"tcga_hcc_same_series_review_summary.json").write_text(
        json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(summary,ensure_ascii=False))


if __name__=="__main__":
    main()
