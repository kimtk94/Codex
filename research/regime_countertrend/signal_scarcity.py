"""Explain zero fresh UP_DIP / DOWN_RALLY signals without modifying thresholds."""
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd

from .failure_diagnostics import run as proxy_events
from .robust_walkforward import signal_features

CUTOFF="2026-09-04"

def diagnose(history,appended):
    old=history.sort_values("date_ny").copy()
    if old.date_ny.iloc[-1]!=CUTOFF:
        raise ValueError("historical price cutoff does not match locked boundary")
    fresh=appended.sort_values("date_ny").copy()
    if fresh.empty or fresh.date_ny.min()<=CUTOFF or fresh.date_ny.duplicated().any():
        raise ValueError("missing, overlapping or duplicate fresh data")
    p=pd.concat([old,fresh],ignore_index=True).sort_values("date_ny").reset_index(drop=True)
    q60=p.close_qqq.pct_change(60)
    x5=p.close_qld.pct_change(5)
    features=signal_features(p)
    p=p.join(features.drop(columns="date_ny"))
    p["qqq60"]=q60
    p["qld5"]=x5
    p["regime"]=np.select([q60>=.08,q60<=-.08],["UP","DOWN"],default="SIDE")
    p["up_regime"]=q60>=.08
    p["down_regime"]=q60<=-.08
    p["qld5_dip"]=x5<=-.03
    p["qld5_rally"]=x5>=.03
    p["up_dip_raw"]=p.up_regime&p.qld5_dip
    p["down_rally_raw"]=p.down_regime&p.qld5_rally
    last=p[p.date_ny>CUTOFF].copy()
    # Four full sessions are required AFTER the signal for horizon-complete outcomes.
    available_last_date=str(p.date_ny.iloc[-5]) if len(p)>=5 else None
    last["horizon_complete"]=last.date_ny<=available_last_date
    actual,_=proxy_events(p)
    new=actual[actual.date>CUTOFF]
    counts=last.regime.value_counts().to_dict()
    summary={
        "status":"SIGNAL_SCARCITY_DIAGNOSTIC_NOT_RULE_PROMOTION",
        "new_days":len(last),"first_new_date":str(last.date_ny.min()),
        "last_new_date":str(last.date_ny.max()),
        "up_regime_days":int(counts.get("UP",0)),
        "down_regime_days":int(counts.get("DOWN",0)),
        "side_regime_days":int(counts.get("SIDE",0)),
        "qld5_dip_days":int(last.qld5_dip.sum()),
        "qld5_rally_days":int(last.qld5_rally.sum()),
        "up_dip_raw_days":int(last.up_dip_raw.sum()),
        "down_rally_raw_days":int(last.down_rally_raw.sum()),
        "up_dip_raw_horizon_complete":int((last.up_dip_raw&last.horizon_complete).sum()),
        "down_rally_raw_horizon_complete":int((last.down_rally_raw&last.horizon_complete).sum()),
        "selected_completed_trades":len(new),
        "horizon_complete_days":int(last.horizon_complete.sum()),
        "pending_horizon_days":int((~last.horizon_complete).sum()),
        "qqq60_min":float(last.qqq60.min()),
        "qqq60_max":float(last.qqq60.max()),
        "qld5_min":float(last.qld5.min()),
        "qld5_max":float(last.qld5.max()),
        "rsi_rising_days":int(last.RSI_RISING.sum()),
        "macd_rising_days":int(last.MACD_RISING.sum()),
        "both_rising_days":int(last.RSI_AND_MACD_RISING.sum()),
        "price_only":True,"promotion_allowed":False
    }
    return last,summary

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--history",default="research/regime_countertrend/data/QLD_QQQ_daily_alignment.csv")
    p.add_argument("--appended",default="results/regime_countertrend/fresh_oos/paired_public_daily_prices.csv")
    p.add_argument("--out",default="results/regime_countertrend/signal_scarcity")
    a=p.parse_args()
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    if not Path(a.appended).is_file():
        info={"status":"HOLD_NO_VALIDATED_FRESH_DAILY_DATA","promotion_allowed":False}
    else:
        days,info=diagnose(pd.read_csv(a.history),pd.read_csv(a.appended))
        days.to_csv(out/"daily_signal_components.csv",index=False)
    (out/"summary.json").write_text(json.dumps(info,indent=2))
    print("SIGNAL_SCARCITY",json.dumps(info))
if __name__=="__main__":main()
