#!/usr/bin/env python3
"""Audit saved grid v3 fills and equity, never touch source SQLite."""
import argparse,json
from pathlib import Path
import pandas as pd
def main():
 p=argparse.ArgumentParser()
 p.add_argument("--dir",default="~/ETH_REGIME_RESEARCH_20261014/grid_v3")
 a=p.parse_args();root=Path(a.dir).expanduser()
 t=pd.read_csv(root/"trades.csv");e=pd.read_csv(root/"equity.csv")
 summary=json.loads((root/"summary.json").read_text())
 initial=float(summary["initial_krw"])
 buys=t[t.side=="BUY"];sells=t[t.side=="SELL"]
 pnl=pd.to_numeric(sells.net_pnl,errors="coerce")
 e["ts"]=pd.to_datetime(e.ts,utc=True)
 e["exposure_pct"]=e.capital_krw/initial*100
 e["daily"]=e.ts.dt.strftime("%Y-%m-%d")
 e["month"]=e.ts.dt.strftime("%Y-%m")
 monthly=e.groupby("month").agg(start_equity=("equity_krw","first"),end_equity=("equity_krw","last"),max_exposure_pct=("exposure_pct","max"),mean_exposure_pct=("exposure_pct","mean"))
 monthly["return_pct"]=(monthly.end_equity/monthly.start_equity-1)*100
 print("EXIT_STATS",json.dumps({"profitable":int((pnl>0).sum()),"lossmaking":int((pnl<0).sum()),"zero":int((pnl==0).sum()),"worst_exit_pnl_krw":float(pnl.min()),"best_exit_pnl_krw":float(pnl.max()),"sum_exit_pnl_krw":float(pnl.sum()),"max_exposure_bars":int((e.exposure_pct>=29.999).sum()),"max_exposure_pct_of_bars":round(float((e.exposure_pct>=29.999).mean()*100),3),"flat_pct_of_bars":round(float((e.open_lots==0).mean()*100),3),"max_open_lots":int(e.open_lots.max()),"last_open_lots":int(e.open_lots.iloc[-1]),"cash_min_krw":float(e.cash_krw.min())},ensure_ascii=False))
 print("MONTHLY",monthly.round(4).to_json(orient="index"))
 print("CAUTION: outputs describe filled market proxies, not exchange fills or passive-limit grid.")
if __name__=="__main__":main()
