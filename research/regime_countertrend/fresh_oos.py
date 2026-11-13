"""Research-only QLD/QQQ post-2026-09-04 temporal validation.

Public OHLC providers; never use trade accounts, Neon, broker credentials or LIVE.
Read the historical training snapshot unchanged, anchor price basis on 2026-09-04,
and evaluate FIXED, previously explored rules without re-optimizing them.
"""
import argparse
import csv
import hashlib
import io
import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from .failure_diagnostics import run as proxy_events
from .robust_walkforward import build_events, RULES

ANCHOR="2026-09-04"
TARGET_END="2026-11-10"  # most recent complete NY session at research checkpoint
REF_CLOSE={"QLD":78.20,"QQQ":674.76}  # public Yahoo/StockAnalysis checkpoint
REF_TOL=0.012
PAIR=("QLD","QQQ")
COLUMNS=("open","high","low","close","volume")

def parse_stooq_csv(raw,symbol):
    table=list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
    if not table or "Date" not in table[0]:raise ValueError("Stooq schema/data unavailable")
    rows=[]
    for row in table:
        try:
            date=pd.Timestamp(row["Date"]).date().isoformat()
            nums=[float(row[k]) for k in ("Open","High","Low","Close","Volume")]
        except (ValueError,KeyError,TypeError):
            continue
        rows.append(dict(zip(("date",)+COLUMNS,(date,)+tuple(nums))))
    return validate_price_rows(pd.DataFrame(rows),symbol)

def parse_yahoo_chart(raw,symbol):
    data=json.loads(raw)
    block=data["chart"]["result"][0]
    dates=pd.to_datetime(block["timestamp"],unit="s",utc=True).tz_convert(
        ZoneInfo("America/New_York")).date.astype(str)
    q=block["indicators"]["quote"][0]
    rows=pd.DataFrame({"date":dates,**{k:q[k] for k in COLUMNS}})
    rows=rows.dropna(subset=list(COLUMNS))
    return validate_price_rows(rows,symbol)

def validate_price_rows(frame,symbol):
    if frame.empty:raise ValueError(f"{symbol}: no daily prices")
    d=frame.copy()
    d["date"]=pd.to_datetime(d["date"],errors="raise").dt.strftime("%Y-%m-%d")
    if d.date.duplicated().any():raise ValueError(f"{symbol}: duplicated days")
    for k in COLUMNS:d[k]=pd.to_numeric(d[k],errors="raise")
    if not np.isfinite(d[list(COLUMNS)].to_numpy()).all():
        raise ValueError(f"{symbol}: invalid numbers")
    if (d[list(COLUMNS[:4])]<=0).any().any() or (d.volume<0).any():
        raise ValueError(f"{symbol}: nonpositive price or volume")
    if ((d.high<d[["open","close","low"]].max(axis=1))|
        (d.low>d[["open","high","close"]].min(axis=1))).any():
        raise ValueError(f"{symbol}: invalid OHLC range")
    return d.sort_values("date").reset_index(drop=True)

def download(symbol,provider,from_day="2026-08-20",through="2026-11-11"):
    if provider=="stooq":
        url="https://stooq.com/q/d/l/?"+urllib.parse.urlencode({
            "s":symbol.lower()+".us","d1":from_day.replace("-",""),
            "d2":through.replace("-",""),"i":"d"})
    elif provider=="yahoo":
        start=int(pd.Timestamp(from_day,tz="UTC").timestamp())
        end=int(pd.Timestamp(through,tz="UTC").timestamp())
        url=f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?"+urllib.parse.urlencode({
            "period1":start,"period2":end,"interval":"1d","events":"history"})
    else:raise ValueError("invalid provider")
    req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0 (research-data-validation; public)"})
    with urllib.request.urlopen(req,timeout=22) as resp:
        raw=resp.read(3_000_000)
    return (parse_stooq_csv if provider=="stooq" else parse_yahoo_chart)(raw,symbol),hashlib.sha256(raw).hexdigest()

def stitch(history,fresh,minimum_recent=TARGET_END):
    h=history.sort_values("date_ny").reset_index(drop=True).copy()
    if h.date_ny.iloc[-1]!=ANCHOR:raise ValueError("historical anchor changed")
    if h.date_ny.duplicated().any():raise ValueError("historical duplicate date")
    if any(s not in fresh for s in PAIR):raise ValueError("both symbols required")
    adapted={};checks={}
    for sym in PAIR:
        d=validate_price_rows(fresh[sym],sym)
        anchor=d.loc[d.date==ANCHOR]
        if len(anchor)!=1:raise ValueError(f"{sym}: missing same-day overlap anchor")
        expected=float(h.iloc[-1][f"close_{sym.lower()}"])
        observed=float(anchor.close.iloc[0])
        ratio=expected/observed
        if not .985<=ratio<=1.015:
            raise ValueError(f"{sym}: unverified price basis/split: factor={ratio:.6f}")
        after=d[d.date>ANCHOR].copy()
        if after.empty or after.date.max()<minimum_recent:
            raise ValueError(f"{sym}: stale source")
        if abs(float(after.iloc[-1].close)-REF_CLOSE[sym])/REF_CLOSE[sym]>REF_TOL and minimum_recent==TARGET_END:
            raise ValueError(f"{sym}: latest close cross-source check fails")
        # OHLC adjusted to historical *price basis*; volume kept unchanged.
        for k in ("open","high","low","close"):after[k]*=ratio
        prefix={k:f"{k}_{sym.lower()}" for k in COLUMNS}
        adapted[sym]=after.rename(columns={"date":"date_ny",**prefix})
        checks[sym]={"anchor_source":observed,"anchor_historical":expected,
          "price_basis_factor":ratio,"last_raw_date":str(d.date.max()),
          "last_raw_close":float(d.close.iloc[-1]),
          "added_rows":len(after)}
    q=adapted["QQQ"].merge(adapted["QLD"],on="date_ny",how="outer",indicator=True,validate="one_to_one")
    if not (q._merge=="both").all():raise ValueError("unmatched QLD/QQQ trading days")
    if q.date_ny.duplicated().any() or q.date_ny.min()<=ANCHOR:raise ValueError("broken appends")
    merged=pd.concat([h,q.drop(columns=["_merge"])],ignore_index=True)
    merged=merged.sort_values("date_ny").reset_index(drop=True)
    for sym in PAIR:
        lower=sym.lower()
        merged[f"return_1d_{lower}"]=merged[f"close_{lower}"].pct_change()
    merged["relative_return_qld_minus_2x_qqq"]=merged.return_1d_qld-2*merged.return_1d_qqq
    return merged,checks

def evaluate_oos(history,merged):
    original,_=proxy_events(history)
    candidate,_=proxy_events(merged)
    # No signals at or before the known research boundary count as fresh.
    new=candidate[candidate.date>ANCHOR][["date","event"]]
    if new.empty:
        return pd.DataFrame(),pd.DataFrame(),{"status":"INSUFFICIENT_FRESH_SIGNALS","n_signals":0,"promotion_allowed":False,"note":"No eligible original UP_DIP or DOWN_RALLY signals in the new 46-session window; cannot evaluate rule returns."}
    scored=build_events(merged,new)
    scored["fresh_after_boundary"]=True
    rows=[]
    for event_name,x in (("ALL",scored),("UP_DIP",scored[scored.event=="UP_DIP"]),
                         ("DOWN_RALLY",scored[scored.event=="DOWN_RALLY"])):
        for rule in RULES:
            y=x[x[rule]]
            rows.append({"event":event_name,"rule":rule,"opportunities":len(x),
              "taken":len(y),"mean_net_taken":float(y.net_20bp.mean()) if len(y) else None,
              "net_per_opportunity":float(y.net_20bp.sum()/len(x)) if len(x) else None,
              "negative_taken":int((y.net_20bp<0).sum()),
              "worst_taken":float(y.net_20bp.min()) if len(y) else None})
    table=pd.DataFrame(rows)
    return scored,table,{
      "status":"FURTHER_TEMPORAL_VALIDATION_NOT_UNTOUCHED_OOS",
      "n_signals":len(scored),"n_up_dip":int((scored.event=="UP_DIP").sum()),
      "n_down_rally":int((scored.event=="DOWN_RALLY").sum()),
      "first_signal":str(scored.date.min()),"last_signal":str(scored.date.max()),
      "baseline_n_prior":len(original),
      "promotion_allowed":False,
      "warnings":["2025-26 was previously inspected; do not claim independent alpha",
        "Frozen +3/-3, next daily open, 4-day exit, 20bp roundtrip only",
        "No actual 15m first-bar fills, market impact, MDD or portfolio returns",
        "Small fresh signal sample may be insufficient for significance"]}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--history",default="research/regime_countertrend/data/QLD_QQQ_daily_alignment.csv")
    p.add_argument("--out",default="results/regime_countertrend/fresh_oos")
    a=p.parse_args()
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    log={"research_only":True,"snapshot_cutoff":ANCHOR,"target_last_complete_session":TARGET_END,
         "fetched_utc":datetime.now(timezone.utc).isoformat(),"provider_attempts":[]}
    try:
        data={};hashes={}
        for symbol in PAIR:
            failures=[]
            for provider in ("stooq","yahoo"):
                try:
                    table,sha=download(symbol,provider)
                    data[symbol]=table;hashes[symbol]={"provider":provider,"raw_sha256":sha}
                    break
                except Exception as e:
                    failures.append({"source":provider,"error":type(e).__name__,
                                     "detail":str(e)[:140]})
            log["provider_attempts"].append({"symbol":symbol,"failures":failures,
                                               "success":hashes.get(symbol)})
            if symbol not in data:raise ValueError(f"{symbol} sources unavailable")
        history=pd.read_csv(a.history)
        merged,checks=stitch(history,data)
        scored,comparison,meta=evaluate_oos(history,merged)
        log.update(meta)
        log["price_checks"]=checks
        log["fresh_paired_days"]=len(merged)-len(history)
        log["last_date"]=str(merged.date_ny.iloc[-1])
        scored.to_csv(out/"new_signals.csv",index=False)
        comparison.to_csv(out/"locked_rules.csv",index=False)
        merged[merged.date_ny>ANCHOR].to_csv(out/"paired_public_daily_prices.csv",index=False)
    except Exception as e:
        log.update({"status":"HOLD_SOURCE_OR_DATA_VALIDATION","error":str(e)[:300],
                    "promotion_allowed":False})
    (out/"provenance.json").write_text(json.dumps(log,ensure_ascii=False,indent=2))
    print("FRESH_OOS",json.dumps(log,ensure_ascii=False))
if __name__=="__main__":main()
