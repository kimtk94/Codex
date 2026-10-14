#!/usr/bin/env python3
"""Read-only terminal liquidation audit for saved Upbit v3/v5 runs."""
import argparse,json,sqlite3
from pathlib import Path
import pandas as pd

def main():
 p=argparse.ArgumentParser()
 p.add_argument("--db",default="~/research/upbit_eth/krw_eth_1m.sqlite3")
 p.add_argument("--root",default="~/ETH_REGIME_RESEARCH_20261014")
 a=p.parse_args()
 root=Path(a.root).expanduser()
 runs=[
 ("v3_base","continuous_v3",5,2),("v5_base","continuous_v5_stop3",5,2),
 ("v3_mid","continuous_v3_fee10_slip5",10,5),
 ("v5_mid","continuous_v5_stop3_fee10_slip5",10,5),
 ("v3_high","continuous_v3_fee20_slip10",20,10),
 ("v5_high","continuous_v5_stop3_fee20_slip10",20,10)]
 db=sqlite3.connect(f"file:{Path(a.db).expanduser()}?mode=ro",uri=True)
 db.execute("PRAGMA query_only=ON")
 result=[]
 for label,folder,fee_bps,slip_bps in runs:
  path=root/folder
  if not (path/"summary.json").exists():
   result.append({"label":label,"status":"MISSING"});continue
  summ=json.loads((path/"summary.json").read_text())
  e=pd.read_csv(path/"equity.csv",usecols=["ts","equity_krw"])
  t=pd.read_csv(path/"trades.csv")
  last_ts=str(e.ts.iloc[-1]).replace(" ","T")
  if not last_ts.endswith("+00:00"): last_ts+="+00:00"
  row=db.execute("SELECT close FROM candles WHERE ts_utc=?",(last_ts,)).fetchone()
  if row is None:raise ValueError(f"last close unavailable for {label}: {last_ts}")
  close=float(row[0])
  held=0.0
  for tr in t.itertuples(index=False):
   held+=float(tr.qty)*(1 if tr.side=="BUY" else -1)
  if held<-1e-7:raise ValueError(f"negative inventory {label}")
  held=max(0.0,held)
  equity=float(e.equity_krw.iloc[-1])
  fee=fee_bps/10000;slip=slip_bps/10000
  liquidated=equity-held*close+held*close*(1-slip)*(1-fee)
  result.append(dict(label=label,status="OK",final_price_krw=close,held_eth=round(held,9),
   marked_equity_krw=round(equity,2),terminal_liquidation_equity_krw=round(liquidated,2),
   liquidation_penalty_krw=round(equity-liquidated,2),net_return_after_liquidation_pct=round(100*(liquidated/1000000-1),4)))
 db.close()
 print(json.dumps({"comparison":result,"warning":"Liquidation at final close with assumed adverse slippage and fee; not executable bid/market depth, and does not model end-of-data forced exit path."},ensure_ascii=False,indent=2))
if __name__=="__main__":main()
