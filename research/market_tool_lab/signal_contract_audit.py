"""Validate external Kalman entry-signal export against daily OHLCV.

Never generate entry signals from future data. Reject undocumented timestamps,
duplicate signals, unknown symbols, and non-trading dates. Read-only research.
"""
import argparse,csv,json
from collections import Counter
from datetime import date
from pathlib import Path
from triple_barrier_reference import triple_barrier

REQUIRED={"date_ny","symbol","signal","strategy","regime"}

def evaluate(bars_path,signals_path,fee_rate=0.001,slippage_rate=0.0005):
    if min(fee_rate,slippage_rate)<0: raise ValueError("negative costs")
    with Path(bars_path).open(newline="",encoding="utf-8-sig") as f:
        daily=list(csv.DictReader(f))
    date_index={r["date_ny"]:i for i,r in enumerate(daily)}
    if len(date_index)!=len(daily): raise ValueError("duplicate daily dates")
    with Path(signals_path).open(newline="",encoding="utf-8-sig") as f:
        reader=csv.DictReader(f)
        if not REQUIRED.issubset(reader.fieldnames or []): raise ValueError("missing required signal columns")
        signals=list(reader)
    keyset=set()
    buckets={}
    for row in signals:
        date.fromisoformat(row["date_ny"])
        symbol=row["symbol"].upper()
        if symbol not in ("QQQ","QLD"): raise ValueError("unsupported symbol")
        if row["date_ny"] not in date_index: raise ValueError("signal date missing from bar data")
        if row["signal"] not in ("0","1"): raise ValueError("signal must be 0 or 1")
        if not row["strategy"].strip() or not row["regime"].strip(): raise ValueError("missing provenance")
        key=(row["date_ny"],symbol,row["strategy"])
        if key in keyset: raise ValueError("duplicate signal")
        keyset.add(key)
        if row["signal"]=="1":
            i=date_index[row["date_ny"]]
            if i+4>=len(daily): continue
            bars=[{k:float(r[f"{k}_{symbol.lower()}"]) for k in ("open","high","low","close")} for r in daily[i:i+5]]
            event=triple_barrier(bars,0)
            bucket=(row["strategy"],symbol,row["regime"])
            agg=buckets.setdefault(bucket,{"events":0,"tp":0,"sl":0,"time":0,"net_sum":0.0})
            agg["events"]+=1
            agg[event["reason"].lower()]+=1
            agg["net_sum"]+=(1+event["gross_return"])*(1-fee_rate-slippage_rate)**2-1
    return {"status":"DESCRIPTIVE_ONLY","signals_read":len(signals),"groups":[
       {"strategy":k[0],"symbol":k[1],"regime":k[2],**v,
        "mean_net_event_return":v["net_sum"]/v["events"]}
       for k,v in sorted(buckets.items())],
       "warnings":["Assumes entry at signal-date close; source signals must be timestamp-validated externally.",
       "Overlapping signals are NOT executed as a portfolio; no MDD or strategy CAGR.",
       "All in-sample or post-hoc signals invalidate causal performance interpretation."]}

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--bars",required=True);p.add_argument("--signals",required=True)
    p.add_argument("--output");a=p.parse_args()
    report=evaluate(a.bars,a.signals)
    content=json.dumps(report,indent=2,ensure_ascii=False)
    if a.output:Path(a.output).write_text(content+"\n",encoding="utf-8")
    print(content)
