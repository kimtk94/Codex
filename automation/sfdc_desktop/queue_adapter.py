#!/usr/bin/env python3
"""Turn human-approved CSS/Sheet action rows into a Salesforce Task staging CSV.

Offline only. No Salesforce API or Sheets writes. Explicit approval is mandatory.
This is a *staging* file, never evidence that an SFDC record was created.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path

ALLOWED_DECISIONS = {"APPROVED_FOR_SFDC", "READY_FOR_SFDC"}
OUTPUT_FIELDS = ["source_id", "object_type", "record_key", "Subject", "Description"]
REQUIRED_SOURCE = {"source_id", "decision", "account_key", "subject"}

def strip(s):
    return (s or "").strip()

def assemble(rows):
    staged, skipped, seen = [], {}, set()
    for row in rows:
        decision = strip(row.get("decision")).upper()
        if decision not in ALLOWED_DECISIONS:
            skipped["not_approved"] = skipped.get("not_approved", 0) + 1
            continue
        src, account, subject = [strip(row.get(k)) for k in ("source_id", "account_key", "subject")]
        if not all((src, account, subject)):
            skipped["missing_required"] = skipped.get("missing_required", 0) + 1
            continue
        # A source event should only generate one Task regardless of reruns.
        key = "css-task-" + hashlib.sha256(src.encode("utf-8")).hexdigest()[:24]
        if key in seen:
            skipped["duplicate_source"] = skipped.get("duplicate_source", 0) + 1
            continue
        seen.add(key)
        staged.append({"source_id": src, "object_type": "Task", "record_key": key,
                       "Subject": subject, "Description": strip(row.get("description"))})
    return staged, skipped

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True, help="Reviewed CSV with explicit SFDC decisions")
    p.add_argument("--output", required=True, help="LOCAL staging queue CSV; never commit")
    args = p.parse_args()
    inpath, outpath = Path(args.input).resolve(), Path(args.output).resolve()
    if inpath == outpath:
        p.error("input and output must differ")
    with inpath.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or not REQUIRED_SOURCE.issubset(reader.fieldnames):
            p.error("source header must include " + ",".join(sorted(REQUIRED_SOURCE)))
        staged, skipped = assemble(reader)
    outpath.parent.mkdir(parents=True, exist_ok=True)
    with outpath.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        writer.writerows(staged)
    print(json.dumps({"status": "STAGED_NOT_SUBMITTED", "staged": len(staged),
                      "skipped": skipped}, ensure_ascii=False))

if __name__ == "__main__":
    main()
