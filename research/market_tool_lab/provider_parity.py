"""Compare point-in-time daily OHLCV providers with Kalman's QQQ/QLD baseline.

Offline comparator. Does not download data, modify the baseline, or trade.
Provider CSV: date,symbol,open,high,low,close,volume
"""
import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path

FIELDS=("open","high","low","close","volume")

def load_base(path):
    data={}
    with Path(path).open(newline="",encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            for symbol in ("QQQ","QLD"):
                data[(row["date_ny"],symbol)]={k:float(row[f"{k}_{symbol.lower()}"]) for k in FIELDS}
    return data

def load_provider(path):
    data={}
    repeats=0
    with Path(path).open(newline="",encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            key=(row["date"],row["symbol"].upper())
            if key in data:
                repeats+=1
            data[key]={k:float(row[k]) for k in FIELDS}
    return data,repeats

def compare(baseline,provider,close_tolerance=0.01):
    base=load_base(baseline)
    other,duplicates=load_provider(provider)
    common=set(base)&set(other)
    by_symbol=defaultdict(list)
    price_mismatches=0
    for key in sorted(common):
        b,o=base[key],other[key]
        if b["close"] <= 0 or o["close"] <= 0:
            raise ValueError("nonpositive close")
        gap=abs(o["close"]/b["close"]-1)
        by_symbol[key[1]].append(gap)
        price_mismatches+=gap>close_tolerance
    result={
        "baseline_records":len(base),
        "provider_records":len(other),
        "overlap_records":len(common),
        "baseline_only":len(set(base)-set(other)),
        "provider_only":len(set(other)-set(base)),
        "duplicate_provider_keys":duplicates,
        "close_gap_gt_tolerance":price_mismatches,
        "close_tolerance_fraction":close_tolerance,
        "by_symbol":{s:{"overlap":len(gaps),"mean_abs_close_gap_pct":round(100*sum(gaps)/len(gaps),5),
                        "max_abs_close_gap_pct":round(100*max(gaps),5)}
                      for s,gaps in sorted(by_symbol.items())},
        "status":"REVIEW" if duplicates or price_mismatches or not common else "COMPARABLE",
        "warning":"Price adjustment, venue, session cutoff, currency and publication timing must be verified before accepting COMPARABLE data."
    }
    return result

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--baseline",required=True)
    p.add_argument("--provider",required=True)
    p.add_argument("--output")
    a=p.parse_args()
    report=compare(a.baseline,a.provider)
    text=json.dumps(report,ensure_ascii=False,indent=2)
    if a.output: Path(a.output).write_text(text+"\n",encoding="utf-8")
    print(text)
