"""Descriptive Triple Barrier outcomes for every daily bar, NOT a trading strategy.

Labels every eligible day independently (overlap is expected); does not report
portfolio returns, win rates of an actual strategy, or model predictions.
"""
import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from triple_barrier_reference import triple_barrier

def labels(csv_path):
    with Path(csv_path).open(newline="",encoding="utf-8-sig") as f:
        records=list(csv.DictReader(f))
    output={"schema_version":1,"mode":"DESCRIPTIVE_OVERLAPPING_EVENT_LABELS_ONLY",
            "source":Path(csv_path).name,"records":len(records),"symbols":{}}
    for symbol in ("QQQ","QLD"):
        bars=[{k:float(r[f"{k}_{symbol.lower()}"]) for k in ("open","high","low","close")} for r in records]
        counters=Counter()
        gross=[]
        for i in range(len(bars)-4):
            x=triple_barrier(bars,i)
            counters[x["reason"]]+=1
            counters["BOTH_TOUCHED_SAME_BAR"]+=int(x["simultaneous_barrier"])
            gross.append(x["gross_return"])
        output["symbols"][symbol]={"events":len(gross),"labels":dict(counters),
          "mean_event_gross_return":sum(gross)/len(gross) if gross else None}
    output["warning"]="Overlapping labels enter on every day with full hindsight; returns are NOT a feasible strategy, portfolio ROI or OOS assessment. No signals, fees or slippage used."
    return output

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--input",required=True)
    p.add_argument("--output")
    a=p.parse_args()
    result=labels(a.input)
    text=json.dumps(result,ensure_ascii=False,indent=2)
    if a.output:Path(a.output).write_text(text+"\n",encoding="utf-8")
    print(text)
