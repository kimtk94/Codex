"""Read-only baseline: validate OHLCV files and compare timestamp alignment.

No network, broker credentials, orders or production imports. CSV headers:
timestamp,open,high,low,close,volume (symbol optional).
"""
import argparse
import csv
import json
import math
from datetime import datetime, timezone
from pathlib import Path


def parse_time(value):
    raw = value.strip().replace("Z", "+00:00")
    try:
        ts = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError("invalid timestamp") from exc
    if ts.tzinfo is None:
        raise ValueError("timestamps must include timezone")
    return ts.astimezone(timezone.utc)


def validate(path):
    prev = None
    rows = 0
    invalid = 0
    missing = 0
    first = last = None
    with Path(path).open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        required = {"timestamp", "open", "high", "low", "close", "volume"}
        if not required.issubset(set(reader.fieldnames or [])):
            raise ValueError("missing OHLCV required columns")
        for row in reader:
            rows += 1
            try:
                t = parse_time(row["timestamp"])
                values = [float(row[k]) for k in ("open", "high", "low", "close", "volume")]
                o,h,l,c,v = values
                valid = all(math.isfinite(z) for z in values) and l > 0 and l <= min(o,c) <= max(o,c) <= h and v >= 0
                if not valid:
                    invalid += 1
                if prev is not None and t <= prev:
                    invalid += 1
                prev = t
                first = first or t
                last = t
            except (ValueError, TypeError, KeyError):
                invalid += 1
    return {"file":Path(path).name,"rows":rows,"invalid_rows":invalid,"first_utc":first.isoformat() if first else None,"last_utc":last.isoformat() if last else None,"status":"PASS" if rows and invalid == 0 else "FAIL"}


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--output")
    args=ap.parse_args()
    report={"schema_version":1,"mode":"offline_read_only","sources":[validate(p) for p in args.files]}
    report["status"]="PASS" if all(x["status"]=="PASS" for x in report["sources"]) else "FAIL"
    output=json.dumps(report,indent=2,ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(output+"\n",encoding="utf-8")
    print(output)
    if report["status"]!="PASS":
        raise SystemExit(1)


if __name__=="__main__":
    main()
