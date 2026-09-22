from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import psycopg

SCHEMA="kalman-r5-exit-shadow-v1"
START=pd.Timestamp("2026-09-22T10:45:00Z")
STRATEGY="R5.1_BASE_HGB"
HORIZONS=(2,4,6,8)
COST=0.001

DEFAULT_ROOT="/mnt/gdrive"
DEFAULT_OUT="/mnt/gdrive/US_ETF/model_lab_v1/results/r5_exit_shadow_v1"

SIGNAL_STABLE=[
    "signal_id","symbol","as_of","signal_available_at","strategy_version",
    "expected_seq","entry_close","position_weight","research_non_overlap_entry",
]
OUTCOME_STABLE=[
    "outcome_id","signal_id","symbol","as_of","horizon_buckets","entry_expected_seq",
    "exit_expected_seq","entry_close","exit_close","maturity_timestamp",
    "position_weight","gross_return","net10_return",
]

def nts(x):
    return pd.to_datetime(x,utc=True,errors="coerce")

def signal_id(symbol,as_of):
    x=f"{STRATEGY}|{symbol.upper()}|{pd.Timestamp(as_of).isoformat()}"
    return hashlib.sha256(x.encode()).hexdigest()[:24]

def outcome_id(sid,h):
    return hashlib.sha256(f"{sid}|{h}".encode()).hexdigest()[:28]

def db_url():
    u=os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_URL_WRITER")
    if not u:
        raise RuntimeError("DATABASE_URL or DATABASE_URL_WRITER is required for read-only signal retrieval")
    return u

def fetch_signals(start):
    sql="""
    SELECT run_id,symbol,as_of,strategy_version,payload
    FROM strategy_signal
    WHERE market='US'
      AND strategy_version=%s
      AND signal='SHADOW'
      AND as_of >= %s
      AND lower(COALESCE(payload->>'allow_trade_shadow','false'))='true'
    ORDER BY as_of,run_id
    """
    with psycopg.connect(db_url()) as conn, conn.cursor() as cur:
        cur.execute(sql,(STRATEGY,start.to_pydatetime()))
        cols=[d.name for d in cur.description]
        return pd.DataFrame([dict(zip(cols,r)) for r in cur.fetchall()])

def read_panel(root,symbol):
    root=Path(root)
    paths=[
        root/"US_ETF/directional_research/canonical_history_v1/panel_1h_gap_aware"/f"{symbol}_1h_gap_aware.parquet",
        root/"US_ETF/directional_research/r4_live_canonical_v1/panel_1h_overlay"/f"{symbol}_1h_live.parquet",
    ]
    parts=[]
    for p in paths:
        if not p.exists():
            continue
        q=pd.read_parquet(p)
        keep=[x for x in ["expected_seq","timestamp","candle_time_utc","close","prev_bar_contiguous","data_gap_before"] if x in q.columns]
        q=q[keep].copy()
        if "timestamp" not in q.columns:
            if "candle_time_utc" not in q.columns:
                raise RuntimeError(f"{p} has no timestamp/candle_time_utc")
            q["timestamp"]=q["candle_time_utc"]
        q["timestamp"]=nts(q["timestamp"])
        q["expected_seq"]=pd.to_numeric(q["expected_seq"],errors="coerce")
        q["close"]=pd.to_numeric(q["close"],errors="coerce")
        q=q.loc[q["expected_seq"].notna() & q["timestamp"].notna() & q["close"].notna()].copy()
        q["expected_seq"]=q["expected_seq"].astype("int64")
        parts.append(q[["expected_seq","timestamp","close"]])
    if not parts:
        return pd.DataFrame(columns=["expected_seq","timestamp","close"])
    return (
        pd.concat(parts,ignore_index=True)
        .sort_values(["expected_seq","timestamp"])
        .drop_duplicates("expected_seq",keep="last")
        .reset_index(drop=True)
    )

def _bool(v):
    return str(v or "").strip().lower() in {"true","1","yes"}

def build_signal_rows(raw,root):
    if raw.empty:
        return pd.DataFrame(columns=SIGNAL_STABLE+["run_id","mapping_status"])
    raw=raw.copy()
    raw["as_of"]=nts(raw["as_of"])
    raw["_position_weight"]=raw["payload"].map(
        lambda p: float((p or {}).get("position_weight") or 1.0)
    )
    raw["_research_non_overlap"]=raw["payload"].map(
        lambda p: _bool((p or {}).get("shadow_entry_this_signal"))
    )
    raw=(
        raw.sort_values(["as_of","run_id"])
        .groupby(["symbol","as_of"],as_index=False)
        .agg(
            run_id=("run_id","last"),
            strategy_version=("strategy_version","last"),
            position_weight=("_position_weight","last"),
            research_non_overlap_entry=("_research_non_overlap","max"),
        )
    )

    rows=[]
    panels={}
    for r in raw.itertuples(index=False):
        symbol=str(r.symbol).upper()
        if symbol not in panels:
            panels[symbol]=read_panel(root,symbol)
        q=panels[symbol]
        hit=q.loc[q["timestamp"]==r.as_of]
        expected_seq=None
        entry_close=None
        status="EXACT_CANONICAL_MATCH"
        if hit.empty:
            status="SIGNAL_TIMESTAMP_NOT_IN_CANONICAL"
        else:
            z=hit.iloc[-1]
            expected_seq=int(z["expected_seq"])
            entry_close=float(z["close"])
        weight=float(r.position_weight)
        rows.append({
            "signal_id":signal_id(symbol,r.as_of),
            "run_id":str(r.run_id),
            "symbol":symbol,
            "as_of":r.as_of,
            "signal_available_at":r.as_of+pd.to_timedelta(3600,unit="s"),
            "strategy_version":STRATEGY,
            "expected_seq":expected_seq,
            "entry_close":entry_close,
            "position_weight":weight,
            "research_non_overlap_entry":bool(r.research_non_overlap_entry),
            "mapping_status":status,
            "prospective_boundary":START,
        })
    return pd.DataFrame(rows)

def build_outcomes(signals,root):
    rows=[]
    panels={}
    for r in signals.itertuples(index=False):
        if pd.isna(r.expected_seq) or pd.isna(r.entry_close):
            continue
        symbol=str(r.symbol)
        if symbol not in panels:
            panels[symbol]=read_panel(root,symbol).set_index("expected_seq")
        q=panels[symbol]
        entry=float(r.entry_close)
        seq=int(r.expected_seq)
        for h in HORIZONS:
            target=seq+h
            if target not in q.index:
                continue
            z=q.loc[target]
            if isinstance(z,pd.DataFrame):
                z=z.iloc[-1]
            exit_close=float(z["close"])
            maturity=nts(z["timestamp"])+pd.to_timedelta(3600,unit="s")
            gross=exit_close/entry-1.0
            w=float(r.position_weight)
            rows.append({
                "outcome_id":outcome_id(r.signal_id,h),
                "signal_id":r.signal_id,
                "symbol":symbol,
                "as_of":r.as_of,
                "horizon_buckets":h,
                "entry_expected_seq":seq,
                "exit_expected_seq":target,
                "entry_close":entry,
                "exit_close":exit_close,
                "maturity_timestamp":maturity,
                "position_weight":w,
                "gross_return":gross,
                "net10_return":w*gross-w*COST,
                "cost_contract":"10bps_x_position_weight",
                "source":"canonical_exact_expected_seq",
            })
    return pd.DataFrame(rows)

def _same(a,b,col):
    x=a[col]
    y=b[col]
    if pd.isna(x) and pd.isna(y):
        return True
    if col in {"entry_close","exit_close","position_weight","gross_return","net10_return"}:
        try:
            return abs(float(x)-float(y))<=1e-12
        except Exception:
            return False
    if col in {"as_of","signal_available_at","maturity_timestamp"}:
        return nts(x)==nts(y)
    return str(x)==str(y)

def append_immutable(path,new,key,stable_cols):
    path=Path(path)
    if path.exists():
        old=pd.read_parquet(path)
    else:
        old=pd.DataFrame(columns=new.columns if len(new.columns) else [key])

    if not old.empty and not new.empty:
        om=old.set_index(key,drop=False)
        for _,r in new.iterrows():
            k=r[key]
            if k not in om.index:
                continue
            prev=om.loc[k]
            if isinstance(prev,pd.DataFrame):
                raise RuntimeError(f"duplicate existing {key}={k}")
            bad=[c for c in stable_cols if c in old.columns and c in new.columns and not _same(prev,r,c)]
            if bad:
                raise RuntimeError(f"immutable ledger mismatch {key}={k} cols={bad}")

    combined=pd.concat([old,new],ignore_index=True,sort=False)
    if key in combined.columns:
        combined=combined.drop_duplicates(key,keep="first")
    tmp=path.with_suffix(path.suffix+".tmp")
    combined.to_parquet(tmp,index=False)
    tmp.replace(path)
    return combined

def status(signals,outcomes):
    horizon={}
    for h in HORIZONS:
        z=outcomes.loc[outcomes["horizon_buckets"]==h].copy() if not outcomes.empty else pd.DataFrame()
        days=int(nts(z["as_of"]).dt.floor("D").nunique()) if not z.empty else 0
        n=int(len(z))
        horizon[str(h)]={
            "mature_outcomes":n,
            "distinct_signal_days":days,
            "minimum_review_ready":n>=100 and days>=60,
            "preferred_review_ready":n>=150 and days>=90,
            "mean_net10_return":float(pd.to_numeric(z["net10_return"],errors="coerce").mean()) if n else None,
            "median_net10_return":float(pd.to_numeric(z["net10_return"],errors="coerce").median()) if n else None,
            "win_rate":float((pd.to_numeric(z["net10_return"],errors="coerce")>0).mean()) if n else None,
        }
    return {
        "schema":SCHEMA,
        "generated_at_utc":datetime.now(timezone.utc).isoformat(),
        "research_only":True,
        "production_changed":False,
        "live_exit_changed":False,
        "strategy_version":STRATEGY,
        "prospective_boundary":START.isoformat(),
        "signal_rows":int(len(signals)),
        "mapped_signal_rows":int((signals.get("mapping_status",pd.Series(dtype=str))=="EXACT_CANONICAL_MATCH").sum()),
        "outcome_rows":int(len(outcomes)),
        "horizons":horizon,
        "review_rule":"NO_HORIZON_SELECTION_BEFORE_MINIMUM_REVIEW_GATE",
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--root",default=DEFAULT_ROOT)
    ap.add_argument("--output-dir",default=DEFAULT_OUT)
    args=ap.parse_args()

    out=Path(args.output_dir)
    out.mkdir(parents=True,exist_ok=True)

    raw=fetch_signals(START)
    new_signals=build_signal_rows(raw,args.root)
    signals=append_immutable(out/"signals.parquet",new_signals,"signal_id",SIGNAL_STABLE)

    new_outcomes=build_outcomes(signals,args.root)
    outcomes=append_immutable(out/"outcomes.parquet",new_outcomes,"outcome_id",OUTCOME_STABLE)

    st=status(signals,outcomes)
    (out/"status.json").write_text(json.dumps(st,indent=2,default=str)+"\n")
    print(json.dumps(st,indent=2,default=str))
    print("SIGNALS=",out/"signals.parquet")
    print("OUTCOMES=",out/"outcomes.parquet")
    print("STATUS=",out/"status.json")

if __name__=="__main__":
    main()
