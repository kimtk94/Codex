"""Daily-OHLC failure diagnostics. Exploratory proxy, not LIVE trades."""
import argparse,json
from pathlib import Path
import numpy as np,pandas as pd
def run(data):
 d=data.sort_values("date_ny").reset_index(drop=True).copy()
 for c in ("open_qld","high_qld","low_qld","close_qld","close_qqq","volume_qld"):
  if c not in d: raise ValueError("missing "+c)
 d["qqq60"]=d.close_qqq.pct_change(60)
 d["qqq20"]=d.close_qqq.pct_change(20)
 d["qld5"]=d.close_qld.pct_change(5)
 d["rv20"]=d.close_qqq.pct_change().rolling(20).std()*np.sqrt(252)
 d["ma20dist"]=d.close_qqq/d.close_qqq.rolling(20).mean()-1
 d["volratio"]=d.volume_qld/d.volume_qld.shift(1).rolling(20).median()
 d["event"]=np.select([(d.qqq60>=.08)&(d.qld5<=-.03),(d.qqq60<=-.08)&(d.qld5>=.03)],["UP_DIP","DOWN_RALLY"],default="NONE")
 rows=[];last={}
 for i in range(60,len(d)-5):
  kind=d.at[i,"event"]
  if kind=="NONE" or i-last.get(kind,-999)<5:continue
  last[kind]=i
  entry=d.at[i+1,"open_qld"];tp=entry*1.03;sl=entry*.97
  outcome="TIME";exitprice=d.at[i+4,"close_qld"]
  for j in range(i+1,i+5):
   low,high=d.at[j,"low_qld"],d.at[j,"high_qld"]
   if low<=sl and high>=tp:outcome="AMBIGUOUS_BOTH";exitprice=sl;break
   if low<=sl:outcome="SL";exitprice=sl;break
   if high>=tp:outcome="TP";exitprice=tp;break
  net=exitprice/entry-1-.002
  rows.append(dict(date=d.at[i,"date_ny"],year=int(str(d.at[i,"date_ny"])[:4]),event=kind,outcome=outcome,net_return=net,failed=net<0,qqq20=d.at[i,"qqq20"],rv20=d.at[i,"rv20"],ma20dist=d.at[i,"ma20dist"],volratio=d.at[i,"volratio"]))
 out=pd.DataFrame(rows)
 return out,{"n":len(out),"failures":int(out.failed.sum()),"note":"Daily OHLC same-day dual barrier conservatively recorded as SL; no 15m fills, gaps, or execution slippage; 20bp flat round trip."}
if __name__=="__main__":
 ap=argparse.ArgumentParser();ap.add_argument("--csv",required=True);ap.add_argument("--out",default="results/regime_countertrend/failures");a=ap.parse_args()
 e,m=run(pd.read_csv(a.csv));p=Path(a.out);p.mkdir(parents=True,exist_ok=True);e.to_csv(p/"trades.csv",index=False);(p/"summary.json").write_text(json.dumps(m,indent=2));print(m)
