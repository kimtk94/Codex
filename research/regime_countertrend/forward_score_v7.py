"""CFM-V7 frozen JSON prospective SHADOW scorer.

Only a previously committed, audited read-only JSON model may generate
signals. No training code is called. All source marks must match the frozen
historical vintage (5bp max) on Nov10; the USDKRW rate is KRW per 1 USD.
First eligible trade decision AFTER Nov16 2026 US close. Four future NYSE
sessions must finish before outcome evaluation. No order actions / LIVE.
"""
import argparse
import hashlib
import json
import urllib.parse
import urllib.request
from datetime import datetime,timedelta,timezone
from pathlib import Path

import numpy as np
import pandas as pd

from .sector_price_sources_v3 import (
    fetch_symbol,apply_ticker_trade_eligibility,manifest_load
)
from .sector_hierarchy_v3 import make_pair
from .correlated_factor_model import feature_frame,FEATURES
from .peer_macro_v4 import macro_history,MACRO_ETFS,MACRO_COLS
from .krw_fx_v5 import parse_fx_chart,attach_fx
from .krw_detail_regime_v5 import fx_asof_signal,FX_FEATURES
from .forward_shadow_v6 import (
    most_recent_completed_ny_session,new_proxy_signals
)
from .freeze_krw_model_v7 import (
    FIRST_PROSPECTIVE,score_frozen_json,validate_frozen_integrity
)

ANCHOR_DATE="2026-11-10"
MAX_VINTAGE_DRIFT_BPS=5
MAX_FX_AGE_DAYS=5
MODEL_FILENAME="research/regime_countertrend/models/cfm_v7_frozen_krw_model.json"

def audit_frozen_vintage(source,fx,model):
    prov=model.get("source_price_provenance") or {}
    anchors=prov.get("anchors") or {}
    if len(anchors)!=24 or len(source)!=24:
        raise ValueError("frozen 24-asset price source contract absent")
    bad=[]
    for symbol,old in sorted(anchors.items()):
        if symbol not in source:
            bad.append(f"{symbol}:MISSING")
            continue
        frame=source[symbol]
        checks=old.get("historical_checkpoints",{})
        for date,reference in checks.items():
            if date<"2024-01-01":continue
            price=frame.loc[frame.date==date,"close"]
            if len(price)!=1:
                bad.append(f"{symbol}@{date}:MISSING")
                continue
            bps=(float(price.iloc[0])/float(reference)-1)*10000
            if abs(bps)>MAX_VINTAGE_DRIFT_BPS:
                bad.append(f"{symbol}@{date}:{bps:.3f}bp")
    fx_mark=fx.loc[fx.date==ANCHOR_DATE,"usdkrw_close"]
    if len(fx_mark)!=1:
        bad.append("USDKRW:ANCHOR_MISSING")
    else:
        old_fx=float(prov["usdkrw_last_close"])
        bps=(float(fx_mark.iloc[0])/old_fx-1)*10000
        if abs(bps)>MAX_VINTAGE_DRIFT_BPS:
            bad.append(f"USDKRW@{ANCHOR_DATE}:{bps:.3f}bp")
    return {"status":"PASS_FROZEN_V7_VINTAGE" if not bad else "HOLD_SOURCE_VINTAGE_DRIFT",
        "checks":sum(len([d for d in a["historical_checkpoints"] if d>="2024-01-01"])
                     for a in anchors.values())+1,
        "failures":bad,
        "model_training_end":model["training_last_session"],
        "model_first_forward":model["prospective_starts"]}

def fresh_fx(expected_last):
    start=int(pd.Timestamp("2024-01-01",tz="UTC").timestamp())
    end=int(pd.Timestamp(expected_last+timedelta(days=1),tz="UTC").timestamp())
    query=urllib.parse.urlencode({"period1":start,"period2":end,
        "interval":"1d","events":"history"})
    faults=[]
    for host in ("query1.finance.yahoo.com","query2.finance.yahoo.com"):
        try:
            url=f"https://{host}/v8/finance/chart/KRW=X?{query}"
            req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0"})
            with urllib.request.urlopen(req,timeout=25) as r:
                raw=r.read(3_000_000)
            fx=parse_fx_chart(raw)
            if str(fx.date.max())>str(expected_last):
                raise ValueError("future dated FX values")
            if (pd.Timestamp(expected_last)-pd.Timestamp(fx.date.max())).days>MAX_FX_AGE_DAYS:
                raise ValueError("stale FX source")
            if (fx.date==ANCHOR_DATE).sum()!=1:
                raise ValueError("missing FX anchor")
            return fx,{"status":"FX_SOURCE_PASS","provider":host,
                "sha256":hashlib.sha256(raw).hexdigest(),
                "last_date":str(fx.date.max())}
        except Exception as e:
            faults.append(f"{host}: {type(e).__name__}: {str(e)[:120]}")
    raise ValueError("FX_SOURCE_UNAVAILABLE: "+" ; ".join(faults))

def score_frozen_candidates(stocks,all_prices,fx,manifest,model,
                            latest_completed_session):
    """Only events at or AFTER freeze-start, scored using completed daily bars."""
    if str(latest_completed_session)<FIRST_PROSPECTIVE:
        return pd.DataFrame(),pd.DataFrame()
    market=macro_history({sym:all_prices[sym] for sym in MACRO_ETFS})
    scores=[];outcomes=[]
    for asset in manifest["universe"]:
        if not asset["model_eligible"]:continue
        sym=asset["symbol"]
        pair=make_pair(stocks[sym],all_prices["QQQ"],sym)
        feature=feature_frame(pair).rename(columns={"date_ny":"date"})
        events,matured=new_proxy_signals(stocks[sym],all_prices["QQQ"],
                                         sym,asset["industry"])
        for event in events:
            if event["date"]<FIRST_PROSPECTIVE:continue
            when=event["date"]
            feats=feature.loc[feature.date==when]
            mac=market.loc[market.date==when]
            if len(feats)!=1 or len(mac)!=1:
                raise ValueError(f"{sym}@{when} missing complete feature/macro rows")
            row=feats.merge(mac,on="date",validate="one_to_one")
            for key,value in (("symbol",sym),("event",event["event"])):
                row[key]=value
            for key,val in zip(FX_FEATURES,
                               fx_asof_signal([when],fx).iloc[0].tolist()):
                row[key]=float(val)
            if row[list(FEATURES)+list(MACRO_COLS)+list(FX_FEATURES)].isna().any().any():
                raise ValueError(f"{sym}@{when}: factor missing")
            probability=float(score_frozen_json(row,model)[0])
            scores.append({"date":when,"symbol":sym,"industry":asset["industry"],
                "event":event["event"],"probability_krw_win":probability,
                "would_select":probability>=model["probability_threshold"],
                "horizon_complete":bool(event["horizon_complete"]),
                "source_status":"FROZEN_V7_PRICE_ONLY",
                "model_name":model["model"],
                "research_only":True,"actual_trade_executed":False})
        for event in matured:
            if event["date"]<FIRST_PROSPECTIVE:continue
            outcomes.append(event)
    pred=pd.DataFrame(scores)
    resolved=pd.DataFrame(outcomes)
    if len(resolved):
        resolved=resolved.rename(columns={"usd_net_20bp":"net_20bp"})
        attached=attach_fx(resolved[[
            "date","symbol","entry_date","exit_date","net_20bp"]],fx)
        resolved["krw_mark_return"]=attached.krw_mark_return.to_numpy()
    return pred,resolved

def run_forward(model,manifest,out,now_utc=None,
                downloader=fetch_symbol,fx_downloader=fresh_fx):
    path=Path(out);path.mkdir(parents=True,exist_ok=True)
    validate_frozen_integrity(model)
    model_start=pd.Timestamp(model["prospective_starts"]).date()
    last=most_recent_completed_ny_session(now_utc)
    summary={"status":"HOLD_NO_POST_FREEZE_SESSION",
         "asof_last_nyse_session":str(last),"model_starts":str(model_start),
         "v7_model_frozen":True,"new_signals":0,
         "matured_krw_outcomes":0,
         "broker_fills_verified":False,"promotion_allowed":False}
    if last<model_start:
        (path/"decision.json").write_text(json.dumps(summary,indent=2))
        print("CFM_V7_FORWARD",json.dumps(summary))
        return summary
    until=str(last+timedelta(days=1))
    prices={};issues=[];status=[]
    for asset in manifest["universe"]:
        if asset["asset_class"]=="CRYPTO":continue
        sym=asset["symbol"]
        try:
            frame,meta=downloader(sym,from_date="2024-01-01",until=until)
            if frame is None:raise ValueError(str(meta))
            frame,_=apply_ticker_trade_eligibility(frame,asset)
            if str(frame.date.max())!=str(last):
                raise ValueError("missing actual completed NYSE session")
            prices[sym]=frame
            status.append({"symbol":sym,"status":"SOURCE_PASS",
                           "last_complete":str(last),
                           "source_sha256":meta.get("sha256")})
        except Exception as e:
            issues.append({"symbol":sym,"status":"HOLD_SOURCE",
                           "error":str(e)[:200]})
    (path/"source_health.json").write_text(json.dumps({
        "available":len(prices),"issues":issues,
        "last_complete":str(last),"market_sources":status},indent=2))
    if len(prices)!=24:
        summary["status"]="HOLD_PRICE_SOURCE_UNAVAILABLE"
        summary["price_sources"]=len(prices)
    else:
        try:
            fx,fxmeta=fx_downloader(last)
            vintage=audit_frozen_vintage(prices,fx,model)
            summary["vintage"]=vintage
            summary["fx_provenance"]=fxmeta
            if vintage["status"]!="PASS_FROZEN_V7_VINTAGE":
                summary["status"]="HOLD_SOURCE_VINTAGE_DRIFT"
            else:
                stocks={a["symbol"]:prices[a["symbol"]]
                    for a in manifest["universe"] if a["model_eligible"]}
                scores,outcomes=score_frozen_candidates(
                    stocks,prices,fx,manifest,model,last)
                if not scores.empty:
                    scores.to_csv(path/"frozen_model_forward_scores.csv",index=False)
                if not outcomes.empty:
                    outcomes.to_csv(path/"matured_price_only_krw_outcomes.csv",index=False)
                n=len(scores);m=len(outcomes)
                summary.update({"new_signals":n,"matured_krw_outcomes":m,
                    "status":"HOLD_NO_NEW_FROZEN_MODEL_SIGNAL" if n==0 else
                       "HOLD_FUTURE_OUTCOME_UNMATURED" if m==0 else
                       "HOLD_UNDERPOWERED_INDEPENDENT_FORWARD",
                    "no_retraining":True,"source_prices":len(prices)})
        except Exception as e:
            summary.update({"status":"HOLD_FX_OR_SCORER",
                            "error_type":type(e).__name__,
                            "error":str(e)[:250]})
    (path/"decision.json").write_text(json.dumps(summary,indent=2))
    print("CFM_V7_FORWARD",json.dumps(summary,ensure_ascii=False))
    return summary

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--model",default=MODEL_FILENAME)
    parser.add_argument("--manifest",default="research/regime_countertrend/universe_sector_v3.json")
    parser.add_argument("--out",default="results/regime_countertrend/forward_v7")
    a=parser.parse_args()
    if not Path(a.model).is_file():
        output=Path(a.out);output.mkdir(parents=True,exist_ok=True)
        report={"status":"HOLD_FROZEN_MODEL_FILE_NOT_COMMITTED",
           "path_expected":a.model,"promotion_allowed":False}
        (output/"decision.json").write_text(json.dumps(report,indent=2))
        print("CFM_V7_FORWARD",json.dumps(report))
    else:
        run_forward(json.loads(Path(a.model).read_text()),
            manifest_load(a.manifest),a.out)
