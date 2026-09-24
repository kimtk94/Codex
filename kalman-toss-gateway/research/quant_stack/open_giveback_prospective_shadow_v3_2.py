#!/usr/bin/env python3
"""Frozen OPEN_GIVEBACK_5M prospective shadow v3.2.

Research only: reads managed_position and Alpaca IEX, never submits orders,
never mutates managed positions, never writes Neon.
"""
from __future__ import annotations
import argparse, json, os, sqlite3, hashlib
from pathlib import Path
from datetime import datetime, time as dt_time, timezone
from zoneinfo import ZoneInfo
import pandas as pd
from dotenv import load_dotenv
from research.quant_stack.open_revalidation_backtest import (
    _fetch_alpaca_1m, _effective_bar_close, _last_completed_close,
    _first_open_at_or_after,
)

NY=ZoneInfo("America/New_York")
POLICY="OPEN_GIVEBACK_5M"
SOURCE_COMMIT="f56d51c795989c33961ee98cfd11fffefae235b5"
COLS=[
"shadow_id","position_id","symbol","strategy_version","entry_signal_as_of",
"evaluation_day_et","evaluated_at_utc","policy","source_commit","feed","adjustment",
"model_entry_price","actual_entry_fill_price","prev_close_price","open_0_price","open_5_price",
"position_return_prev_close","position_return_5m","open_momentum_5m",
"giveback_prev_close_to_5m","trigger","decision","state_at_evaluation","note"
]

def active_positions(db:Path):
    con=sqlite3.connect(db); con.row_factory=sqlite3.Row
    try:
        return [dict(x) for x in con.execute(
            """SELECT * FROM managed_position
               WHERE state IN ('OPEN','ADD_ON_RESERVED','ADD_ON_SUBMITTED')
               ORDER BY created_at"""
        ).fetchall()]
    finally: con.close()

def main():
    load_dotenv(os.environ.get("KALMAN_ENV_FILE","/opt/kalman/.env"),override=True)
    ap=argparse.ArgumentParser()
    ap.add_argument("--state-db",default=os.environ.get("TRADING_STATE_DB","/opt/kalman/state/trading.sqlite3"))
    ap.add_argument("--out",default="/opt/kalman/state/research/open_giveback_v3_2")
    ap.add_argument("--feed",default="iex")
    ap.add_argument("--evaluation-date-et",default=None)
    args=ap.parse_args()
    now=datetime.now(timezone.utc); now_et=now.astimezone(NY)
    eval_day=pd.Timestamp(args.evaluation_date_et).date() if args.evaluation_date_et else now_et.date()
    out=Path(args.out); out.mkdir(parents=True,exist_ok=True)
    ledger=out/"shadow_decisions.parquet"
    pos=active_positions(Path(args.state_db))
    emitted=[]; skipped=[]
    for p in pos:
        sym=str(p.get("symbol") or "").upper().replace(".","-")
        try:
            entry_ts=pd.Timestamp(p["entry_signal_as_of"])
            entry_ts=entry_ts.tz_localize("UTC") if entry_ts.tzinfo is None else entry_ts.tz_convert("UTC")
            entry_day=entry_ts.tz_convert(NY).date()
            if entry_day>=eval_day:
                skipped.append({"position_id":p["position_id"],"symbol":sym,"reason":"NOT_CROSS_SESSION_YET"}); continue
            # Do not evaluate before 09:38 ET: 09:35 bar plus original +3m tolerance.
            if args.evaluation_date_et is None and (now_et.hour,now_et.minute)<(9,38):
                skipped.append({"position_id":p["position_id"],"symbol":sym,"reason":"BEFORE_0938_ET"}); continue
            start=pd.Timestamp(datetime.combine(entry_day,dt_time(9,20),tzinfo=NY)).tz_convert("UTC")
            end=pd.Timestamp(datetime.combine(eval_day,dt_time(9,40),tzinfo=NY)).tz_convert("UTC")
            bars=_fetch_alpaca_1m(sym,start_utc=start,end_utc=end,feed=args.feed)
            if bars.empty: raise RuntimeError("NO_ALPACA_BARS")
            model_entry=_last_completed_close(bars,_effective_bar_close(entry_ts))
            local=bars.timestamp.dt.tz_convert(NY)
            prior=bars.loc[(local.dt.date==entry_day)&(local.dt.time>=dt_time(9,30))&(local.dt.time<dt_time(16,0))]
            today=bars.loc[(local.dt.date==eval_day)&(local.dt.time>=dt_time(9,30))&(local.dt.time<dt_time(16,0))]
            if model_entry is None or prior.empty or today.empty: raise RuntimeError("SESSION_FEATURES_UNAVAILABLE")
            prev=float(prior.iloc[-1].close)
            o0=_first_open_at_or_after(today,local_hour=9,local_minute=30)
            o5=_first_open_at_or_after(today,local_hour=9,local_minute=35)
            if o0 is None or o5 is None: raise RuntimeError("OPEN_0_OR_5_UNAVAILABLE")
            pos_prev=prev/model_entry-1.0
            pos5=o5/model_entry-1.0
            mom5=o5/o0-1.0
            giveback=pos_prev-pos5
            trig=bool(pos_prev>=.005 and giveback>=.007 and mom5<=0.0)
            key=f"{p['position_id']}|{eval_day}|{POLICY}"
            emitted.append({
                "shadow_id":hashlib.sha256(key.encode()).hexdigest()[:24],
                "position_id":p["position_id"],"symbol":sym,"strategy_version":p.get("strategy_version"),
                "entry_signal_as_of":str(p.get("entry_signal_as_of")),"evaluation_day_et":str(eval_day),
                "evaluated_at_utc":now.isoformat(),"policy":POLICY,"source_commit":SOURCE_COMMIT,
                "feed":args.feed,"adjustment":"all","model_entry_price":model_entry,
                "actual_entry_fill_price":float(p["entry_avg_fill_price"]) if p.get("entry_avg_fill_price") else None,
                "prev_close_price":prev,"open_0_price":o0,"open_5_price":o5,
                "position_return_prev_close":pos_prev,"position_return_5m":pos5,
                "open_momentum_5m":mom5,"giveback_prev_close_to_5m":giveback,
                "trigger":trig,"decision":"GIVEBACK_EXIT" if trig else "KEEP_FIXED_4",
                "state_at_evaluation":p.get("state"),"note":"SHADOW_ONLY_NO_ORDER"
            })
        except Exception as e:
            skipped.append({"position_id":p.get("position_id"),"symbol":sym,"reason":f"{type(e).__name__}: {e}"})
    new=pd.DataFrame(emitted,columns=COLS)
    if ledger.is_file():
        try: old=pd.read_parquet(ledger)
        except Exception: old=pd.DataFrame(columns=COLS)
        allx=pd.concat([old,new],ignore_index=True)
    else: allx=new
    allx=allx.reindex(columns=COLS).drop_duplicates("shadow_id",keep="last")
    allx.to_parquet(ledger,index=False)
    status={"schema":"kalman-open-giveback-prospective-shadow-v3.2","generated_at_utc":now.isoformat(),
      "research_only":True,"production_changed":False,"live_trading":False,"neon_write":False,
      "policy":POLICY,"source_commit":SOURCE_COMMIT,"feed":args.feed,"adjustment":"all",
      "evaluation_day_et":str(eval_day),"active_positions_seen":len(pos),"evaluated":len(emitted),
      "triggered":sum(bool(x["trigger"]) for x in emitted),"skipped":skipped,"ledger_rows":len(allx),
      "ledger":str(ledger)}
    (out/"status.json").write_text(json.dumps(status,indent=2,default=str)+"\n")
    print(json.dumps(status,indent=2,default=str))
    if emitted:
        print(pd.DataFrame(emitted)[["symbol","decision","position_return_prev_close","giveback_prev_close_to_5m","open_momentum_5m"]].to_string(index=False))
    return 0

if __name__=="__main__": raise SystemExit(main())
