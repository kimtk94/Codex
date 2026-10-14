#!/usr/bin/env python3
"""Offline, read-only snapshot quality gate. No network, DB or broker writes."""
import argparse
import datetime as dt
import json
from pathlib import Path

UTC = dt.timezone.utc

def timestamp(value):
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else None
    except (TypeError, ValueError):
        return None

def evaluate(row, now):
    generated, data, expiry = (timestamp(row.get(k)) for k in
                               ("generated_at", "data_as_of", "stale_after"))
    flags = []
    if any(v is None for v in (generated, data, expiry)):
        flags.append("MISSING_OR_INVALID_TIMESTAMP")
    if generated and data and data > generated:
        flags.append("DATA_AFTER_GENERATION")
    if generated and generated > now + dt.timedelta(minutes=5):
        flags.append("GENERATION_IN_FUTURE")
    if generated and expiry and expiry <= generated:
        flags.append("EXPIRED_AT_GENERATION")
    if expiry and expiry <= now:
        flags.append("STALE_AT_EVALUATION")
    if row.get("status") == "READY" and "STALE_AT_EVALUATION" in flags:
        flags.append("READY_BUT_STALE")
    freshness = ("UNKNOWN" if any(v is None for v in (generated, data, expiry))
                 else ("STALE" if expiry <= now else "FRESH"))
    passed = row.get("status") == "READY" and freshness == "FRESH" and not flags
    return {"market":row.get("market"), "pipeline_status":row.get("status"),
            "freshness":freshness, "quality_pass":passed, "flags":flags,
            "generated_at":row.get("generated_at"),"data_as_of":row.get("data_as_of"),
            "stale_after":row.get("stale_after")}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=str(Path(__file__).with_name("dashboard_snapshot_20261014.json")))
    parser.add_argument("--at", help="Timezone-aware ISO time; otherwise now UTC")
    parser.add_argument("--output", help="Optional output JSON path")
    args = parser.parse_args()
    now = timestamp(args.at) if args.at else dt.datetime.now(UTC)
    if now is None:
        parser.error("--at must be timezone-aware ISO8601")
    rows = json.loads(Path(args.input).read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        parser.error("input must be an array")
    items = [evaluate(row, now) for row in rows]
    payload = {"mode":"OFFLINE_READ_ONLY","evaluated_at":now.isoformat(),
               "items":items,"summary":{"total":len(items),
               "pass":sum(item["quality_pass"] for item in items),
               "fail":sum(not item["quality_pass"] for item in items)}}
    result = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(result+"\n",encoding="utf-8")
    print(result)

if __name__ == "__main__":
    main()
