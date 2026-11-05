#!/usr/bin/env python3
"""Metadata-only TCIA HCC cohort audit. No images or private data downloaded."""
import argparse
import csv
import json
import os
import time
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

BASE = "https://services.cancerimagingarchive.net/nbia-api/services/v1"
COLLECTIONS = ("HCC-TACE-Seg", "TCGA-LIHC")

def get_series(collection, retries=3):
    query = urllib.parse.urlencode({"Collection": collection, "Modality": "CT"})
    url = f"{BASE}/getSeries?{query}"
    last_error = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "HCC-public-CI/0.1", "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=45) as response:
                result = json.load(response)
            if not isinstance(result, list):
                raise ValueError(f"Expected list, got {type(result).__name__}")
            return result
        except Exception as exc:
            last_error = str(exc)
            if i + 1 < retries:
                time.sleep(2 ** i)
    raise RuntimeError(f"{collection} API request failed: {last_error}")

def records(rows, collection):
    fields = ("Collection", "PatientID", "StudyInstanceUID", "SeriesInstanceUID", "Modality",
              "SeriesDescription", "StudyDescription", "ProtocolName", "ImageCount", "FileSize")
    output = []
    for row in rows:
        item = {key: str(row.get(key, "") or "") for key in fields}
        item["Collection"] = collection
        output.append(item)
    return output

def write_csv(path, rows):
    fields = ("Collection", "PatientID", "StudyInstanceUID", "SeriesInstanceUID", "Modality",
              "SeriesDescription", "StudyDescription", "ProtocolName", "ImageCount", "FileSize")
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="artifacts/hcc_tcia")
    parser.add_argument("--offline-test", action="store_true")
    args = parser.parse_args()
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    if args.offline_test:
        fixture = [{"PatientID": "A", "SeriesInstanceUID": "S1", "Modality": "CT"}]
        assert records(fixture, "test")[0]["PatientID"] == "A"
        write_csv(out / "fixture.csv", records(fixture, "test"))
        print("OFFLINE_TEST_PASS")
        return
    summary = {"status": "PASS", "cohorts": {}, "validation_status": "NOT_STARTED",
               "notes": ["Metadata is not proof of segmentation/ground-truth availability.",
                         "No patient images or hospital records are transferred."]}
    failed = False
    for collection in COLLECTIONS:
        try:
            rows = records(get_series(collection), collection)
            write_csv(out / f"{collection}_ct_series.csv", rows)
            ids = {r["PatientID"] for r in rows if r["PatientID"]}
            summary["cohorts"][collection] = {"ct_patients": len(ids), "ct_series": len(rows),
                                               "image_count_total": sum(int(r["ImageCount"]) for r in rows if r["ImageCount"].isdigit())}
            if not rows:
                failed = True
        except Exception as exc:
            failed = True
            summary["cohorts"][collection] = {"error": str(exc)}
    summary["status"] = "FAIL" if failed else "PASS"
    (out / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    if failed:
        raise SystemExit(1)

if __name__ == "__main__":
    main()
