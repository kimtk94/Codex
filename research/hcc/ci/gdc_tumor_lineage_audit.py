#!/usr/bin/env python3
"""Audit GDC RNA file -> associated biospecimen identifiers for TCIA CT-linked cases.

Reads PUBLIC metadata; never downloads RNA values, DICOM images or hospital records.
A TCGA barcode association is evidence of the file's biospecimen lineage,
not a full image/tissue/ROI eligibility determination.
"""
import argparse
import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from tcga_rna_overlap_audit import fetch_gdc_files, normalize_id

PRIMARY_CODE = "01"
FIELDS = (
    "patient_id", "file_id", "file_name", "associated_entities",
    "sample_type_codes", "file_biospecimen_status", "reason",
)


def sample_code(entity_barcode, patient_id):
    parts = str(entity_barcode or "").strip().upper().split("-")
    if len(parts) < 4 or "-".join(parts[:3]) != patient_id:
        return ""
    if len(parts[3]) < 2 or not parts[3][:2].isdigit():
        return ""
    return parts[3][:2]


def classify_file(file, patient_id):
    """Requires file-specific associated entity identifiers; case-level tumor is insufficient."""
    associates = file.get("associated_entities") or []
    if not isinstance(associates, list):
        return "", "UNRESOLVED_FILE_ASSOCIATION", "unexpected associated_entities structure"
    if not associates:
        return "", "UNRESOLVED_FILE_ASSOCIATION", "no file-specific associated entities"
    codes = [sample_code(x.get("entity_submitter_id"), patient_id)
             for x in associates if isinstance(x, dict)]
    if not codes or any(not x for x in codes):
        return ",".join(sorted(set(x for x in codes if x))), "UNRESOLVED_FILE_ASSOCIATION", (
            "missing/foreign/malformed associated biospecimen barcode")
    uniq = set(codes)
    if uniq == {PRIMARY_CODE}:
        return PRIMARY_CODE, "PRIMARY_TUMOR_FILE_BARCODE_LINKED", (
            "associated GDC entities all bear TCGA primary solid tumor code 01")
    if PRIMARY_CODE in uniq:
        return ",".join(sorted(uniq)), "MIXED_SAMPLE_TYPES_REVIEW", (
            "one RNA file references both primary tumor and non-primary biospecimens")
    return ",".join(sorted(uniq)), "NONPRIMARY_FILE_BARCODE_LINKED", (
        "associated file barcodes contain no TCGA primary tumor sample code 01")


def evaluate(files, candidates):
    candidates_by_patient = {str(x["patient_id"]).strip().upper(): x for x in candidates}
    if not candidates_by_patient:
        raise ValueError("No CT x RNA metadata candidates")
    records, seen = [], set()
    for f in files:
        if f.get("data_type") != "Gene Expression Quantification":
            continue
        if (f.get("analysis") or {}).get("workflow_type") != "STAR - Counts":
            continue
        fid = f.get("file_id") or f.get("id")
        if not fid:
            continue
        for case in f.get("cases") or []:
            pid = normalize_id(case.get("submitter_id"))
            if pid not in candidates_by_patient or (pid, fid) in seen:
                continue
            seen.add((pid, fid))
            codes, status, reason = classify_file(f, pid)
            records.append({
                "patient_id": pid,
                "file_id": fid,
                "file_name": f.get("file_name") or "",
                "associated_entities": "|".join(
                    sorted(str(x.get("entity_submitter_id") or "")
                           for x in f.get("associated_entities") or []
                           if isinstance(x, dict))),
                "sample_type_codes": codes,
                "file_biospecimen_status": status,
                "reason": reason,
            })
    patient_counts = defaultdict(Counter)
    for item in records:
        patient_counts[item["patient_id"]][item["file_biospecimen_status"]] += 1
    patients = []
    for pid in sorted(candidates_by_patient):
        c = patient_counts[pid]
        good = c["PRIMARY_TUMOR_FILE_BARCODE_LINKED"]
        unresolved = c["UNRESOLVED_FILE_ASSOCIATION"] + c["MIXED_SAMPLE_TYPES_REVIEW"]
        status = ("TUMOR_RNA_BARCODE_LINK_CONFIRMED" if good else
                  "UNRESOLVED_REQUIRES_MANUAL_REVIEW" if unresolved else
                  "NO_PRIMARY_TUMOR_FILE_LINK_FOUND")
        patients.append({
            "patient_id": pid,
            "ct_series_count": candidates_by_patient[pid].get("ct_series_count") or "",
            "tumor_rna_files_by_case_filter": candidates_by_patient[pid].get(
                "tumor_rna_star_counts_files") or "",
            "observed_star_counts_files": sum(c.values()),
            "primary_tumor_linked_files": good,
            "nonprimary_linked_files": c["NONPRIMARY_FILE_BARCODE_LINKED"],
            "unresolved_or_mixed_files": unresolved,
            "rna_lineage_status": status,
            "ct_phase_verified": "NO",
            "tumor_roi_verified": "NO",
            "pretreatment_verified": "NO",
            "qualified_ct_tumor_rna_patient": "NOT_ASSESSED",
        })
    status_counts = Counter(p["rna_lineage_status"] for p in patients)
    summary = {
        "status": "PASS_PUBLIC_FILE_BARCODE_AUDIT",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "ct_rna_case_metadata_candidates": len(candidates_by_patient),
        "file_biospecimen_primary_tumor_patient_candidates":
            status_counts["TUMOR_RNA_BARCODE_LINK_CONFIRMED"],
        "patient_unresolved_without_primary_link":
            status_counts["UNRESOLVED_REQUIRES_MANUAL_REVIEW"],
        "patient_without_primary_tumor_file_link":
            status_counts["NO_PRIMARY_TUMOR_FILE_LINK_FOUND"],
        "examined_file_case_pairs": len(records),
        "qualified_ct_seg_rna_pairs": "NOT_ASSESSED",
        "notes": [
            "TCGA barcode 01 associated with the *file* is stronger evidence than a tumor sample anywhere on the case.",
            "Association barcode alone does not validate tumor purity, RNA QC, tumor mask, or imaging date.",
            "TCIA shifted DICOM dates and GDC relative dates cannot be directly compared by calendar date.",
            "Liver organ segmentation is not HCC tumor/lesion segmentation.",
        ],
    }
    return records, patients, summary


def read_csv(path, columns):
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not set(columns).issubset(reader.fieldnames):
            raise ValueError(f"Missing fields {columns} in {path}")
        rows = list(reader)
    if not rows:
        raise ValueError(f"Empty input: {path}")
    return rows


def write_csv(path, records, fieldnames):
    with Path(path).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)


def offline_test():
    files = [
        {"file_id": "F1", "data_type": "Gene Expression Quantification",
         "analysis": {"workflow_type": "STAR - Counts"},
         "cases": [{"submitter_id": "TCGA-AA-0001"}],
         "associated_entities": [{"entity_type": "aliquot",
                                  "entity_submitter_id": "TCGA-AA-0001-01A-11R-X123-07"}]},
        {"file_id": "F2", "data_type": "Gene Expression Quantification",
         "analysis": {"workflow_type": "STAR - Counts"},
         "cases": [{"submitter_id": "TCGA-BB-0002"}],
         "associated_entities": [{"entity_type": "aliquot",
                                  "entity_submitter_id": "TCGA-BB-0002-11A-11R-X123-07"}]},
        {"file_id": "F3", "data_type": "Gene Expression Quantification",
         "analysis": {"workflow_type": "STAR - Counts"},
         "cases": [{"submitter_id": "TCGA-CC-0003"}],
         "associated_entities": []},
    ]
    inputs = [{"patient_id": f"TCGA-{prefix}-000{n}", "ct_series_count": "2"}
              for n, prefix in ((1, "AA"), (2, "BB"), (3, "CC"))]
    rows, patients, summary = evaluate(files, inputs)
    assert len(rows) == 3 and len(patients) == 3
    assert summary["file_biospecimen_primary_tumor_patient_candidates"] == 1
    assert summary["patient_without_primary_tumor_file_link"] == 1
    assert summary["patient_unresolved_without_primary_link"] == 1
    assert sample_code("TCGA-AA-0001-01A-11R", "TCGA-AA-0001") == "01"
    assert sample_code("TCGA-BB-0002-01A", "TCGA-AA-0001") == ""
    mixed = {"associated_entities": [
        {"entity_submitter_id": "TCGA-AA-0001-01A"},
        {"entity_submitter_id": "TCGA-AA-0001-11A"}]}
    assert classify_file(mixed, "TCGA-AA-0001")[1] == "MIXED_SAMPLE_TYPES_REVIEW"
    print("HCC_GDC_FILE_TO_TUMOR_LINEAGE_OFFLINE_TEST_PASS")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--matches-csv", default="artifacts/hcc_tcia/tcga_rna_overlap_candidates.csv")
    parser.add_argument("--output", default="artifacts/hcc_tcia")
    parser.add_argument("--offline-test", action="store_true")
    args = parser.parse_args()
    if args.offline_test:
        offline_test()
        return
    candidates = read_csv(args.matches_csv, ["patient_id"])
    records, patients, summary = evaluate(fetch_gdc_files(), candidates)
    if not records:
        raise RuntimeError("No GDC RNA files found for all candidate patients")
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "tcga_gdc_rna_file_lineage.csv", records, FIELDS)
    write_csv(out / "tcga_gdc_rna_patient_lineage.csv", patients, list(patients[0]))
    (out / "tcga_gdc_rna_lineage_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
