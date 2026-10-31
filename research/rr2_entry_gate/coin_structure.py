#!/usr/bin/env python3
"""COIN structural RR>=2.0 research on SIP 15m, NOT model-matched and NEVER live."""
from __future__ import annotations
import argparse, hashlib, json, math
from datetime import datetime, timedelta, timezone
from pathlib import Path
import exchange_calendars as xcals
import pandas as pd

ARMS=("ORL_BUFFER_2R","PRIOR_LOW_BUFFER_2R","FIXED_2PCT_2R","ORL_PRIOR20_HIGH")
HORIZONS=(1,2,4)
FEE=.003
UTC=timezone.utc

def required_target(stop,fee=FEE):
    return 2*stop+3*fee+1e-10

def geometry(entry,opening_low,previous_low,previous_20_high,arm,fee=FEE):
    if not math.isfinite(entry) or not math.isfinite(opening_low) or min(entry,opening_low)<=0:
        raise ValueError("INVALID_ENTRY")
    if arm=="FIXED_2PCT_2R": stop=.02
    elif arm in ("ORL_BUFFER_2R","ORL_PRIOR20_HIGH"):
        stop=(entry-(opening_low-entry*.001))/entry
    elif arm=="PRIOR_LOW_BUFFER_2R":
        if previous_low is None or not math.isfinite(previous_low) or previous_low<=0:
            return {"pass":False,"reason":"MISSING_PRIOR_LOW"}
        stop=(entry-(previous_low-entry*.001))/entry
    else: raise ValueError("UNKNOWN_ARM")
    if stop<.005: return {"pass":False,"reason":"STOP_TOO_TIGHT"}
    if stop>.03: return {"pass":False,"reason":"STOP_TOO_WIDE"}
    required=required_target(stop,fee)
    if arm=="ORL_PRIOR20_HIGH":
        if previous_20_high is None or not math.isfinite(previous_20_high):
            return {"pass":False,"reason":"NO_PRIOR20_RESISTANCE"}
        target=previous_20_high/entry-1
        if target<required: return {"pass":False,"reason":"RESISTANCE_TOO_CLOSE"}
    else: target=required
    if target>.08: return {"pass":False,"reason":"TARGET_TOO_FAR"}
    rr=(target-fee)/(stop+fee)
    assert rr>=2-1e-9
    return {"pass":True,"reason":"PASS","stop_pct":stop,"target_pct":target,
            "planned_net_rr":rr}

def build_sessions(raw_bars,*,start,end):
    cal=xcals.get_calendar("XNYS")
    calendar=cal.sessions_in_range(pd.Timestamp(start),pd.Timestamp(end))
    indexed={}
    for raw in raw_bars:
        stamp=raw.get("t") or raw.get("timestamp")
        if not isinstance(stamp,str): raise ValueError("BAD_TIMESTAMP")
        stamp=datetime.fromisoformat(stamp.replace("Z","+00:00"))
        if stamp.tzinfo is None: raise ValueError("NAIVE_TIMESTAMP")
        stamp=stamp.astimezone(UTC)
        v=[float(raw.get(x,raw.get(y))) for x,y in
           (("o","open"),("h","high"),("l","low"),("c","close"))]
        if not all(math.isfinite(x) and x>0 for x in v) or v[1]<max(v) or v[2]>min(v):
            raise ValueError("INVALID_OHLC")
        if stamp in indexed: raise ValueError("DUPLICATE_TIMESTAMPS")
        indexed[stamp]={"t":stamp,"o":v[0],"h":v[1],"l":v[2],"c":v[3]}
    sessions=[]
    incomplete=[]
    for d in calendar:
        opened=cal.session_open(d).to_pydatetime().astimezone(UTC)
        closed=cal.session_close(d).to_pydatetime().astimezone(UTC)
        expected=[opened+timedelta(minutes=15*i) for i in
                  range(int((closed-opened).total_seconds()//900))]
        bars=[indexed.get(t) for t in expected]
        if any(x is None for x in bars) or len(bars)<2:
            incomplete.append({"date":d.date().isoformat(),
                               "missing_bars":sum(x is None for x in bars)})
            continue
        sessions.append({"date":d.date().isoformat(),"bars":bars,
                         "low":min(x["l"] for x in bars),
                         "high":max(x["h"] for x in bars),
                         "close":bars[-1]["c"],"early_close":len(bars)!=26})
    quality={"expected_sessions":len(calendar),"complete_sessions":len(sessions),
             "incomplete_sessions":len(incomplete),"first_incomplete":incomplete[:5],
             "received_bars":len(raw_bars)}
    return sessions,quality

def simulate(sessions,index,horizon,stop_pct,target_pct,*,fee=FEE):
    if index+horizon>len(sessions): raise ValueError("INCOMPLETE_HORIZON")
    entry=sessions[index]["bars"][1]["o"]  # 09:45 bar open, first bar completed
    stop=entry*(1-stop_pct)
    target=entry*(1+target_pct)
    end_index=index+horizon-1
    reason="TIME_CLOSE"
    exit_price=sessions[end_index]["close"]
    for j in range(index,index+horizon):
        bars=sessions[j]["bars"][1:] if j==index else sessions[j]["bars"]
        for bar in bars:
            if bar["o"]<=stop: exit_price,reason,end_index=bar["o"],"STOP_GAP",j
            elif bar["o"]>=target: exit_price,reason,end_index=bar["o"],"TARGET_GAP",j
            elif bar["l"]<=stop: exit_price,reason,end_index=stop,"STOP",j
            elif bar["h"]>=target: exit_price,reason,end_index=target,"TARGET",j
            else: continue
            break
        if reason!="TIME_CLOSE": break
    net=exit_price/entry-1-fee
    return {"entry_index":index,"exit_index":end_index,"entry_price":entry,
            "exit_price":exit_price,"reason":reason,"net_fraction":net,
            "realized_R":net/(stop_pct+fee),"planned_stop_fraction":stop_pct,
            "planned_target_fraction":target_pct}

def metrics(trades,sessions):
    empty={"trades":0,"mean_R":None,"mean_net_pct":None,"total_return_pct":0,
           "eod_mdd_pct":0,"stop_gap_count":0,"stop_count":0,"target_count":0,
           "time_count":0,"cost_stress_50bp_mean_R":None,
           "cost_stress_100bp_mean_R":None,
           "cost_stress_50bp_planned_rr2_count":0,
           "cost_stress_100bp_planned_rr2_count":0}
    if not trades: return empty
    equity=peak=1.
    worst=0.
    t=0
    for day in range(trades[0]["entry_index"],trades[-1]["exit_index"]+1):
        if t<len(trades) and trades[t]["entry_index"]<=day<=trades[t]["exit_index"]:
            tr=trades[t]
            if day==tr["exit_index"]:
                equity*=1+tr["net_fraction"]
                t+=1
            else:
                marked=equity*(sessions[day]["close"]/tr["entry_price"]-FEE)
                peak=max(peak,marked)
                worst=min(worst,marked/peak-1)
                continue
        peak=max(peak,equity)
        worst=min(worst,equity/peak-1)
    def stress(fee):
        returns=[(x["exit_price"]/x["entry_price"]-1-fee)/
                 (x["planned_stop_fraction"]+fee) for x in trades]
        viable=sum((x["planned_target_fraction"]-fee)/
                   (x["planned_stop_fraction"]+fee)>=2 for x in trades)
        return round(sum(returns)/len(returns),6),viable
    s50,v50=stress(.005);s100,v100=stress(.01)
    reasons=[x["reason"] for x in trades]
    return {"trades":len(trades),
            "mean_R":round(sum(x["realized_R"] for x in trades)/len(trades),6),
            "mean_net_pct":round(100*sum(x["net_fraction"] for x in trades)/len(trades),6),
            "total_return_pct":round(100*(equity-1),6),
            "eod_mdd_pct":round(100*worst,6),
            "stop_gap_count":reasons.count("STOP_GAP"),
            "stop_count":reasons.count("STOP")+reasons.count("STOP_GAP"),
            "target_count":reasons.count("TARGET")+reasons.count("TARGET_GAP"),
            "time_count":reasons.count("TIME_CLOSE"),
            "cost_stress_50bp_mean_R":s50,"cost_stress_100bp_mean_R":s100,
            "cost_stress_50bp_planned_rr2_count":v50,
            "cost_stress_100bp_planned_rr2_count":v100}

def research(sessions,quality):
    if quality["incomplete_sessions"] or not sessions:
        return {"status":"DATA_HOLD_INCOMPLETE_SIP","live":"HOLD",
                "quality":quality,"results":[]}
    results=[]
    atr_by_year={}
    for year in (2024,2025,2026):
        indices=[i for i,s in enumerate(sessions)
                 if int(s["date"][:4])==year and i>=20]
        ratios=[]
        for i in indices:
            true_ranges=[]
            for j in range(i-14,i):
                x=sessions[j];prev=sessions[j-1]["close"]
                true_ranges.append(max(x["high"]-x["low"],abs(x["high"]-prev),
                                       abs(x["low"]-prev)))
            ratios.append(sum(true_ranges)/14/sessions[i]["bars"][1]["o"])
        ratios.sort()
        atr_by_year[str(year)]={"count":len(ratios),
               "median_prior14_daily_atr_over_entry":round(ratios[len(ratios)//2],6)
                if ratios else None}
        for arm in ARMS:
            prepared=[];rejected={}
            for i in indices:
                current=sessions[i]
                entry=current["bars"][1]["o"]
                prior_low=sessions[i-1]["low"]
                prior_high=max(x["high"] for x in sessions[i-20:i])
                g=geometry(entry,current["bars"][0]["l"],prior_low,prior_high,arm)
                if not g["pass"]: rejected[g["reason"]]=rejected.get(g["reason"],0)+1
                else: prepared.append((i,g))
            for horizon in HORIZONS:
                selected=[];last_exit=-1;blocked=tail=0
                for i,g in prepared:
                    if i+horizon>len(sessions): tail+=1;continue
                    if i<=last_exit: blocked+=1;continue
                    x=simulate(sessions,i,horizon,g["stop_pct"],g["target_pct"])
                    selected.append(x);last_exit=x["exit_index"]
                results.append({"year":year,"arm":arm,"hold_sessions":horizon,
                                "all_sessions_after_warmup":len(indices),
                                "geometry_pass":len(prepared),
                                "geometry_rejected_by_primary":rejected,
                                "tail_censored":tail,"overlap_rejected":blocked,
                                **metrics(selected,sessions)})
    return {"schema":"coin-structure-rr2-all-sessions-pilot-v1",
            "status":"RESEARCH_ONLY_NOT_MODEL_SIGNAL_MATCHED","live":"HOLD",
            "instrument":"COIN","feed":"ALPACA_SIP_15MIN_ADJUSTMENT_ALL",
            "entry":"09:45_NEW_YORK_SECOND_RTH_BAR_OPEN",
            "signal_cohort":"ALL_COMPLETE_EXCHANGE_SESSIONS_NOT_V_UNWEIGHTED_SIGNALS",
            "min_net_rr":2.0,"roundtrip_cost_fraction":FEE,
            "max_stop_fraction":.03,"max_target_fraction":.08,
            "same_bar_ordering":"STOP_FIRST",
            "position":"ONE_AT_A_TIME_PER_ARM_HORIZON",
            "historical_data_status":"2025_2026_ALREADY_INSPECTED_NOT_NEW_OOS",
            "limitations":[
                "All sessions are unconditional opportunities, NOT model signals.",
                "OHLC STOP-first, no spread/impact/quotes or fill uncertainty model.",
                "50bp/100bp costs stress a 30bp planned target; RR2 may no longer hold.",
                "2024/2025/2026 are researched historical years; no pristine OOS."
            ],
            "quality":quality,"atr_reference_by_year":atr_by_year,"results":results}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--bars",required=True,type=Path)
    p.add_argument("--out",type=Path,default=Path("outputs/coin_structural_rr2/summary.json"))
    p.add_argument("--start",default="2024-01-01")
    p.add_argument("--end",default="2026-10-30")
    a=p.parse_args()
    private=a.bars.read_bytes()
    raw=json.loads(private)
    if not isinstance(raw,list): raise ValueError("EXPECTED_ALPACA_BAR_ARRAY")
    sessions,q=build_sessions(raw,start=a.start,end=a.end)
    d=research(sessions,q)
    d["private_source_sha256"]=hashlib.sha256(private).hexdigest()
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(d,indent=2)+"\n")
    print(json.dumps({"status":d["status"],"quality":q,
                      "aggregate_rows":len(d["results"]),"live":"HOLD"}))
    if d["status"]!="RESEARCH_ONLY_NOT_MODEL_SIGNAL_MATCHED":
        raise SystemExit("DATA_HOLD: NO PERFORMANCE CLAIMS")

if __name__=="__main__": main()
