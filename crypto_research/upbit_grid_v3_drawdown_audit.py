#!/usr/bin/env python3
"""Read-only diagnostics of grid v3 equity curve, drawdown and inventory saturation."""
import argparse,json
from pathlib import Path
import pandas as pd

def streaks(mask,ts):
    group=(mask!=mask.shift(fill_value=False)).cumsum()
    out=[]
    for _,part in pd.DataFrame({"on":mask,"ts":ts,"g":group}).groupby("g",sort=False):
        if not bool(part.on.iloc[0]):continue
        out.append({"start":str(part.ts.iloc[0]),"end":str(part.ts.iloc[-1]),
                    "observed_bars":int(len(part)),
                    "elapsed_hours":round((part.ts.iloc[-1]-part.ts.iloc[0]).total_seconds()/3600,3)})
    return sorted(out,key=lambda x:x["elapsed_hours"],reverse=True)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--dir",default="~/ETH_REGIME_RESEARCH_20261014/grid_v3")
    p.add_argument("--out",default="~/ETH_REGIME_RESEARCH_20261014/v3_risk_deep_audit.json")
    a=p.parse_args();folder=Path(a.dir).expanduser()
    s=json.loads((folder/"summary.json").read_text())
    e=pd.read_csv(folder/"equity.csv",parse_dates=["ts"])
    t=pd.read_csv(folder/"trades.csv",parse_dates=["ts"])
    capital=float(s["initial_krw"]);e=e.sort_values("ts")
    e["dd_pct"]=(e.equity_krw/e.equity_krw.cummax()-1)*100
    e["exposure_pct"]=100*e.capital_krw/capital
    e["month"]=e.ts.dt.strftime("%Y-%m")
    month=[]
    for m,g in e.groupby("month",sort=True):
        month.append({"month":m,"bars":len(g),"first_equity":round(float(g.equity_krw.iloc[0]),2),
            "last_equity":round(float(g.equity_krw.iloc[-1]),2),
            "month_change_krw":round(float(g.equity_krw.iloc[-1]-g.equity_krw.iloc[0]),2),
            "min_drawdown_from_prior_peak_pct":round(float(g.dd_pct.min()),3),
            "at_cap_pct_of_bars":round(float((g.exposure_pct>=29.999).mean()*100),2),
            "mean_lots":round(float(g.open_lots.mean()),2)})
    peak_index=e.equity_krw.idxmax()
    last=e.iloc[-1]
    cap=(e.exposure_pct>=29.999)
    sell=t[t.side=="SELL"].copy()
    sell["month"]=sell.ts.dt.strftime("%Y-%m")
    sell_month=sell.groupby("month").net_pnl.agg(["size","sum"]).round(2).to_dict(orient="index")
    result={"source":"v3 local saved outputs, not market execution records",
      "overall":s,
      "max_equity_krw":round(float(e.loc[peak_index,"equity_krw"]),2),
      "max_equity_ts":str(e.loc[peak_index,"ts"]),
      "last_equity_krw":round(float(last.equity_krw),2),
      "drawdown_from_peak_at_end_pct":round((float(last.equity_krw)/float(e.equity_krw.max())-1)*100,3),
      "max_cap_streaks_top5":streaks(cap,e.ts)[:5],
      "monthly":month,"monthly_realized_exit_pnl":sell_month,
      "limitations":"No forced liquidation or trading fees on terminal inventory; duration measured by timestamps even if missing bars; does not demonstrate live fill quality."}
    out=Path(a.out).expanduser();out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2,default=str))
    print(json.dumps({k:v for k,v in result.items() if k!="overall"},ensure_ascii=False,indent=2,default=str))
if __name__=="__main__":main()
