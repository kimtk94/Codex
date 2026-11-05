"""Read-only real-fill / 15-minute price-path attribution.

Inputs are real aggregated fills and regular-session 15m bars, not synthetic
backtests. Bar timestamps are UTC *bar starts*. The containing fill bar and
exit bar are excluded because OHLC cannot establish intrabar sequence.
All metrics are observational, never automatically actionable.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd

TRADES_REQUIRED = {
    "trade_id","symbol","side","signal_ts_utc","entry_ts_utc",
    "exit_ts_utc","entry_price","exit_price","quantity","fees_usd"
}
BARS_REQUIRED = {"symbol","ts_utc","open","high","low","close","volume"}
ALLOWED_SIDES = {"LONG","SHORT"}

def timestamp(series, label):
    ts = pd.to_datetime(series,utc=True,errors="raise")
    if ts.isna().any():
        raise ValueError(f"{label}: null timestamp")
    return ts

def prepare(trades, bars):
    t=trades.copy()
    b=bars.copy()
    missing=TRADES_REQUIRED-set(t)
    if missing: raise ValueError(f"missing trade columns: {sorted(missing)}")
    missing=BARS_REQUIRED-set(b)
    if missing: raise ValueError(f"missing bar columns: {sorted(missing)}")
    if t.trade_id.isna().any() or t.trade_id.duplicated().any():
        raise ValueError("trade_id must be nonnull unique; aggregate partial fills upstream")
    for field in ("signal_ts_utc","entry_ts_utc","exit_ts_utc"):
        t[field]=timestamp(t[field],field)
    b["ts_utc"]=timestamp(b.ts_utc,"ts_utc")
    if ((t.signal_ts_utc>t.entry_ts_utc)|(t.entry_ts_utc>=t.exit_ts_utc)).any():
        raise ValueError("invalid chronology signal -> entry -> exit")
    if not t.side.isin(ALLOWED_SIDES).all():
        raise ValueError("side must be LONG or SHORT")
    if t.symbol.isna().any() or b.symbol.isna().any():
        raise ValueError("null symbol")
    for col in ("entry_price","exit_price","quantity","fees_usd"):
        t[col]=pd.to_numeric(t[col],errors="raise")
    if (t[["entry_price","exit_price","quantity"]]<=0).any().any() or (t.fees_usd<0).any():
        raise ValueError("invalid trade prices, quantities or fees")
    for col in ("open","high","low","close","volume"):
        b[col]=pd.to_numeric(b[col],errors="raise")
    if b[["open","high","low","close","volume"]].isna().any().any() or (b[["open","high","low","close"]]<=0).any().any() or (b.volume<0).any():
        raise ValueError("invalid OHLCV")
    if ((b.high<b[["open","low","close"]].max(axis=1))|(b.low>b[["open","high","close"]].min(axis=1))).any():
        raise ValueError("invalid OHLC range")
    if b.duplicated(["symbol","ts_utc"]).any():
        raise ValueError("duplicate symbol/bar start")
    b=b.sort_values(["symbol","ts_utc"])
    if "intended_entry_price" in t:
        t["intended_entry_price"]=pd.to_numeric(t.intended_entry_price,errors="coerce")
        if (t.intended_entry_price.dropna()<=0).any():
            raise ValueError("invalid intended price")
    return t,b

def attribute(trades,bars,adverse_threshold=.015,giveback_threshold=.015,slippage_bps=10.):
    t,b=prepare(trades,bars)
    records=[]
    for _,r in t.iterrows():
        side=1 if r.side=="LONG" else -1
        full=b[(b.symbol==r.symbol)&(b.ts_utc>=r.entry_ts_utc)&
                (b.ts_utc+pd.Timedelta(minutes=15)<=r.exit_ts_utc)].copy()
        near=full[full.ts_utc+pd.Timedelta(minutes=15)<=r.entry_ts_utc+pd.Timedelta(minutes=60)]
        # Four contiguous 15m bars starting exactly at the fill time are
        # necessary to call the first-hour observation complete.
        first_hour_complete=(len(near)==4 and
            near.ts_utc.iloc[0]==r.entry_ts_utc and
            all((near.ts_utc.diff().dropna()==pd.Timedelta(minutes=15))))
        gross=side*(r.exit_price/r.entry_price-1)
        net=gross-float(r.fees_usd)/(r.entry_price*r.quantity)
        def excursion(z):
            if z.empty: return (None,None)
            favorable=(z.high.max()/r.entry_price-1) if side==1 else (1-z.low.min()/r.entry_price)
            adverse=(z.low.min()/r.entry_price-1) if side==1 else (1-z.high.max()/r.entry_price)
            return float(favorable),float(adverse)
        mfe,mae=excursion(full)
        mfe60,mae60=excursion(near) if first_hour_complete else (None,None)
        intent=r.get("intended_entry_price",np.nan)
        signed_slippage=(side*(r.entry_price/intent-1)*10000
                         if pd.notna(intent) else None)
        pattern="NO_LOSS" if net>=0 else "LOSS_UNDETERMINED"
        if net<0:
            if signed_slippage is not None and signed_slippage>slippage_bps:
                pattern="ENTRY_SLIPPAGE_ABOVE_THRESHOLD"
            elif first_hour_complete and mae60 is not None and mae60<=-adverse_threshold:
                pattern="EARLY_ADVERSE_MOVE"
            elif mfe is not None and mfe>=giveback_threshold:
                pattern="FAVORABLE_EXCURSION_GIVEN_BACK"
        records.append({
            "trade_id":r.trade_id,"symbol":r.symbol,"side":r.side,
            "entry_ts_utc":r.entry_ts_utc.isoformat(),"exit_ts_utc":r.exit_ts_utc.isoformat(),
            "gross_return":gross,"net_return":net,"lost":bool(net<0),
            "full_bars":len(full),"first_hour_complete":bool(first_hour_complete),
            "mfe_full_bars":mfe,"mae_full_bars":mae,
            "mfe_first_hour":mfe60,"mae_first_hour":mae60,
            "signed_entry_slippage_bps":signed_slippage,
            "exit_reason_reported":r.get("exit_reason",None),
            "observed_pattern":pattern,
            "interpretation":"OBSERVATIONAL_NOT_CAUSAL"})
    out=pd.DataFrame(records)
    meta={
        "status":"COMPLETE" if len(out) and bool(out.first_hour_complete.all()) else "PARTIAL_INTRADAY_COVERAGE",
        "trades":len(out),"first_hour_covered":int(out.first_hour_complete.sum()) if len(out) else 0,
        "losing_trades":int(out.lost.sum()) if len(out) else 0,
        "missing_intended_entry_price":int(out.signed_entry_slippage_bps.isna().sum()) if len(out) else 0,
        "limitations":[
            "15-minute bars exclude containing entry/exit bars and cannot determine same-bar stop/target ordering",
            "No slippage inference without intended entry price",
            "No causal classification from OHLC alone",
            "Partial fills must be aggregated with actual fees and quantities",
            "Intraday bar adjusted/unadjusted price basis must match executions",
            "No strategy promotion or LIVE modification"],
    }
    return out,meta

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--trades",required=True)
    p.add_argument("--bars",required=True)
    p.add_argument("--out",default="results/regime_countertrend/execution")
    args=p.parse_args()
    trades,report=attribute(pd.read_csv(args.trades),pd.read_csv(args.bars))
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    trades.to_csv(out/"trade_attribution.csv",index=False)
    (out/"coverage.json").write_text(json.dumps(report,indent=2))
    print(json.dumps(report))
if __name__=="__main__":main()
