"""Audit available Kalman bars without credentials, market requests, or trades.

Reports only observed coverage. Does not infer missing exchange sessions from
calendar weekdays; a proper exchange calendar is required for gap verdicts.
"""
import argparse
import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


def inspect_daily(path):
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        reader=csv.DictReader(handle)
        if not {"date_ny","close_qqq","close_qld"}.issubset(reader.fieldnames or ()):
            raise ValueError("daily alignment schema mismatch")
        dates=[datetime.strptime(row["date_ny"],"%Y-%m-%d").date() for row in reader]
    duplicates=len(dates)-len(set(dates))
    return {"rows":len(dates),"first":str(min(dates)) if dates else None,
            "last":str(max(dates)) if dates else None,"duplicate_dates":duplicates,
            "historical_interval":"1d", "continuous_intraday":False}


def inspect_latest(path):
    groups=defaultdict(list)
    with Path(path).open(newline="",encoding="utf-8-sig") as handle:
        reader=csv.DictReader(handle)
        if not {"market","timeframe","candle_time_utc","open","high","low","close","volume"}.issubset(reader.fieldnames or ()):
            raise ValueError("latest bars schema mismatch")
        for r in reader:
            timestamp=datetime.fromisoformat(r["candle_time_utc"].replace("Z","+00:00"))
            if timestamp.tzinfo is None:
                raise ValueError("timestamp must be timezone aware")
            groups[(r["market"],r["timeframe"])].append(timestamp.astimezone(timezone.utc))
    result={}
    for (symbol,timeframe),values in sorted(groups.items()):
        result[symbol+"/"+timeframe]={"bars":len(values),"unique_timestamps":len(set(values)),
                                     "first":min(values).isoformat(),"last":max(values).isoformat()}
    return {"total_bars":sum(map(len,groups.values())),"groups":result,
            "continuous_intraday":False,"note":"latest-bar mixed timeframe snapshots do not establish historical coverage"}


def audit(daily, latest):
    return {"schema_version":1,"mode":"offline_read_only","daily":inspect_daily(daily),
            "latest":inspect_latest(latest),
            "alpaca_entitlement":"NOT_VERIFIED",
            "training_intraday_ready":False}


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--daily",required=True)
    p.add_argument("--latest",required=True)
    p.add_argument("--output")
    a=p.parse_args()
    report=audit(a.daily,a.latest)
    payload=json.dumps(report,ensure_ascii=False,indent=2)
    if a.output:
        Path(a.output).write_text(payload+"\n",encoding="utf-8")
    print(payload)
