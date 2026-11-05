"""Read-only reconciliation gate for Kalman Neon *mirror* trades.

The database mirror is NOT an authoritative broker fill record. No promotion to
LIVE or publish of raw fill/order identifiers is permitted from this module.
"""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

REQUIRED = {
    "symbol", "state", "entry_average_price", "exit_average_price",
    "net_return", "round_trip_cost_bps", "entry_order_id",
    "exit_order_id", "exit_reason"
}

def audit(df, gross_net_tolerance_bps=5):
    missing = REQUIRED - set(df.columns)
    if missing:
        raise ValueError("missing required mirror fields: " + ", ".join(sorted(missing)))
    d = df.copy()
    d = d[d.state == "CLOSED"].copy()
    if d.empty:
        return pd.DataFrame(), {"status":"HOLD_NO_CLOSED_TRADES","mirror_count":0,
                                "promotion_allowed":False}
    for col in ("entry_average_price","exit_average_price","net_return","round_trip_cost_bps"):
        d[col] = pd.to_numeric(d[col],errors="coerce")
    valid=(d.entry_average_price>0)&(d.exit_average_price>0)
    d["gross_price_return"] = np.where(
        valid,d.exit_average_price/d.entry_average_price-1,np.nan)
    d["price_down"] = d.gross_price_return < 0
    d["missing_order_link"] = d.entry_order_id.isna() | d.exit_order_id.isna()
    d["missing_net"] = d.net_return.isna()
    d["metadata_net_exceeds_gross"] = (
        d.net_return.notna()&d.gross_price_return.notna()&
        (d.net_return>d.gross_price_return+gross_net_tolerance_bps/10000))
    d["gross_net_discrepancy_gt_1pct"] = (
        d.net_return.notna()&d.gross_price_return.notna()&
        ((d.net_return-d.gross_price_return).abs()>.01))
    d["net_positive_while_price_down"] = d.price_down & (d.net_return>=0)
    d["expected_net_using_recorded_cost"] = (
        d.gross_price_return-d.round_trip_cost_bps/10000)
    d["net_inconsistent_with_recorded_cost"] = (
        d.net_return.notna()&d.expected_net_using_recorded_cost.notna()&
        ((d.net_return-d.expected_net_using_recorded_cost).abs()>
         gross_net_tolerance_bps/10000))
    groups=d.groupby(d.exit_reason.fillna("MISSING"),dropna=False).agg(
        positions=("symbol","size"),
        price_down=("price_down","sum"),
        net_missing=("missing_net","sum"),
        net_exceeds_gross=("metadata_net_exceeds_gross","sum"),
        mean_gross=("gross_price_return","mean")).reset_index()
    groups=groups.rename(columns={"exit_reason":"reason"})
    total={
        "status":"HOLD_MIRROR_NOT_BROKER_RECONCILED",
        "source":"NEON_MIRROR_NOT_INDEPENDENT_BROKER_RECORD",
        "mirror_count":int(len(d)),
        "price_valid":int(valid.sum()),
        "price_down":int(d.price_down.sum()),
        "net_available":int(d.net_return.notna().sum()),
        "net_negative":int((d.net_return<0).sum()),
        "missing_links":int(d.missing_order_link.sum()),
        "missing_net":int(d.missing_net.sum()),
        "net_exceeds_gross":int(d.metadata_net_exceeds_gross.sum()),
        "gross_net_discrepancy_gt_1pct":int(d.gross_net_discrepancy_gt_1pct.sum()),
        "down_with_positive_net":int(d.net_positive_while_price_down.sum()),
        "net_cost_mismatch":int(d.net_inconsistent_with_recorded_cost.sum()),
        "avg_gross_pct":float(d.gross_price_return.mean()*100),
        "avg_metadata_net_pct":float(d.net_return.mean()*100),
        "profit_to_loss_flip_n":int((d.exit_reason=="PROFIT_TO_LOSS_FLIP").sum()),
        "profit_to_loss_flip_price_down":int(((d.exit_reason=="PROFIT_TO_LOSS_FLIP")&d.price_down).sum()),
        "promotion_allowed":False,
        "limitations":["Assumes long positions for price-return sign; validate side with broker",
           "The stored net_return may be defined inconsistently; no silent unit conversion",
           "No independently attested broker IDs, fees, fill timestamps or 15m path",
           "This is an audit of a mirrored state, not verified realized PnL"],
    }
    return groups,total

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--csv",required=True,help="PRIVATE export from a read-only mirror view, never commit")
    p.add_argument("--out",default="results/regime_countertrend/mirror_audit")
    args=p.parse_args()
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    groups,summary=audit(pd.read_csv(args.csv))
    groups.to_csv(out/"reasons_aggregate.csv",index=False)
    (out/"gate.json").write_text(json.dumps(summary,indent=2,ensure_ascii=False))
    print(json.dumps(summary,ensure_ascii=False))
if __name__=="__main__":
    main()
