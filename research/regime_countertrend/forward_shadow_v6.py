"""CFM-V6 prospective market snapshot: strict 24-symbol price anchors.

Lock old rules; never retrain V5 on new observations. A daily source update
produces separate statuses for unavailable data, source revisions, no signals,
signals awaiting a full four-session outcome, and underpowered fresh outcomes.
2026-11-11/12 = newly observed exploratory rows; 2026-11-13 onward =
forward-registered observation period. None of this proves broker execution.
"""
import argparse
import hashlib
import json
import urllib.parse
import urllib.request
from datetime import datetime,timedelta,timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from .sector_price_sources_v3 import (
    manifest_load,fetch_symbol,apply_ticker_trade_eligibility
)
from .sector_hierarchy_v3 import make_pair
from .robust_walkforward import simulate
from .krw_fx_v5 import parse_fx_chart,attach_fx

FROZEN="2026-11-10"
FORMAL="2026-11-13"
MIN_COMPLETED_SIGNALS=30
MIN_DISTINCT_FRESH_MONTHS=6

def most_recent_completed_ny_session(now_utc=None):
    now=(now_utc or datetime.now(timezone.utc)).astimezone(
        ZoneInfo("America/New_York"))
    day=now.date() if (now.hour>=17) else now.date()-timedelta(days=1)
    while day.weekday()>4:day-=timedelta(days=1)
    return day

def frozen_anchor_audit(frame,anchor,expected_last):
    if frame.date.duplicated().any():raise ValueError("duplicate provider market dates")
    rows=frame[frame.date==FROZEN]
    if len(rows)!=1:raise ValueError("missing frozen price anchor")
    bps=10000*(float(rows.close.iloc[0])/float(anchor)-1)
    if not np.isfinite(bps):raise ValueError("invalid source anchor")
    if frame.date.max()>str(expected_last):
        raise ValueError("data includes not-yet-completed market date")
    if str(frame.date.max())<str(expected_last-timedelta(days=5)):
        raise ValueError("market data stale more than 5 calendar days")
    return {"anchor_delta_bps":float(bps),"anchor_match_within_5bp":bool(abs(bps)<=5),
        "new_sessions_after_frozen":int((frame.date>FROZEN).sum()),
        "latest_session":str(frame.date.max()),
        "frozen_compatibility":"PASS" if abs(bps)<=5 else "HOLD_RETRO_ADJUSTMENT"}

def new_proxy_signals(prices,benchmark,symbol,industry):
    """Identical locked UP_DIP / DOWN_RALLY / SIDE_DIP thresholds and 5d cooldown."""
    pair=make_pair(prices,benchmark,symbol)
    qqq60=pair.close_qqq.pct_change(60,fill_method=None)
    stock5=pair.close_qld.pct_change(5,fill_method=None)
    last={}
    observations=[]
    complete=[]
    for i in range(65,len(pair)):
        q=float(qqq60.iloc[i]);s=float(stock5.iloc[i])
        if not np.isfinite(q) or not np.isfinite(s):continue
        regime="UP" if q>=.08 else ("DOWN" if q<=-.08 else "SIDE")
        if regime=="UP" and s<=-.03:event="UP_DIP"
        elif regime=="DOWN" and s>=.03:event="DOWN_RALLY"
        elif regime=="SIDE" and s<=-.03:event="SIDE_DIP"
        else:continue
        if i-last.get(event,-1000)<5:continue
        last[event]=i
        date=str(pair.date_ny.iloc[i])
        if date<=FROZEN:continue
        horizon=(i+4<len(pair))
        is_formal=date>=FORMAL
        info={"date":date,"symbol":symbol,"industry":industry,
            "event":event,"regime":regime,"qqq_ret60":q,"stock_ret5":s,
            "signal_freeze_rule":"UNMODIFIED_V3_5DAY_COOLDOWN",
            "formal_prospective":is_formal,
            "horizon_complete":horizon,
            "price_data_only":True,"v5_model_prediction":"NOT_FROZEN_FOR_PROSPECTIVE"}
        observations.append(info)
        if horizon:
            result=simulate(pair,i,"STOP_FIRST",roundtrip_bps=20,hold_days=4)
            complete.append({**info,"entry_date":str(pair.date_ny.iloc[i+1]),
                 "exit_date":str(result["exit_date"]),
                 "usd_net_20bp":float(result["net"]),
                 "synthetic_outcome":str(result["outcome"])})
    return observations,complete

def fetch_fresh_fx(expected_last):
    start=int(pd.Timestamp("2026-09-01",tz="UTC").timestamp())
    end=int(pd.Timestamp(expected_last+timedelta(days=1),tz="UTC").timestamp())
    args=urllib.parse.urlencode({"period1":start,"period2":end,
        "interval":"1d","events":"history"})
    errors=[]
    for host in ("query1.finance.yahoo.com","query2.finance.yahoo.com"):
        try:
            url=f"https://{host}/v8/finance/chart/KRW=X?{args}"
            request=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0"})
            with urllib.request.urlopen(request,timeout=25) as resp:
                raw=resp.read(2_000_000)
            values=parse_fx_chart(raw)
            anchor=values[values.date==FROZEN]
            if len(anchor)!=1:raise ValueError("missing 2026-11-10 FX baseline")
            fx_anchor=float(anchor.usdkrw_close.iloc[0])
            anchor_diff_bps=(fx_anchor/1334.0-1)*10000
            if abs(anchor_diff_bps)>5:
                raise ValueError(f"USDKRW frozen quote revised by {anchor_diff_bps:.2f}bp")
            if str(values.date.max())>str(expected_last) or str(values.date.max())<str(
                    expected_last-timedelta(days=5)):
                raise ValueError("FX source stale or includes future dated close")
            # FX is quoted KRW per USD, not USD per KRW.
            return values,{"status":"SOURCE_PASS","provider":host,
                "raw_sha256":hashlib.sha256(raw).hexdigest(),
                "anchor_2026_11_10":fx_anchor,
                "anchor_revision_bps":anchor_diff_bps,
                "latest":str(values.date.max())}
        except Exception as exc:
            errors.append({"provider":host,"error":type(exc).__name__,
                           "message":str(exc)[:130]})
    raise ValueError("forward FX source unavailable "+json.dumps(errors)[:450])

def run_snapshot(manifest,frozen,output,now_utc=None,
                 downloader=fetch_symbol,fx_downloader=fetch_fresh_fx):
    folder=Path(output);folder.mkdir(parents=True,exist_ok=True)
    end_session=most_recent_completed_ny_session(now_utc)
    expected=set(frozen["anchored_adjusted_close_usd"])
    us_assets=[a for a in manifest["universe"] if a["asset_class"]!="CRYPTO"]
    if set(a["symbol"] for a in us_assets)!=expected or len(expected)!=24:
        raise ValueError("frozen universe membership changed")
    source=[];tables={};future_prices=[]
    until=str(end_session+timedelta(days=1))
    for a in us_assets:
        symbol=a["symbol"]
        try:
            frame,provenance=downloader(symbol,
                from_date="2026-01-01",until=until)
            if frame is None:raise ValueError(str(provenance))
            frame,removed=apply_ticker_trade_eligibility(frame,a)
            qc=frozen_anchor_audit(frame,
                frozen["anchored_adjusted_close_usd"][symbol],end_session)
            meta={"symbol":symbol,"status":"PASS" if qc["anchor_match_within_5bp"]
                   else "HOLD_PRICE_SOURCE_DRIFT",
                  "provider":provenance.get("provider"),"raw_sha256":provenance.get("sha256"),
                  "removed_pre_listed":removed,**qc}
            if meta["status"]=="PASS":
                tables[symbol]=frame
                after=frame[frame.date>FROZEN].copy()
                after.insert(0,"symbol",symbol)
                future_prices.append(after)
        except Exception as e:
            meta={"symbol":symbol,"status":"HOLD_SOURCE_OR_PRICE_QC",
                  "error_type":type(e).__name__,"reason":str(e)[:160]}
        source.append(meta)
    pd.DataFrame(source).to_csv(folder/"all_24_market_price_health.csv",index=False)
    if future_prices:
        pd.concat(future_prices).to_csv(folder/"newly_observed_market_bars.csv",index=False)
    events=[];completed=[];fx_status={"status":"NOT_CHECKED"}
    status="HOLD_INCOMPLETE_24_SYMBOL_SOURCE"
    if len(tables)==24:
        benchmark=tables["QQQ"]
        for a in us_assets:
            if not a["model_eligible"]:continue
            new,done=new_proxy_signals(tables[a["symbol"]],benchmark,
                                      a["symbol"],a["industry"])
            events.extend(new)
            completed.extend(done)
        status=("HOLD_NO_NEW_SIGNALS" if not events else
                "HOLD_PENDING_OUTCOME" if not completed else
                "HOLD_INSUFFICIENT_NEW_EVIDENCE")
        try:
            fx,fx_status=fx_downloader(end_session)
            if completed:
                priced=pd.DataFrame([{
                    "date":x["date"],"symbol":x["symbol"],"entry_date":x["entry_date"],
                    "exit_date":x["exit_date"],"net_20bp":x["usd_net_20bp"]}
                    for x in completed])
                attached=attach_fx(priced,fx)
                for item,(_,r) in zip(completed,attached.iterrows()):
                    item["krw_mark_return"]=float(r.krw_mark_return)
                    item["fx_entry_reference"]=str(r.entry_fx_reference_date)
                    item["fx_exit_reference"]=str(r.exit_fx_reference_date)
            fx[fx.date>FROZEN].to_csv(folder/"newly_observed_usdkrw.csv",index=False)
        except Exception as e:
            fx_status={"status":"HOLD_FX_SOURCE_OR_ASOF","error":str(e)[:250]}
            status="HOLD_FX_PRICE_VALIDATION"
    observations=pd.DataFrame(events,columns=["date","symbol","industry","event",
        "regime","qqq_ret60","stock_ret5","signal_freeze_rule",
        "formal_prospective","horizon_complete","price_data_only",
        "v5_model_prediction"])
    observations.to_csv(folder/"new_proxy_signals_including_pending.csv",index=False)
    pd.DataFrame(completed).to_csv(folder/"matured_synthetic_outcomes.csv",index=False)
    fresh_formal=[x for x in completed if x["formal_prospective"]]
    unique_months=len(set(x["date"][:7] for x in fresh_formal))
    if len(fresh_formal)>=MIN_COMPLETED_SIGNALS and unique_months>=MIN_DISTINCT_FRESH_MONTHS:
        status="HOLD_FUTURE_MODEL_AND_EXECUTION_NOT_VERIFIED"
    report={"status":status,"research_only":True,"frozen_snapshot_date":FROZEN,
        "formal_prospective_start":FORMAL,
        "last_expected_complete_ny_session":str(end_session),
        "complete_us_sources":len(tables),"required_us_sources":24,
        "fx_source":fx_status,"new_proxy_events":len(events),
        "matured_synthetic_events":len(completed),
        "formal_completed_events":len(fresh_formal),
        "formal_completed_months":unique_months,
        "eligibility_requirements":{"at_least_completed":MIN_COMPLETED_SIGNALS,
                                    "at_least_distinct_months":MIN_DISTINCT_FRESH_MONTHS},
        "v5_frozen_model_available":False,"broker_fills_attested":False,
        "no_model_training_on_new_window":True,"promotion_allowed":False,
        "warnings":["Post-2026-11-10 observations before 2026-11-13 are not called prospective",
            "Rule signals are fixed-price proxy events, not broker orders",
            "No 2025/2026-examined model fitted or tuned using new bars",
            "Adjusted Yahoo prices may be retrospectively revised: >5bps anchor drift is HOLD",
            "Actual entry at 15m, volume execution and KRW cash settlement remain unverified"]}
    (folder/"decision.json").write_text(json.dumps(report,indent=2,ensure_ascii=False))
    print("FORWARD_V6",json.dumps({k:report[k] for k in (
         "status","complete_us_sources","required_us_sources",
         "new_proxy_events","matured_synthetic_events",
         "formal_completed_events","last_expected_complete_ny_session",
         "promotion_allowed")},ensure_ascii=False))
    return report

if __name__=="__main__":
    a=argparse.ArgumentParser()
    a.add_argument("--manifest",default="research/regime_countertrend/universe_sector_v3.json")
    a.add_argument("--frozen",default="research/regime_countertrend/frozen_market_anchor_v6.json")
    a.add_argument("--out",default="results/regime_countertrend/forward_v6")
    x=a.parse_args()
    run_snapshot(manifest_load(x.manifest),json.loads(Path(x.frozen).read_text()),x.out)
