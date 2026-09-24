#!/usr/bin/env python3
"""Research-only prospective shadow recorder for frozen OPEN_GIVEBACK_5M.

No orders, no production strategy mutation, no Neon writes.
Reads the current open-revalidation audit/features and appends idempotent shadow decisions.
"""
from __future__ import annotations
import argparse, json, hashlib
from pathlib import Path
from datetime import datetime, timezone
import pandas as pd

SOURCE_COMMIT="f56d51c795989c33961ee98cfd11fffefae235b5"
POLICY="OPEN_GIVEBACK_5M"

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--audit",default="/mnt/gdrive/US_ETF/model_lab_v1/results/open_revalidation_v1/open_revalidation_trade_audit.parquet")
    ap.add_argument("--out",default="/mnt/gdrive/US_ETF/model_lab_v1/results/open_revalidation_v1/prospective_shadow_v3_1")
    ap.add_argument("--since",default="2026-09-03")
    args=ap.parse_args()
    audit=Path(args.audit); out=Path(args.out); out.mkdir(parents=True,exist_ok=True)
    if not audit.is_file(): raise SystemExit(f"AUDIT_MISSING {audit}")
    a=pd.read_parquet(audit)
    req=["fold","symbol","entry_timestamp","entry_seq","net_return","weight","entry_price_iex","fixed4_exit_price_iex",
         "open_5_price_iex","position_return_prev_close","giveback_prev_close_to_5m","open_momentum_5m","revalidation_data_ready"]
    miss=[c for c in req if c not in a]
    if miss: raise SystemExit("MISSING_COLUMNS "+",".join(miss))
    a["entry_timestamp"]=pd.to_datetime(a["entry_timestamp"],utc=True,errors="coerce")
    z=a.loc[(a["entry_timestamp"]>=pd.Timestamp(args.since,tz="UTC")) & a["revalidation_data_ready"].fillna(False)].copy()
    rows=[]
    for _,r in z.iterrows():
        trig=bool(float(r.position_return_prev_close)>=0.005 and float(r.giveback_prev_close_to_5m)>=0.007 and float(r.open_momentum_5m)<=0.0)
        fixed_raw=float(r.fixed4_exit_price_iex)/float(r.entry_price_iex)-1.0
        cand_raw=float(r.open_5_price_iex)/float(r.entry_price_iex)-1.0
        shadow_net=float(r.net_return)+float(r.weight)*(cand_raw-fixed_raw) if trig else float(r.net_return)
        key=f"{r['fold']}|{r['symbol']}|{r['entry_timestamp'].isoformat()}|{r['entry_seq']}|{POLICY}"
        rows.append({"shadow_id":hashlib.sha256(key.encode()).hexdigest()[:24],"policy":POLICY,"source_commit":SOURCE_COMMIT,
          "fold":str(r["fold"]),"symbol":str(r["symbol"]),"entry_timestamp":r["entry_timestamp"].isoformat(),"entry_seq":int(r["entry_seq"]),
          "evaluated_at_et":"09:35","trigger":trig,"decision":"GIVEBACK_EXIT" if trig else "KEEP_FIXED_4",
          "position_return_prev_close":float(r.position_return_prev_close),"giveback_prev_close_to_5m":float(r.giveback_prev_close_to_5m),
          "open_momentum_5m":float(r.open_momentum_5m),"baseline_fixed4_net_return":float(r.net_return),
          "shadow_candidate_net_return":shadow_net,"paired_delta":shadow_net-float(r.net_return)})
    new=pd.DataFrame(rows)
    ledger=out/"shadow_decisions.parquet"
    if ledger.is_file():
        old=pd.read_parquet(ledger)
        new=pd.concat([old,new],ignore_index=True).drop_duplicates("shadow_id",keep="last")
    if not new.empty: new=new.sort_values(["entry_timestamp","symbol"]).reset_index(drop=True)
    new.to_parquet(ledger,index=False)
    status={"schema":"kalman-open-giveback-prospective-shadow-v3.1","generated_at_utc":datetime.now(timezone.utc).isoformat(),
      "research_only":True,"production_changed":False,"live_trading":False,"neon_write":False,"policy":POLICY,
      "source_commit":SOURCE_COMMIT,"frozen_contract":{"position_return_prev_close_gte":0.005,"giveback_prev_close_to_5m_gte":0.007,
      "open_momentum_5m_lte":0.0,"evaluation_et":"09:35"},"since":args.since,"rows":int(len(new)),
      "triggered":int(new["trigger"].sum()) if len(new) else 0,"ledger":str(ledger)}
    (out/"status.json").write_text(json.dumps(status,indent=2)+"\n")
    print(json.dumps(status,indent=2))
if __name__=="__main__": main()
