"""Read-only 16 live profit-flip exits vs historical SIP 5-minute alternatives.

Uses actual broker-mirrored entry average as the entry cost anchor. For add-ons
this final cost basis is ex-post, so treat multi-entry trades as diagnostic ONLY.
This is not a portfolio trading replay and does not allow redeployed exit cash.
"""
from __future__ import annotations
import argparse
from datetime import datetime,timedelta,timezone,time
from pathlib import Path
from zoneinfo import ZoneInfo
import json
import os
import statistics
import pandas as pd
import requests
from flip_exit_backfill_2026 import load_creds,request_bars,parse_ts,effective_hour_end
from flip_exit_replay_2026 import THRESHOLDS,prepare_bars,run_path

NY=ZoneInfo("America/New_York")
ROOT=Path(os.environ.get("KALMAN_FLIP_RESEARCH_ROOT", "/home/taehoon/kalman-data/trading/research_flip_2026"))


def resolve_cap(position, signals):
    asof=parse_ts(position["entry_signal_as_of"])
    candidates=[parse_ts(t) for t in signals if parse_ts(t)>asof]
    if len(candidates)<4:
        return None
    mark=candidates[3]
    # Overnight synthetic as_of (e.g. 00:00 UTC) may be after US regular close.
    ny=mark.astimezone(NY)
    if not (time(9,30)<=ny.time().replace(tzinfo=None)<time(16,0)):
        return mark
    return effective_hour_end(mark.isoformat())


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--cost-mode",choices=("broker_fees","25bps"),default="broker_fees")
    args=p.parse_args()
    source=json.loads((ROOT/"live_flip_16_snapshot.json").read_text())
    orders=json.loads((ROOT/"neon_live_buy_orders_snapshot.json").read_text())["rows"]
    signals=source["canonical_signal_times"]
    headers=load_creds()
    session=requests.Session()
    rows=[]
    cache=ROOT/"cache_live_sip_5min"
    cache.mkdir(exist_ok=True)
    for position in source["rows"]:
        start=parse_ts(position["first_seen_at"])
        real_exit=parse_ts(position["exit_time"])
        cap=resolve_cap(position,signals)
        # If no fourth signal, the 2026-10-09 NY Friday cut-off is observable.
        ny=start.astimezone(NY)
        friday_cut=datetime.combine(ny.date(),time(15,45),NY).astimezone(timezone.utc)
        # Include the next regular session when the 4th signal falls after NY close.
        latest_observed=datetime.now(timezone.utc)-timedelta(minutes=20)
        data_end=min(latest_observed,(max(real_exit,cap) if cap else max(real_exit,friday_cut))+timedelta(days=4))
        path=cache/(position["position_id"]+"_extended.json")
        if path.exists():
            data=json.loads(path.read_text())
        else:
            data=request_bars(session,position["symbol"],start-timedelta(minutes=15),
                              data_end,"sip",headers)
            path.write_text(json.dumps(data,separators=(",",":"))+"\n")
        b=prepare_bars(data.get("bars") or [])
        reference=float(position["entry_price"])
        exit_px=float(position["exit_price"])
        qty=float(position["quantity"])
        cost_actual=float(position["exit_tax"])+float(position["exit_commission"])
        cost_bps=10000*cost_actual/(qty*reference)
        if args.cost_mode=="25bps":
            cost_bps=25.
        actual=(exit_px/reference-1)-cost_bps/10000
        matched=[order for order in orders if order["symbol"]==position["symbol"]
                 and start<=parse_ts(order["created_at"])<=real_exit
                 and order["broker_status"]=="FILLED"]
        add_on_count=sum(1 for order in matched if order["entry_type"]=="ADD_ON")
        adopted=position["entry_status"]=="ADOPTED"
        entry_bar=next((bar for bar in b if bar["t"]>=start),None)
        after=[bar for bar in b if entry_bar and bar["t"]>entry_bar["t"]]
        options={}
        for name,thr in THRESHOLDS:
            if entry_bar:
                target=cap if cap is not None else friday_cut
                outcome=run_path(after,reference,target,thr,cost_bps,True)
            else:
                outcome={"status":"NO_5MIN_AFTER_ENTRY"}
            options[name]=outcome
        rows.append({
            "symbol":position["symbol"],"date":position["first_seen_at"][:10],
            "position_id":position["position_id"],"adopted":adopted,"add_on_count":add_on_count,
            "quality":"SINGLE_ENTRY" if not adopted and add_on_count==0 else
                      "ADOPTED_EX_POST" if adopted else "ADD_ON_EX_POST",
            "status":data.get("status"),"bars":len(b),
            "entry_avg_usd":reference,"real_exit_avg_usd":exit_px,
            "cost_bps":cost_bps,"real_net_pct":actual*100,
            "counterfactual_ny_friday_cap":str(cap or friday_cut),
            "five_min_baseline_net_pct":options["FLIP_-0.2%"].get("net",None),
            "options":options
        })
    summary={}
    for cohort,filtered in [("all",rows),("single_entry_only",[r for r in rows if r["quality"]=="SINGLE_ENTRY"])]:
        grid={}
        for name,thr in THRESHOLDS:
            matched=[r for r in filtered if r["options"][name].get("status")=="PASS"]
            d=[r["options"][name]["net"]*100 for r in matched]
            grid[name]={"n":len(d),"mean_net_pct":statistics.mean(d) if d else None,
                        "win_n":sum(x>0 for x in d),
                        "baseline_real_same_sample_pct":statistics.mean(r["real_net_pct"] for r in matched) if matched else None,
                        "positive_vs_real":sum(r["options"][name]["net"]*100>r["real_net_pct"] for r in matched),
                        "exits":{why:sum(r["options"][name]["reason"]==why for r in matched)
                                 for why in sorted({r["options"][name]["reason"] for r in matched})}}
        summary[cohort]=grid
    output=ROOT/("live_16_5min_counterfactual_"+args.cost_mode+".json")
    output.write_text(json.dumps({"summary":summary,"detail":rows},indent=2,default=str)+"\n")
    tab=[{k:v for k,v in row.items() if k!="options"}|{
        name:(row["options"][name].get("net")*100 if row["options"][name].get("net") is not None else None)
         for name,_ in THRESHOLDS} for row in rows]
    pd.DataFrame(tab).to_csv(ROOT/("live_16_counterfactual_"+args.cost_mode+".csv"),index=False)
    print(json.dumps({"rows":len(rows),"quality_counts":{str(k):int(v) for k,v in pd.Series([r["quality"] for r in rows]).value_counts().items()},
                      "summary":summary},ensure_ascii=False))


if __name__=="__main__":
    main()
