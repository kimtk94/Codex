"""2026 R5.1 profit-flip threshold sensitivity on immutable Alpaca SIP 5-minute bars.

Research-only, same frozen entry sequence for every policy, no future data for
decision logic. Exit execution approximated as 5m close observed by watchdog.
Use one bar AFTER end of entry signal to avoid entering on unseen bar prices.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timedelta, time, timezone
import gzip
import json
import math
import os
from pathlib import Path
import statistics
from zoneinfo import ZoneInfo

import pandas as pd
try:
    from .flip_exit_backfill_2026 import effective_hour_end, parse_ts
except ImportError:
    from flip_exit_backfill_2026 import effective_hour_end, parse_ts

NY = ZoneInfo("America/New_York")
ROOT = Path(os.environ.get("KALMAN_FLIP_RESEARCH_ROOT", "/home/taehoon/kalman-data/trading/research_flip_2026"))
ARM = 0.002
STOP = -0.03
TAKE = 0.20
FRIDAY_FLAT_HOUR = 15
FRIDAY_FLAT_MINUTE = 45
THRESHOLDS = [("FLIP_-0.2%", -.002),("FLIP_-0.5%",-.005),("FLIP_-1.0%",-.01),
              ("FLIP_-1.5%",-.015),("FLIP_-2.0%",-.02),("FLIP_OFF",None)]


def regular(bar):
    """Returns true only for US regular session bars, respecting NY DST."""
    local = bar["t"].astimezone(NY)
    return local.weekday() < 5 and time(9,30) <= local.time().replace(tzinfo=None) < time(16,0)


def prepare_bars(raw):
    out = []
    seen = set()
    for b in raw:
        try:
            ts = parse_ts(b["t"])
            if ts in seen:
                continue
            row = {"t":ts,"end":ts+timedelta(minutes=5),
                   "o":float(b["o"]),"h":float(b["h"]),
                   "l":float(b["l"]),"c":float(b["c"]),
                   "v":float(b.get("v",0))}
            if min(row[k] for k in ("o","h","l","c"))<=0 or not regular(row):
                continue
            seen.add(ts)
            out.append(row)
        except (KeyError, ValueError, TypeError):
            continue
    return sorted(out,key=lambda b:b["t"])


def friday_due(end_time):
    local = end_time.astimezone(NY)
    return local.weekday()==4 and (local.hour,local.minute)>=(FRIDAY_FLAT_HOUR,FRIDAY_FLAT_MINUTE)


def first_eligible_entry(bars, start):
    # A 5m bar OPENING at model's known 60m close is the earliest causal fill.
    return next((b for b in bars if b["t"]>=start),None)


def run_path(monitor, entry_price, cap_at, threshold, cost_bps, friday_flat=True):
    armed=False
    below=0
    peak=0.0
    for b in monitor:
        end=b["end"]
        raw=b["c"]/entry_price-1.0
        peak=max(peak,raw)
        armed=armed or peak>=ARM
        if armed and threshold is not None and raw<=threshold:
            below+=1
        else:
            below=0
        reason=None
        if raw<=STOP:
            reason="STOP_LOSS"
        elif raw>=TAKE:
            reason="TAKE_PROFIT"
        elif threshold is not None and armed and below>=2:
            reason="PROFIT_FLIP"
        elif friday_flat and friday_due(end):
            reason="FRIDAY_FLAT"
        elif end>=cap_at:
            reason="MAX_HOLD_4"
        if reason:
            return {"status":"PASS","exit_px":b["c"],"exit_at":end.isoformat(),
                    "gross":raw,"net":raw-cost_bps/10000,
                    "reason":reason,"peak":peak,
                    "intrabar_stop_breach":any(z["l"]/entry_price-1<=STOP
                                                for z in monitor if z["t"]<=b["t"])}
    return {"status":"CENSORED_NO_EXIT"}


def run_one(trade, raw_bars, cost_bps=10, friday_flat=True, entry_mode='sip'): 
    bars=prepare_bars(raw_bars)
    entry_end=effective_hour_end(trade["entry_time"])
    cap_end=effective_hour_end(trade["exit_time"])
    entry_bar=first_eligible_entry(bars,entry_end)
    if not entry_bar or entry_bar["end"]>=cap_end:
        return {"status":"CENSORED_NO_ENTRY","symbol":trade["symbol"],
                "bar_count":len(bars)}
    entry_price = (float(trade['entry_price']) if entry_mode == 'legacy' else entry_bar['c'])
    if not any(b["end"]>=cap_end for b in bars):
        return {"status":"CENSORED_NO_CAP","symbol":trade["symbol"],
                "bar_count":len(bars)}
    monitor=[b for b in bars if b["t"]>entry_bar["t"]]
    scenarios={}
    for name,threshold in THRESHOLDS:
        scenarios[name]=run_path(monitor,entry_price,cap_end,threshold,cost_bps,friday_flat)
    data={
      "status":"PASS","symbol":trade["symbol"],"date":str(trade["entry_time"])[:10],
      "trade_id":trade["trade_id"],"model_entry_time":trade["entry_time"],
      "model_exit_time":trade["exit_time"],"entry_at":entry_bar["end"].isoformat(),
      "entry_price_simulated":entry_price,"entry_price_sip":entry_bar['c'],
      "entry_price_legacy":float(trade["entry_price"]),
      "entry_price_gap_bps":(entry_bar['c']/float(trade["entry_price"])-1)*10000,
      "exit_price_legacy":float(trade["exit_price"]),
      "original_weighted_net":float(trade["return_pct"]),
      "position_weight":float(trade.get("position_weight") or 1),
      "bar_count":len(bars),"scenarios":scenarios,
      "baseline_reference_raw":float(trade["exit_price"])/float(trade["entry_price"])-1,
    }
    return data


def stats(results, threshold):
    good=[x for x in results if x["status"]=="PASS" and x["scenarios"][threshold]["status"]=="PASS"]
    if not good:
        return None
    rets=[x["scenarios"][threshold]["net"] for x in good]
    retsW=[x["scenarios"][threshold]["net"]*x["position_weight"] for x in good]
    profits=sum(v for v in retsW if v>0)
    losses=-sum(v for v in retsW if v<0)
    equity=1.0
    peak=1.0
    mdd=0.0
    for r in retsW:
        equity*=1+r
        peak=max(peak,equity)
        mdd=min(mdd,equity/peak-1)
    return {"n":len(good),"win_n":sum(x>0 for x in rets),"win_rate":sum(x>0 for x in rets)/len(rets),
            "mean_net":statistics.mean(rets),"median_net":statistics.median(rets),
            "mean_weighted_net":statistics.mean(retsW),"sum_weighted_net":sum(retsW),
            "cum_trade_sequence_proxy":equity-1,
            "mdd_trade_sequence_proxy":mdd,
            "profit_factor_weighted":(profits/losses if losses>0 else None),
            "exits":dict(Counter(x["scenarios"][threshold]["reason"] for x in good)),
            "intrabar_stop_breach":sum(x["scenarios"][threshold]["intrabar_stop_breach"] for x in good)}


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--feed",default="sip",choices=["sip","iex"])
    ap.add_argument("--cost-bps",type=float,default=10)
    ap.add_argument("--no-friday-flat",action="store_true")
    ap.add_argument("--max-trades",type=int,default=0)
    ap.add_argument("--entry-mode",choices=['sip','legacy'],default='sip')
    args=ap.parse_args()
    trades=json.loads((ROOT/"neon_251_snapshot.json").read_text())["rows"]
    if args.max_trades:
        trades=trades[:args.max_trades]
    results=[]
    for t in trades:
        path=ROOT/"cache_5min"/args.feed/(t["trade_id"]+".json.gz")
        if not path.is_file():
            results.append({"status":"NO_CACHE","symbol":t["symbol"],"trade_id":t["trade_id"]})
            continue
        try:
            with gzip.open(path,"rt") as handle:
                entry=json.load(handle)
            if entry["status"]!="PASS":
                results.append({"status":"BAD_SOURCE_"+entry["status"],
                                "symbol":t["symbol"],"trade_id":t["trade_id"]})
                continue
            results.append(run_one(t,entry.get("bars") or [],args.cost_bps,
                                   not args.no_friday_flat,args.entry_mode))
        except Exception as exc:
            results.append({"status":"ERROR_"+type(exc).__name__,
                            "symbol":t["symbol"],"trade_id":t["trade_id"]})
    output=ROOT/("replay_"+args.feed+"_cost"+str(args.cost_bps).replace(".","_")+("_no_friday" if args.no_friday_flat else "")+("_legacy_entry" if args.entry_mode=='legacy' else "") )
    good=[x for x in results if x["status"]=="PASS"]
    if good:
        pd.DataFrame([{k:v for k,v in r.items() if k!="scenarios"} | 
          {f"{n}_net":s.get("net") for n,s in r["scenarios"].items()} |
          {f"{n}_reason":s.get("reason") for n,s in r["scenarios"].items()} for r in good
          ]).to_csv(str(output)+"_detail.csv",index=False)
    by_month=defaultdict(list)
    for r in good:
        by_month[r["date"][:7]].append(r)
    monthly={month:{name:stats(rows,name) for name,_ in THRESHOLDS}
             for month,rows in sorted(by_month.items())}
    summary={name:stats(results,name) for name,_ in THRESHOLDS}
    tracking={
       "matched_trades":len(good),"total_ledger":len(trades),
       "status":dict(Counter(x["status"] for x in results)),
       "ref_gross_mean":statistics.mean(x["baseline_reference_raw"] for x in good) if good else None,
       "sip_legacy_entry_gap_bps_median":statistics.median(x["entry_price_gap_bps"] for x in good) if good else None,
       "sip_legacy_entry_abs_gap_bps_median":statistics.median(abs(x["entry_price_gap_bps"]) for x in good) if good else None,
       "model_is_in_sample":True,
       "price_data_feed":args.feed,"cost_bps":args.cost_bps,"entry_mode":args.entry_mode,
       "clock_contract":"Model 60m timestamp is bar START; 5m entry fill after end, 5m watcher-close proxy",
       "friday_flat":"15:45 NY; max hold capped by historic 4 signal-bar end",
       "model_rotation":"NOT_REPLAYABLE_FROM_LEDGER",
    }
    artifact={"tracking":tracking,"summary":summary,"monthly":monthly,"detail":results}
    (Path(str(output)+"_report.json")).write_text(json.dumps(artifact,ensure_ascii=False,
                                                             indent=2,default=str)+"\n")
    (Path(str(output)+"_summary.json")).write_text(json.dumps({
            "tracking":tracking,"summary":summary,"monthly":monthly},
            ensure_ascii=False,indent=2,default=str)+"\n")
    print(json.dumps({"tracking":tracking,"summary":summary},ensure_ascii=False,
                     default=str),flush=True)


if __name__=="__main__":
    main()
