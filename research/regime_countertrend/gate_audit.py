"""Audit a prespecified MA20 gate by era; no strategy promotion or model fitting."""
import argparse,json
from pathlib import Path
import pandas as pd

def compare(trades):
    need={"year","net_return","failed","ma20dist","event"}
    missing=need-set(trades.columns)
    if missing:raise ValueError("missing columns: "+str(sorted(missing)))
    d=trades.copy()
    d["keep"]=d.ma20dist>=0
    d["era"]=d.year.map(lambda y: "HOLDOUT_2025_26" if 2025<=int(y)<=2026 else ("DEVELOPMENT_PRE2025" if int(y)<2025 else "POST_2026"))
    rows=[]
    for era in ["DEVELOPMENT_PRE2025","HOLDOUT_2025_26"]:
        for event in ["ALL","UP_DIP","DOWN_RALLY"]:
            z=d[d.era==era]
            if event!="ALL":z=z[z.event==event]
            for strategy,subset in [("BASELINE",z),("MA20_GATE",z[z.keep])]:
                rows.append({"era":era,"event":event,"strategy":strategy,"trades":len(subset),"avg_net_return":float(subset.net_return.mean()) if len(subset) else None,"loss_rate":float(subset.failed.mean()) if len(subset) else None,"sum_trade_returns_not_portfolio":float(subset.net_return.sum())})
    t=pd.DataFrame(rows)
    hold=t[(t.era=="HOLDOUT_2025_26")&(t.event=="ALL")]
    base=hold[hold.strategy=="BASELINE"].iloc[0]
    gate=hold[hold.strategy=="MA20_GATE"].iloc[0]
    verdict="HOLD" if gate.trades<10 or gate.avg_net_return is None or gate.avg_net_return<=base.avg_net_return else "FURTHER_VALIDATION_REQUIRED"
    return t,{"status":verdict,"holdout_baseline_n":int(base.trades),"holdout_gate_n":int(gate.trades),"warning":"Non-executable daily-bar proxy. Small holdout; no independent alpha confirmation, overlap and costs beyond flat 20bps not fully tested."}
def main():
    p=argparse.ArgumentParser();p.add_argument("--csv",required=True);p.add_argument("--out",default="results/regime_countertrend/gate");a=p.parse_args()
    table,summary=compare(pd.read_csv(a.csv))
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    table.to_csv(out/"era_comparison.csv",index=False)
    (out/"decision.json").write_text(json.dumps(summary,indent=2))
    print(json.dumps(summary,indent=2))
if __name__=="__main__":main()
