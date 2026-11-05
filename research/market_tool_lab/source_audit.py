"""Classify Kalman CSV exports before they enter an ML training pipeline.

Offline, dependency-free, read-only input; output is aggregate metadata only.
"""
import argparse
import csv
import json
import math
from collections import Counter
from datetime import date, datetime
from pathlib import Path


def audit_alignment(file_path):
    with Path(file_path).open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        expected = {"date_ny"} | {f"{field}_{sym}" for sym in ("qld", "qqq") for field in ("open", "high", "low", "close", "volume")}
        if not expected.issubset(reader.fieldnames or []):
            raise ValueError("alignment schema mismatch")
        seen, dates = set(), []
        violations = Counter()
        for row in reader:
            try:
                day = date.fromisoformat(row["date_ny"])
                if day in seen:
                    violations["duplicate_date"] += 1
                seen.add(day)
                dates.append(day)
                for sym in ("qld", "qqq"):
                    o, h, l, c, v = (float(row[f"{field}_{sym}"]) for field in ("open", "high", "low", "close", "volume"))
                    if not all(math.isfinite(x) for x in (o,h,l,c,v)) or not (l > 0 and l <= min(o,c) and max(o,c) <= h and v >= 0):
                        violations[f"invalid_ohlcv_{sym}"] += 1
            except (KeyError, ValueError, TypeError):
                violations["invalid_row"] += 1
        if dates != sorted(dates):
            violations["out_of_order"] += 1
    return {"kind":"daily_alignment", "rows":len(dates), "min_date":str(min(dates)) if dates else None,
            "max_date":str(max(dates)) if dates else None, "violations":dict(violations),
            "training_ready": bool(dates) and not violations,
            "caveat":"Adjustments, corporate actions, data availability times and provider parity not independently verified."}


def audit_snapshot(file_path):
    with Path(file_path).open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        required = {"market","timeframe","candle_time_utc","open","high","low","close","volume"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError("snapshot schema mismatch")
        groups, duplicate_keys, violations = Counter(), set(), Counter()
        keys = set()
        dates=[]
        for row in reader:
            try:
                dt=datetime.fromisoformat(row["candle_time_utc"].replace("Z","+00:00"))
                if dt.tzinfo is None:
                    raise ValueError("naive datetime")
                sym,tf=row["market"].upper(),row["timeframe"]
                key=(sym,tf,dt)
                if key in keys:
                    duplicate_keys.add(key)
                keys.add(key)
                groups[(sym,tf)]+=1
                dates.append(dt)
                o,h,l,c,v=(float(row[k]) for k in ("open","high","low","close","volume"))
                if not all(math.isfinite(x) for x in (o,h,l,c,v)) or not (l > 0 and l <= min(o,c) and max(o,c) <= h and v >= 0):
                    violations["invalid_ohlcv"]+=1
            except (KeyError, ValueError, TypeError):
                violations["invalid_row"]+=1
    if duplicate_keys:
        violations["duplicate_symbol_timeframe_timestamp"]=len(duplicate_keys)
    return {"kind":"mixed_timeframe_latest_snapshot", "rows":sum(groups.values()),
            "groups":{f"{sym}:{tf}":count for (sym,tf),count in sorted(groups.items())},
            "min_timestamp":min(dates).isoformat() if dates else None,
            "max_timestamp":max(dates).isoformat() if dates else None,
            "violations":dict(violations),"training_ready":False,
            "caveat":"One latest bar per symbol/timeframe is not historical minute-level series. Keep timeframe dimension; do not concatenate as sequential OHLCV."}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--alignment", required=True)
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--output")
    args=parser.parse_args()
    result={"schema_version":1,"mode":"offline_read_only",
            "alignment":audit_alignment(args.alignment),"snapshot":audit_snapshot(args.snapshot)}
    text=json.dumps(result,indent=2,ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(text+"\n",encoding="utf-8")
    print(text)
    if result["alignment"]["violations"] or result["snapshot"]["violations"]:
        raise SystemExit(1)


if __name__=="__main__":
    main()
