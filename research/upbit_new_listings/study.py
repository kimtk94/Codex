#!/usr/bin/env python3
"""Read-only Upbit KRW new-market first-week event study. No trading credentials."""
import argparse, csv, json, math, time
from datetime import datetime, timedelta, timezone
from pathlib import Path
import requests
UTC=timezone.utc
BASE="https://api.upbit.com/v1"
S=requests.Session()
last_call=0.0
def get(path,**params):
    global last_call
    for attempt in range(6):
        delay=max(0,0.24-(time.monotonic()-last_call))
        if delay: time.sleep(delay)
        last_call=time.monotonic()
        try:
            r=S.get(BASE+path,params=params,timeout=25)
            if r.status_code in (429,500,502,503,504):
                time.sleep(min(20,2**attempt));continue
            r.raise_for_status()
            return r.json()
        except (requests.Timeout,requests.ConnectionError):
            time.sleep(min(20,2**attempt))
    raise RuntimeError(f"API retry exhausted: {path} {params}")
def iso(d):return d.strftime("%Y-%m-%dT%H:%M:%SZ")
def dt(s):return datetime.fromisoformat(s.replace("Z","+00:00")).replace(tzinfo=UTC) if "+" not in s else datetime.fromisoformat(s)
def latest_candle_by(m,day):
    # Last candle at/before a UTC calendar day, not necessarily on that day.
    data=get("/candles/days",market=m,to=iso(day+timedelta(days=1)),count=1)
    return dt(data[0]["candle_date_time_utc"]) if data else None
def first_day(m,cutoff,today):
    # Cumulative predicate stays monotone even on days without trades.
    if latest_candle_by(m,cutoff-timedelta(days=1)) is not None:return None
    if latest_candle_by(m,today) is None:return None
    lo=cutoff;hi=today
    while lo<hi:
        mid=lo+timedelta(days=(hi-lo).days//2)
        if latest_candle_by(m,mid) is not None:hi=mid
        else:lo=mid+timedelta(days=1)
    return lo
def candles_first_week(m,first):
    # Fetch in reverse for 9 days, then retain the first 168h of actual 15m trading.
    start=first
    end=start+timedelta(days=9)
    cursor=end
    rows={}
    for _ in range(8):
        batch=get("/candles/minutes/15",market=m,to=iso(cursor),count=200)
        if not batch:break
        for x in batch:
            t=dt(x["candle_date_time_utc"])
            if start<=t<end:rows[t]=x
        earliest=min(dt(x["candle_date_time_utc"]) for x in batch)
        if earliest<=start:break
        cursor=earliest
    ordered=sorted(rows.items())
    if not ordered:return None,[]
    actual=ordered[0][0]
    return actual,[(t,x) for t,x in ordered if actual<=t<actual+timedelta(days=7)]
def evaluate(rows,entry_bar,tp,sl,fee,slip):
    if len(rows)<=entry_bar+1:return None
    # Entry is OPEN of next bar after a fully observed lag; no future knowledge.
    entry=float(rows[entry_bar][1]["opening_price"])*(1+slip)
    for i in range(entry_bar,len(rows)):
        x=rows[i][1];low=float(x["low_price"]);high=float(x["high_price"])
        if low<=entry*(1-sl):
            exit_price=entry*(1-sl)*(1-slip);reason="stop";break
        if high>=entry*(1+tp):
            exit_price=entry*(1+tp)*(1-slip);reason="take";break
    else:
        exit_price=float(rows[-1][1]["trade_price"])*(1-slip);reason="time"
    return (exit_price*(1-fee)/(entry*(1+fee))-1)*100,reason
def write_csv(path,rows,columns):
    with open(path,"w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=columns);w.writeheader();w.writerows(rows)
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--out",default="outputs/upbit-new-listings")
    p.add_argument("--cutoff",default="2023-10-24")
    p.add_argument("--asof",default="2026-10-24")
    p.add_argument("--limit",type=int,default=0)
    a=p.parse_args();out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    cutoff=datetime.fromisoformat(a.cutoff).replace(tzinfo=UTC)
    asof=datetime.fromisoformat(a.asof).replace(tzinfo=UTC)
    markets=[x for x in get("/market/all",is_details="true") if x["market"].startswith("KRW-")]
    if a.limit:markets=markets[:a.limit]
    print("CURRENT_KRW_MARKETS",len(markets),flush=True)
    cohorts=[];candles=[];errors=[]
    for idx,item in enumerate(markets,1):
        m=item["market"]
        try:
            first=first_day(m,cutoff,asof)
            if first is None:continue
            actual,rows=candles_first_week(m,first)
            if not actual or actual+timedelta(days=7)>asof:
                cohorts.append({"market":m,"first_trade_utc":iso(actual) if actual else "",
                                "bars":len(rows),"status":"incomplete","name":item.get("korean_name","")})
                continue
            expected=672
            cohorts.append({"market":m,"first_trade_utc":iso(actual),"bars":len(rows),
                            "status":"complete" if len(rows)>=600 else "sparse",
                            "name":item.get("korean_name","")})
            for t,x in rows:
                candles.append({"market":m,"t_utc":iso(t),"open":x["opening_price"],
                                "high":x["high_price"],"low":x["low_price"],"close":x["trade_price"],
                                "volume":x["candle_acc_trade_volume"],"value_krw":x["candle_acc_trade_price"]})
            if idx%20==0:print("CHECKED",idx,"of",len(markets),"COHORT",len(cohorts),flush=True)
        except Exception as e:
            errors.append({"market":m,"error":str(e)});print("ERROR",m,str(e),flush=True)
    write_csv(out/"universe.csv",cohorts,["market","first_trade_utc","bars","status","name"])
    write_csv(out/"candles_15m.csv",candles,["market","t_utc","open","high","low","close","volume","value_krw"])
    usable={c["market"]:c for c in cohorts if c["status"]=="complete"}
    by_market={}
    for c in candles:by_market.setdefault(c["market"],[]).append((dt(c["t_utc"]),{
        "opening_price":c["open"],"high_price":c["high"],"low_price":c["low"],"trade_price":c["close"]}))
    trades=[]
    for m,cohort in usable.items():
        rows=by_market[m];year=dt(cohort["first_trade_utc"]).year
        for lag in (1,4,16,96):
            for tp in (.03,.05,.10,.20):
                for sl in (.03,.05,.10):
                    result=evaluate(rows,lag,tp,sl,.0005,.0015)
                    if result:
                        ret,reason=result
                        trades.append({"market":m,"year":year,"first_trade_utc":cohort["first_trade_utc"],
                            "lag_bars":lag,"tp":tp,"sl":sl,"net_return_pct":round(ret,6),"exit_reason":reason,
                            "split":"test" if year==2026 else "train"})
    columns=["market","year","first_trade_utc","lag_bars","tp","sl","net_return_pct","exit_reason","split"]
    write_csv(out/"strategy_trades.csv",trades,columns)
    stats=[]
    for lag in (1,4,16,96):
        for tp in (.03,.05,.10,.20):
            for sl in (.03,.05,.10):
                for split in ("train","test"):
                    r=[t["net_return_pct"] for t in trades if t["lag_bars"]==lag and t["tp"]==tp and t["sl"]==sl and t["split"]==split]
                    if r:stats.append({"lag_bars":lag,"tp":tp,"sl":sl,"split":split,"n":len(r),
                        "mean_net_pct":round(sum(r)/len(r),5),"win_pct":round(100*sum(x>0 for x in r)/len(r),3)})
    write_csv(out/"strategy_summary.csv",stats,["lag_bars","tp","sl","split","n","mean_net_pct","win_pct"])
    fixed=[x for x in stats if x["lag_bars"]==4 and x["tp"]==.10 and x["sl"]==.03]
    (out/"fixed_60m_tp10_sl3.json").write_text(json.dumps({
        "policy":"60m after listing, +10% TP, -3% SL, 7d maximum",
        "train":next((x for x in fixed if x["split"]=="train"),None),
        "test":next((x for x in fixed if x["split"]=="test"),None)
    },indent=2))
    eligible=[x for x in stats if x["split"]=="train" and x["n"]>=10]
    best=max(eligible,key=lambda x:x["mean_net_pct"]) if eligible else None
    test=next((x for x in stats if best and x["split"]=="test" and
             (x["lag_bars"],x["tp"],x["sl"])==(best["lag_bars"],best["tp"],best["sl"])),None)
    report={"asof":a.asof,"cutoff":a.cutoff,"current_krw_markets":len(markets),
        "new_still_listed":len(cohorts),"full_week_cohorts":len(usable),
        "15min_rows":len(candles),"failed_markets":errors,
        "best_in_sample":best,"out_of_sample_same_policy":test,
        "limitations":["Delisted KRW markets are absent: survivor bias until notices/history are added.",
         "Earliest daily candle is a proxy; exact listing announcement time is unverified.",
         "Historical 15-minute candles do not reveal order-book slippage or queue position.",
         "Mean trade return is not a portfolio backtest; concurrent entries and capital/MDD not evaluated.",
         "Only full 7-day cohorts with at least 600 printed candles used in strategy grid.",
         "Worst-case stop-first fill on a candle touching take and stop."]}
    (out/"report.json").write_text(json.dumps(report,indent=2,ensure_ascii=False))
    print(json.dumps(report,ensure_ascii=False),flush=True)
if __name__=="__main__":main()
