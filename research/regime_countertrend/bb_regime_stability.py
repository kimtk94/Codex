"""Regime-conditioned Bollinger stability audit; never promotes a LIVE filter.

Uses completed, fixed-close proxy trades. The development period is <=2024
and the 2025-2026 period is a locked out-of-sample diagnostic.
"""
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import fisher_exact

REQUIRED = {"date", "year", "event", "failed", "net_return", "bb_pct_b"}
EVENTS = ("ALL", "UP_DIP", "DOWN_RALLY")
ERAS = ("DEVELOPMENT_PRE2025", "HOLDOUT_2025_2026")
FIXED_SPLIT = 0.5

def audit(trades):
    missing = REQUIRED - set(trades.columns)
    if missing:
        raise ValueError("missing fields: " + ",".join(sorted(missing)))
    d = trades.copy()
    d["date"] = pd.to_datetime(d.date, errors="raise")
    if d["date"].isna().any() or d.duplicated(["date","event"]).any():
        raise ValueError("missing/duplicate event identity")
    if d[["bb_pct_b","net_return"]].isna().any().any():
        raise ValueError("nonfinite indicator/return")
    if not set(d["failed"].dropna().unique()).issubset({True, False, 0, 1}):
        raise ValueError("failed column must be boolean")
    d["failed"] = d["failed"].astype(bool)
    d["era"] = np.select([d.year <= 2024, d.year.between(2025,2026)],ERAS,default="OUTSIDE")
    d["bb_lower_half"] = d.bb_pct_b < FIXED_SPLIT
    rows = []
    for era in ERAS:
        e = d[d.era == era]
        for event in EVENTS:
            sample = e if event == "ALL" else e[e.event == event]
            low = sample[sample.bb_lower_half]
            high = sample[~sample.bb_lower_half]
            def avg(z, col):
                return float(z[col].mean()) if len(z) else None
            pval = None
            if len(low) and len(high):
                pval = float(fisher_exact([[int(low.failed.sum()), len(low)-int(low.failed.sum())],
                                            [int(high.failed.sum()), len(high)-int(high.failed.sum())]])[1])
            rows.append({
                "era":era, "event":event, "all_n":len(sample),
                "lower_n":len(low),"lower_losses":int(low.failed.sum()),
                "upper_n":len(high),"upper_losses":int(high.failed.sum()),
                "lower_loss_rate":avg(low,"failed"),
                "upper_loss_rate":avg(high,"failed"),
                "lower_mean_net":avg(low,"net_return"),
                "upper_mean_net":avg(high,"net_return"),
                "fisher_two_sided_p":pval,
            })
    table = pd.DataFrame(rows)
    dev = table.query("era=='DEVELOPMENT_PRE2025' and event=='ALL'").iloc[0]
    hold = table.query("era=='HOLDOUT_2025_2026' and event=='ALL'").iloc[0]
    dev_gap = dev.lower_loss_rate-dev.upper_loss_rate
    hold_gap = hold.lower_loss_rate-hold.upper_loss_rate
    reversed_direction = bool(np.sign(dev_gap)!=np.sign(hold_gap)) if pd.notna(dev_gap) and pd.notna(hold_gap) else None
    decision = {
        "status":"HOLD",
        "threshold_predefined":FIXED_SPLIT,
        "development_n":int(dev.all_n),"holdout_n":int(hold.all_n),
        "failure_gap_lower_minus_upper_development":float(dev_gap),
        "failure_gap_lower_minus_upper_holdout":float(hold_gap),
        "direction_reversed":reversed_direction,
        "promotion_allowed":False,
        "reason":"Insufficient independent holdout sample; no stable out-of-sample effect established.",
        "limitations":["Research-only QLD daily-OHLC fills","No 15m execution or actual order logs",
          "Fisher p uncorrected for exploratory comparisons","No portfolio simulation or MDD claim",
          "2026 data frozen at 2026-09-04"],
    }
    return table,decision

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--trades",required=True)
    parser.add_argument("--out",default="results/regime_countertrend/stability")
    args=parser.parse_args()
    table,verdict=audit(pd.read_csv(args.trades))
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    table.to_csv(out/"bb_regime_comparison.csv",index=False)
    (out/"bb_verdict.json").write_text(json.dumps(verdict,indent=2,ensure_ascii=False))
    print(table.to_string(index=False))
    print(json.dumps(verdict,ensure_ascii=False))
