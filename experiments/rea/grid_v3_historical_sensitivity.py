#!/usr/bin/env python3
"""Offline historical sensitivity analysis. No live trades or database writes."""
import argparse
import csv
import importlib.util
import json
import sqlite3
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
SOURCE = BASE / "research/upbit_eth/grid_event_v3.py"
def load_sim(mode):
    code=SOURCE.read_text()
    if mode=="inclusive":
        code=code.replace("low<key[1]", "low<=key[1]").replace("high>key[1]", "high>=key[1]")
    elif mode!="strict":
        raise ValueError(mode)
    ns={"__name__": "grid_v3_sensitivity_module", "__file__": str(SOURCE)}
    exec(compile(code,str(SOURCE),"exec"), ns)
    return ns["sim"]

def evaluate(db, years, spacings, levels, fees, capital):
    uri=f"file:{Path(db).resolve()}?mode=ro"
    con=sqlite3.connect(uri,uri=True)
    con.execute("PRAGMA query_only=ON")
    count,lo,hi=con.execute("SELECT COUNT(*), MIN(ts_utc), MAX(ts_utc) FROM candles").fetchone()
    if not count: raise ValueError("EMPTY_CANDLES")
    strict=load_sim("strict")
    inclusive=load_sim("inclusive")
    rows=[]
    for year in years:
        for space in spacings:
            for level in levels:
                for fee in fees:
                    for name,fn in (("strict",strict),("inclusive_touch",inclusive)):
                        r=fn(con,year,space,level,capital,fee)
                        if r is None: continue
                        rows.append(dict(fill_model=name,fee_rate=fee,**r))
    con.close()
    return {"data":{"bars":count,"first":lo,"last":hi},"results":rows,
            "caveats":["Only equality touch criteria differ, not actual order-book execution.",
                      "OHLC order timing, queue, slippage and Upbit historical tick correctness remain unverified.",
                      "Each calendar year uses independent capital; this is not continuous CAGR."]}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--db",required=True)
    p.add_argument("--out",required=True)
    p.add_argument("--years",default="2024,2025,2026")
    p.add_argument("--spacings",default="0.006,0.01,0.015")
    p.add_argument("--levels",default="20,50,100")
    p.add_argument("--fees",default="0,0.001,0.002")
    p.add_argument("--capital",type=float,default=1_000_000)
    a=p.parse_args()
    years=[int(v) for v in a.years.split(",")]
    spacings=[float(v) for v in a.spacings.split(",")]
    levels=[int(v) for v in a.levels.split(",")]
    fees=[float(v) for v in a.fees.split(",")]
    if not years or not spacings or not levels or not fees or a.capital<=0 or any(v<0 or v>=1 for v in spacings+fees) or any(v<2 for v in levels): raise ValueError("INVALID_PARAMETERS")
    report=evaluate(a.db,years,spacings,levels,fees,a.capital)
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    (out/"sensitivity_metadata.json").write_text(json.dumps({"data":report["data"],"caveats":report["caveats"],"settings":{"years":years,"spacings":spacings,"levels":levels,"fees":fees,"capital":a.capital}},ensure_ascii=False,indent=2))
    rows=report["results"]
    if rows:
        with (out/"sensitivity_results.csv").open("w",newline="") as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    print(json.dumps({"rows":len(rows),"data":report["data"],"out":str(out)},ensure_ascii=False))
if __name__=="__main__":main()
