#!/usr/bin/env python3
"""Public TCGA-LIHC CT × GDC tumor RNA-seq metadata audit; NOT image qualification."""
import argparse
import csv
import json
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

GDC_URL = "https://api.gdc.cancer.gov/files"
CT_COLUMNS = ("PatientID", "SeriesInstanceUID")
GDC_FIELDS = "file_id,file_name,analysis.workflow_type,cases.submitter_id,cases.samples.sample_type"


def normalize_id(value):
    """Normalize TCGA patient barcode to its first three components."""
    parts = str(value or "").strip().upper().replace("_", "-").split("-")
    if len(parts) < 3 or parts[0] != "TCGA" or not all(parts[1:3]):
        return ""
    return "-".join(parts[:3])


def load_ct(path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not set(CT_COLUMNS).issubset(reader.fieldnames):
            raise ValueError(f"CT manifest must have columns {CT_COLUMNS}")
        rows = list(reader)
    return {normalize_id(r["PatientID"]) for r in rows if normalize_id(r["PatientID"])}, rows


def gdc_filter():
    conditions = [
        ("cases.project.project_id", "TCGA-LIHC"),
        ("data_type", "Gene Expression Quantification"),
        ("analysis.workflow_type", "STAR - Counts"),
        ("cases.samples.sample_type", "Primary Tumor"),
    ]
    return {"op": "and", "content": [
        {"op": "in", "content": {"field": k, "value": [v]}} for k, v in conditions
    ]}


def fetch_json(url, attempts=3):
    last_error = None
    for attempt in range(attempts):
        try:
            req = urllib.request.Request(url, headers={
                "Accept": "application/json", "User-Agent": "HCC-public-radiogenomics-audit/1.0"
            })
            with urllib.request.urlopen(req, timeout=45) as response:
                return json.load(response)
        except Exception as exc:
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"GDC request failed: {last_error}")


def fetch_gdc_files(page_size=500):
    offset, files = 0, []
    while True:
        params = urllib.parse.urlencode({
            "filters": json.dumps(gdc_filter(), separators=(",", ":")),
            "fields": GDC_FIELDS, "format": "JSON", "from": offset, "size": page_size,
        })
        payload = fetch_json(GDC_URL + "?" + params)
        data = payload.get("data") or {}
        hits = data.get("hits")
        total = (data.get("pagination") or {}).get("total")
        if not isinstance(hits, list) or total is None:
            raise ValueError("GDC response lacks hits or pagination.total")
        files.extend(hits)
        offset += len(hits)
        if offset >= int(total):
            break
        if not hits:
            raise RuntimeError("GDC pagination stalled with remaining records")
    return files


def rna_candidates(files):
    """Exclude normals and unrelated workflows; review aliquot linkage later."""
    candidates = defaultdict(set)
    for item in files:
        if item.get("data_type") != "Gene Expression Quantification":
            continue
        if (item.get("analysis") or {}).get("workflow_type") != "STAR - Counts":
            continue
        file_id = item.get("file_id") or item.get("id")
        if not file_id:
            continue
        for case in item.get("cases") or []:
            case_id = normalize_id(case.get("submitter_id"))
            if case_id and any(s.get("sample_type") == "Primary Tumor"
                               for s in case.get("samples") or []):
                candidates[case_id].add(file_id)
    return candidates


def summarize(ct_ids, ct_rows, files):
    rna = rna_candidates(files)
    matched = sorted(ct_ids.intersection(rna))
    matched_rows = [{
        "patient_id": pid,
        "ct_series_count": sum(normalize_id(r.get("PatientID")) == pid for r in ct_rows),
        "tumor_rna_star_counts_files": len(rna[pid]),
        "status": "METADATA_ONLY_UNQUALIFIED",
    } for pid in matched]
    return {
        "summary": {
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "status": "PASS_METADATA_ONLY",
            "ct_patients": len(ct_ids),
            "gdc_tumor_star_counts_patients": len(rna),
            "ct_rna_patient_overlap": len(matched),
            "eligible_ct_seg_rna_pairs": "NOT_ASSESSED",
            "notes": [
                "Matching barcodes do not establish pretreatment CT phase or tumor ROI.",
                "Image versus tissue collection date remains unverified.",
                "Verify file-to-aliquot tumor linkage before expression analysis.",
                "Metadata overlap is NOT the final radiogenomics sample size."
            ],
        },
        "matched": matched_rows,
    }


def offline_test():
    ct_rows = [
        {"PatientID": "TCGA-AA-0001", "SeriesInstanceUID": "CT1"},
        {"PatientID": "TCGA-AA-0001", "SeriesInstanceUID": "CT2"},
        {"PatientID": "TCGA-BB-0002", "SeriesInstanceUID": "CT3"},
    ]
    files = [
        {"file_id": "F1", "data_type": "Gene Expression Quantification",
         "analysis": {"workflow_type": "STAR - Counts"},
         "cases": [{"submitter_id": "TCGA-AA-0001",
                    "samples": [{"sample_type": "Primary Tumor"}]}]},
        {"file_id": "F2", "data_type": "Gene Expression Quantification",
         "analysis": {"workflow_type": "STAR - Counts"},
         "cases": [{"submitter_id": "TCGA-BB-0002",
                    "samples": [{"sample_type": "Solid Tissue Normal"}]}]},
        {"file_id": "F3", "data_type": "Gene Expression Quantification",
         "analysis": {"workflow_type": "HTSeq - Counts"},
         "cases": [{"submitter_id": "TCGA-BB-0002",
                    "samples": [{"sample_type": "Primary Tumor"}]}]},
    ]
    result = summarize({"TCGA-AA-0001", "TCGA-BB-0002"}, ct_rows, files)
    assert result["summary"]["ct_rna_patient_overlap"] == 1
    assert result["matched"][0]["ct_series_count"] == 2
    assert normalize_id("TCGA-AA-0001-01A") == "TCGA-AA-0001"
    assert normalize_id("not-tcga") == ""
    assert gdc_filter()["op"] == "and"
    print("TCGA_RNA_OVERLAP_OFFLINE_TEST_PASS")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ct-csv", default="artifacts/hcc_tcia/TCGA-LIHC_ct_series.csv")
    parser.add_argument("--output", default="artifacts/hcc_tcia")
    parser.add_argument("--offline-test", action="store_true")
    args = parser.parse_args()
    if args.offline_test:
        offline_test()
        return
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    ct_ids, ct_rows = load_ct(Path(args.ct_csv))
    result = summarize(ct_ids, ct_rows, fetch_gdc_files())
    (output / "tcga_rna_overlap_summary.json").write_text(
        json.dumps(result["summary"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    with (output / "tcga_rna_overlap_candidates.csv").open(
            "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=(
            "patient_id", "ct_series_count", "tumor_rna_star_counts_files", "status"))
        writer.writeheader()
        writer.writerows(result["matched"])
    print(json.dumps(result["summary"], ensure_ascii=False))


if __name__ == "__main__":
    main()
