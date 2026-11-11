"""Deterministic market universe quality gate. No market/network access."""
import argparse
import csv
import json
from collections import Counter
from pathlib import Path

ALLOWED={"US_STOCK","US_ETF","UPBIT_KRW"}
REQUIRED={"symbol","market","first_seen_utc","last_seen_utc","source"}

def check(path,min_total=200,min_us=120,min_crypto=80):
    with Path(path).open(newline="",encoding="utf-8-sig") as f:
        reader=csv.DictReader(f)
        if not REQUIRED.issubset(reader.fieldnames or []):
            raise ValueError("required columns: "+",".join(sorted(REQUIRED)))
        data=list(reader)
    duplicate=0
    seen=set()
    bad=[]
    counts=Counter()
    for row in data:
        key=(row["market"],row["symbol"].strip().upper())
        if key in seen: duplicate+=1
        seen.add(key)
        if (row["market"] not in ALLOWED or not row["symbol"].strip()
            or not row["source"].strip() or not row["first_seen_utc"].strip()
            or not row["last_seen_utc"].strip()):
            bad.append(row["symbol"])
        counts[row["market"]]+=1
    us=counts["US_STOCK"]+counts["US_ETF"]
    crypto=counts["UPBIT_KRW"]
    result={"source":Path(path).name,"unique":len(seen),"us":us,"crypto":crypto,
      "duplicates":duplicate,"invalid_rows":len(bad),
      "targets":{"min_total":min_total,"min_us":min_us,"min_crypto":min_crypto},
      "status":"PASS" if len(seen)>=min_total and us>=min_us and crypto>=min_crypto and not duplicate and not bad else "FAIL",
      "caution":"Universe count does not prove market data availability or point-in-time historical membership."}
    return result

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("csv");p.add_argument("--min-total",type=int,default=200)
    p.add_argument("--min-us",type=int,default=120)
    p.add_argument("--min-crypto",type=int,default=80)
    p.add_argument("--output")
    args=p.parse_args()
    result=check(args.csv,args.min_total,args.min_us,args.min_crypto)
    s=json.dumps(result,ensure_ascii=False,indent=2)
    if args.output:Path(args.output).write_text(s+"\n",encoding="utf-8")
    print(s)
    if result["status"]!="PASS":raise SystemExit(1)
