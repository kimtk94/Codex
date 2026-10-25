"""Discover public Upbit KRW tickers, combining a dated US snapshot.

Discovery only: no orders, no keys, no candles, no historical eligibility claim.
A universe is NOT model-ready until PIT listings, OHLCV coverage and liquidity pass.
"""
import csv
import json
import argparse
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

API="https://api.upbit.com/v1/market/all?is_details=true"

def generate(us_csv,out_dir):
    now=datetime.now(timezone.utc).isoformat()
    with Path(us_csv).open(encoding="utf-8-sig",newline="") as f:
        us=list(csv.DictReader(line for line in f if not line.startswith("#")))
    for row in us:
        if row["market"]!="US_STOCK":raise ValueError("bad source US market")
    out=Path(out_dir);out.mkdir(parents=True,exist_ok=True)
    report={"timestamp_utc":now,"data_sources":["dated SP100 snapshot","Upbit public current market list"],
            "history_coverage":"NOT_VERIFIED","pit_eligibility":"NOT_VERIFIED","us_count":len(us)}
    try:
        request=Request(API,headers={"User-Agent":"Kalman-Universe-Research/1.0","Accept":"application/json"})
        with urlopen(request,timeout=20) as response:
            markets=json.load(response)
        krw=sorted({r["market"] for r in markets if r.get("market","").startswith("KRW-")})
        report["upbit_count"]=len(krw)
        report["upbit_status"]="DISCOVERY_OK"
    except Exception as exc:
        krw=[]
        report["upbit_count"]=0
        report["upbit_status"]="DISCOVERY_ERROR"
        report["error_type"]=type(exc).__name__
    report["total_count"]=len(us)+len(krw)
    report["gate_200"]=report["total_count"]>=200
    report["gate_150us_100crypto"]=len(us)>=150 and len(krw)>=100
    report["research_ready"]=False
    with (out/"discovered_universe.csv").open("w",encoding="utf-8",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=["symbol","market","discovered_utc","source","pit_history_verified"])
        writer.writeheader()
        for row in us:
            writer.writerow({"symbol":row["symbol"],"market":"US_STOCK","discovered_utc":row["source_snapshot_utc"],"source":"SP100_SNAPSHOT","pit_history_verified":"false"})
        for symbol in krw:
            writer.writerow({"symbol":symbol,"market":"UPBIT_KRW","discovered_utc":now,"source":"UPBIT_PUBLIC_CURRENT","pit_history_verified":"false"})
    (out/"discovery_summary.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False))
    if report["upbit_status"]!="DISCOVERY_OK":raise SystemExit(1)
    return report

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--us-csv",default="research/market_tool_lab/sp100_snapshot_20260901.csv")
    parser.add_argument("--out",default="artifacts/market-tool-lab/universe")
    args=parser.parse_args()
    generate(args.us_csv,args.out)
