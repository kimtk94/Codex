#!/usr/bin/env python3
"""TCIA CT phase text prescreen. Heuristics never establish CT/ROI eligibility."""
import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

PV = re.compile(r"\bPORTAL\b|\bP[.\s]?VENOUS\b|\bPV\b", re.I)
VENOUS = re.compile(r"\bVENOUS\b", re.I)
ARTERIAL = re.compile(r"\bARTERIAL\b|\bLATE ART[.]?\b", re.I)
LOCATOR = re.compile(r"SCOUT|TOPOGRAM|LOCALIZER|MONITORING|PREMONITORING|SURVIEW|BOLUS TRACK", re.I)
REFORMAT = re.compile(r"\bCOR(?:ONAL)?\b|\bSAG(?:ITTAL)?\b|\bMPR\b|REFORMAT", re.I)

def label(row):
    desc = str(row.get("SeriesDescription") or "")
    try:
        images = int(row.get("ImageCount") or 0)
    except (ValueError, TypeError):
        images = 0
    if LOCATOR.search(desc):
        return "excluded_locator_monitor"
    if REFORMAT.search(desc):
        return "excluded_reformat"
    if images < 30:
        return "excluded_short_series"
    if PV.search(desc):
        return "explicit_pv_text_candidate"
    if VENOUS.search(desc):
        return "generic_venous_text_candidate"
    if ARTERIAL.search(desc):
        return "arterial_text_candidate"
    return "unclassified_text_candidate"

def load(path, required):
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not set(required).issubset(reader.fieldnames):
            raise ValueError(f"Missing expected CSV columns in {path}: {required}")
        return list(reader)

def analyze(series, candidates):
    patient_ids = {r["patient_id"] for r in candidates}
    if not patient_ids:
        raise ValueError("Empty CT-RNA patient overlap manifest")
    groups = defaultdict(list)
    for row in series:
        if row["PatientID"] in patient_ids:
            item = dict(row)
            item["phase_text_prescreen"] = label(row)
            groups[row["PatientID"]].append(item)
    if set(groups) != patient_ids:
        raise ValueError("Missing CT series for candidate patient")
    patients, series_out = [], []
    for pid in sorted(patient_ids):
        rows = groups[pid]
        series_out.extend(rows)
        counts = Counter(x["phase_text_prescreen"] for x in rows)
        phase = ("EXPLICIT_PV_METADATA_CANDIDATE" if counts["explicit_pv_text_candidate"] else
                 "GENERIC_VENOUS_METADATA_CANDIDATE" if counts["generic_venous_text_candidate"] else
                 "NO_PV_TEXT_EVIDENCE")
        patients.append({
            "patient_id": pid,
            "ct_series_count": len(rows),
            "explicit_pv_series": counts["explicit_pv_text_candidate"],
            "generic_venous_series": counts["generic_venous_text_candidate"],
            "arterial_series": counts["arterial_text_candidate"],
            "unclassified_series": counts["unclassified_text_candidate"],
            "phase_screen": phase,
            "pretreatment_status": "UNVERIFIED",
            "tumor_roi_status": "UNVERIFIED",
            "image_phase_status": "UNVERIFIED",
            "rna_file_aliquot_status": "UNVERIFIED",
            "eligible_for_radiogenomics": "NOT_ASSESSED",
        })
    statuses = Counter(p["phase_screen"] for p in patients)
    summary = {
        "status": "PASS_METADATA_PRESCREEN_ONLY",
        "matched_ct_rna_metadata_patients": len(patient_ids),
        "explicit_portal_venous_text_patients": statuses["EXPLICIT_PV_METADATA_CANDIDATE"],
        "generic_venous_only_text_patients": statuses["GENERIC_VENOUS_METADATA_CANDIDATE"],
        "no_pv_venous_text_patients": statuses["NO_PV_TEXT_EVIDENCE"],
        "eligible_ct_seg_rna_pairs": "NOT_ASSESSED",
        "min_images_per_series": 30,
        "notes": [
            "SeriesDescription string matching does not prove DICOM phase or scan timing.",
            "Excluded short/reformat/locator series are text/length rules, not expert image review.",
            "No tumor ROI, pretreatment status, or GDC file-to-tumor-aliquot has been validated.",
        ],
    }
    return patients, series_out, summary

def offline_test():
    examples = [
        ("P.VENOUS 3.0 B40F", 100, "explicit_pv_text_candidate"),
        ("PORTAL 3.0 B40F", 80, "explicit_pv_text_candidate"),
        ("VENOUS PHASE 3.0", 80, "generic_venous_text_candidate"),
        ("ARTERIAL 3.0 B40F", 110, "arterial_text_candidate"),
        ("CORONAL PORTAL 3.0", 100, "excluded_reformat"),
        ("SCOUT", 1, "excluded_locator_monitor"),
        ("AXIAL", 1, "excluded_short_series"),
        ("AXIAL", 80, "unclassified_text_candidate"),
    ]
    for desc, images, expected in examples:
        assert label({"SeriesDescription":desc,"ImageCount":images}) == expected
    ct = [{"PatientID":"TCGA-AA-0001","SeriesDescription":"PORTAL 3.0","ImageCount":"80"},
          {"PatientID":"TCGA-BB-0002","SeriesDescription":"ARTERIAL 3.0","ImageCount":"80"}]
    patients, _, report = analyze(ct, [{"patient_id":"TCGA-AA-0001"},{"patient_id":"TCGA-BB-0002"}])
    assert report["matched_ct_rna_metadata_patients"] == 2
    assert report["explicit_portal_venous_text_patients"] == 1
    assert report["no_pv_venous_text_patients"] == 1
    assert all(p["eligible_for_radiogenomics"] == "NOT_ASSESSED" for p in patients)
    print("HCC_CT_PHASE_PRESCREEN_OFFLINE_TEST_PASS")

def write_csv(path, rows):
    if not rows:
        raise ValueError("Empty prescreen table")
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ct-csv", default="artifacts/hcc_tcia/TCGA-LIHC_ct_series.csv")
    parser.add_argument("--matches-csv", default="artifacts/hcc_tcia/tcga_rna_overlap_candidates.csv")
    parser.add_argument("--output", default="artifacts/hcc_tcia")
    parser.add_argument("--offline-test", action="store_true")
    args = parser.parse_args()
    if args.offline_test:
        offline_test()
        return
    ct = load(args.ct_csv, ("PatientID","SeriesDescription","ImageCount"))
    matched = load(args.matches_csv, ("patient_id",))
    patients, series, report = analyze(ct, matched)
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "tcga_ct_phase_patient_prescreen.csv", patients)
    write_csv(out / "tcga_ct_phase_series_prescreen.csv", series)
    (out / "tcga_ct_phase_prescreen_summary.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))

if __name__ == "__main__":
    main()
