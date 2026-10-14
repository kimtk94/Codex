#!/usr/bin/env python3
"""Read-only diagnostics for preliminary fixed-grid results (NOT a trading signal)."""
import argparse, json
from pathlib import Path
import numpy as np
import pandas as pd

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--baseline-dir",default="~/ETH_REGIME_RESEARCH_20261014/baseline")
    p.add_argument("--out",default="~/ETH_REGIME_RESEARCH_20261014/baseline_audit.json")
    args=p.parse_args()
    base=Path(args.baseline_dir).expanduser()
    trades=pd.read_csv(base/"trades.csv")
    eq=pd.read_csv(base/"equity.csv")
    summary=json.loads((base/"summary.json").read_text())
    eq["ts"]=pd.to_datetime(eq.ts,utc=True)
    trades["ts"]=pd.to_datetime(trades.ts,utc=True) if len(trades) else pd.to_datetime([])
    qty=0.0
    invested_cost=0.0
    sells=0
    buys=0
    realized=0.0
    negatives=0
    batches=[]
    exposure_events=[]
    for row in trades.itertuples(index=False):
        q=float(row.quantity)
        if row.side=="BUY":
            buys+=1
            before=float(row.cash)+10000.0
            cost=before-float(row.cash)
            qty+=q
            invested_cost+=cost
        elif row.side=="SELL":
            sells+=1
            if q>qty+1e-8: raise ValueError("SELL quantity exceeds tracked inventory")
            proceeds=float(row.cash)-prev_cash
            cost=invested_cost*q/qty if qty>0 else 0
            pnl=proceeds-cost
            realized+=pnl
            negatives+=int(pnl<0)
            batches.append(dict(exit=str(row.ts),qty=q,realized_net_pnl=pnl))
            invested_cost-=cost
            qty-=q
            if abs(qty)<1e-9:qty=0.0;invested_cost=0.0
        else:raise ValueError("Unknown side: "+str(row.side))
        prev_cash=float(row.cash)
        exposure_events.append((row.ts, qty, invested_cost))
    # This is cost-basis exposure, not mark-to-market exposure.
    event=pd.DataFrame(exposure_events,columns=["ts","qty","invested_cost"])
    if len(event):
        joined=pd.merge_asof(eq.sort_values("ts"),event.sort_values("ts"),on="ts",direction="backward")
        joined[["qty","invested_cost"]]=joined[["qty","invested_cost"]].fillna(0)
    else:
        joined=eq.copy()
        joined["qty"]=0.0
        joined["invested_cost"]=0.0
    initial=1000000.0 # default from original baseline; recover from summary if later recorded
    if trades.empty:
        initial=float(summary.get("initial_krw",initial))
    else:
        first=trades.iloc[0]
        if first.side=="BUY":
            initial=float(first.cash)+10000.0
    stats={
      "baseline_net_return":summary.get("net_return"),
      "baseline_mdd":summary.get("mdd"),
      "bars":len(eq),
      "buy_count":buys,
      "sell_count":sells,
      "open_inventory_qty":qty,
      "open_cost_basis_krw":round(invested_cost,2),
      "closed_net_pnl_krw":round(realized,2),
      "negative_exit_batches":negatives,
      "mean_cost_basis_exposure_pct":round(100*joined.invested_cost.mean()/initial,4),
      "max_cost_basis_exposure_pct":round(100*joined.invested_cost.max()/initial,4),
      "flat_bar_share":round(float((joined.qty==0).mean()),6),
      "warnings":["Buy order size assumed 10000 KRW from baseline invocation.",
       "No exchange order-book queue, latency, limit-tick rounding, or same-minute path.",
       "Intrabar fills remain approximations, not observed fills.",
       "Costs and exposure are reconstructed from trade log; verify against original portfolio ledger."]
    }
    dest=Path(args.out).expanduser()
    dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(stats,indent=2,ensure_ascii=False))
    print(json.dumps(stats,indent=2,ensure_ascii=False))
if __name__=="__main__":main()
