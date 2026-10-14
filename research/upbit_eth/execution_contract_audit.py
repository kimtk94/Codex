#!/usr/bin/env python3
"""Static and dataset-backed audit of exploratory KRW-ETH limit-grid v2.
Read-only. No trading endpoints. Standard Python library only."""
import argparse,csv,datetime as dt,json,sqlite3,math,collections
from pathlib import Path
from zoneinfo import ZoneInfo

def tick(price,day):
    # Historical KRW-ETH prices above 2m always used 1000 KRW ticks.
    # Other tiers reflect general KRW rules and the July 31 2025 revision.
    if day>=dt.date(2025,7,31):
        tiers=[(2000000,1000),(1000000,1000),(500000,500),(100000,100),(50000,50),(10000,10),(5000,5),(1000,1)]
    else:
        tiers=[(2000000,1000),(1000000,500),(500000,100),(100000,50),(50000,10),(10000,10),(5000,1),(1000,1)]
    for cutoff,step in tiers:
        if price>=cutoff:return step
    return 1

def load(path):
    with open(path,newline="") as f:
        return list(csv.DictReader(f))

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--db",default="krw_eth_1m.sqlite3")
    p.add_argument("--fee005",default="results_v2_limit/grid_limit_results.csv")
    p.add_argument("--fee010",default="results_fee_010/grid_limit_results.csv")
    p.add_argument("--out",default="results_contract_audit")
    p.add_argument("--min-profit-pct",type=float,default=10)
    p.add_argument("--max-mdd-pct",type=float,default=20)
    a=p.parse_args()
    out=Path(a.out);out.mkdir(exist_ok=True,parents=True)
    x=load(a.fee005);y=load(a.fee010)
    ky=lambda r:(int(r["year"]),round(float(r["spacing_pct"]),7),int(r["levels"]))
    a0={ky(r):r for r in x}; a1={ky(r):r for r in y}
    if a0.keys()!=a1.keys():raise SystemExit("different config sets")
    years={int(r["year"]) for r in x}
    if years!={2024,2025,2026}:raise SystemExit("Missing year")
    cn=sqlite3.connect("file:"+str(Path(a.db).resolve())+"?mode=ro",uri=True)
    cn.execute("PRAGMA query_only=ON")
    sample_dates=[("2024-01-01T00:00:00+09:00",2024),("2025-01-01T00:00:00+09:00",2025),("2026-01-01T00:00:00+09:00",2026)]
    anchor={}
    for t,yr in sample_dates:
        start=dt.datetime.fromisoformat(t).astimezone(dt.timezone.utc).isoformat()
        row=cn.execute("SELECT close,ts_utc FROM candles WHERE ts_utc>=? ORDER BY ts_utc LIMIT 1",(start,)).fetchone()
        if not row:raise SystemExit("Missing data for "+str(yr))
        anchor[yr]=float(row[0])
    results=[]
    for k in sorted(a0):
        old,new=a0[k],a1[k];yr,spacingpct,levels=k
        spacing=spacingpct/100
        close=anchor[yr];day=dt.date(yr,1,1)
        bid=close/(1+spacing);ask=close*(1+spacing)
        bidstep=tick(bid,day);askstep=tick(ask,day)
        aligned=lambda p,step:abs(p/step-round(p/step))<1e-7
        r={
          "year":yr,"spacing_pct":spacingpct,"levels":levels,
          "return_fee_005_pct":float(old["return_pct"]),
          "return_fee_010_pct":float(new["return_pct"]),
          "fee_sensitivity_pp":round(float(old["return_pct"])-float(new["return_pct"]),5),
          "mdd_fee_010_pct":float(new["mdd_pct"]),
          "fills_fee_010":int(new["fills"]),
          "ambiguous_bars_fee_010":int(new["skipped_ambiguous_bars"]),
          "gap_events":int(new["gap_events"]),
          "first_bid_tick_aligned":aligned(bid,bidstep),
          "first_ask_tick_aligned":aligned(ask,askstep),
          "min_order_notional_krw":round(1000000/levels,2),
          "pass_profit_target":float(new["return_pct"])>=a.min_profit_pct,
          "pass_mdd_target":float(new["mdd_pct"])>=-a.max_mdd_pct
        }
        results.append(r)
    with (out/"execution_contract_audit.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(results[0]));w.writeheader();w.writerows(results)
    per_year={}
    for y in sorted(years):
        sub=[r for r in results if r["year"]==y]
        per_year[y]={
         "tested":len(sub),"passed_both_targets":sum(r["pass_profit_target"] and r["pass_mdd_target"] for r in sub),
         "best_net_return_fee010_pct":max(r["return_fee_010_pct"] for r in sub),
         "first_grid_levels_unaligned":sum(not r["first_bid_tick_aligned"] or not r["first_ask_tick_aligned"] for r in sub),
         "largest_fee_degradation_pp":max(r["fee_sensitivity_pp"] for r in sub),
         "gap_events_observed":max(r["gap_events"] for r in sub)
        }
    limitations=[
     "The legacy research v2 computes fills based on candle H/L touch, not executable volume, queue position, or exchange prints.",
     "The original v2 does not reserve KRW/ETH for outstanding orders. Real simultaneous outstanding order sets can violate exchange available-balance requirements.",
     "The original v2 may overwrite pending orders when equal rounded prices collide, and creates replacement orders during an OHLC bar without an observed execution sequence.",
     "Gap detection counts missing candle minutes. Historical missing candles can indicate zero trade or exchange outage; no stop/restart execution rule has been tested.",
     "Historical tick policy is instrument/date specific. This audit estimates the first grid order's alignment, not a complete per-order fill validation.",
     "Results are exploratory; profit target and MDD checks are screening only, not deploy-readiness."
    ]
    report={"per_year":per_year,"anchor_krw":anchor,"limitations":limitations,
        "recommended_next":"Build an event-state machine with reserved balances and historical valid tick snapping, then rerun forward-chaining tests before any strategy optimization."}
    (out/"summary.json").write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(report,ensure_ascii=False,indent=2))
    print("SAVED",out/"execution_contract_audit.csv",out/"summary.json")
if __name__=="__main__": main()
