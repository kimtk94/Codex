"""Validate read-only AGGREGATE Neon mirror observations (not broker records).

This gate never reads private order identifiers or provides a LIVE strategy permit.
"""
import argparse
import json
from pathlib import Path

def audit(report):
    totals=report["closed_positions"]
    reasons=report["exit_reason_price_loss_counts"]
    gross=report["gross_price_returns_assume_long"]
    issues=report["reconciliation_issues"]
    net=report["metadata_net_return"]
    if len({r["reason"] for r in reasons})!=len(reasons):
        raise ValueError("duplicate exit reasons")
    if sum(r["count"] for r in reasons)!=totals:
        raise ValueError("exit reason counts do not reconcile to closed positions")
    if sum(r["price_down"] for r in reasons)!=gross["negative"]:
        raise ValueError("price-down counts do not reconcile")
    if gross["negative"]+gross["positive_or_zero"]!=totals:
        raise ValueError("price returns do not reconcile")
    if net["available"]+issues["missing_net_return"]!=totals:
        raise ValueError("stored net-return coverage does not reconcile")
    if net["max_pct"]<gross["max_pct"] and issues["net_return_exceeds_gross_price_return_by_more_than_1bp"]>0:
        # Not impossible, but do not silently accept incompatible definitions.
        raise ValueError("stored return summary needs manual review")
    flip=next((r for r in reasons if r["reason"]=="PROFIT_TO_LOSS_FLIP"),None)
    stop=next((r for r in reasons if r["reason"]=="STOP_LOSS_3PCT"),None)
    if flip is None or stop is None:
        raise ValueError("critical exit types missing")
    nloss=gross["negative"]
    return {
        "status":"HOLD_MIRRORED_PNL_NOT_BROKER_RECONCILED",
        "source_as_of":report["data_cutoff"],
        "closed_positions":totals,
        "observed_price_down_positions":nloss,
        "observed_price_down_pct":round(100*nloss/totals,2),
        "flip_exit_reason_count":flip["count"],
        "flip_exit_reason_price_down":flip["price_down"],
        "flip_share_of_price_down_pct":round(100*flip["price_down"]/nloss,2) if nloss else None,
        "stop_exit_reason_count":stop["count"],
        "stop_exit_reason_price_down":stop["price_down"],
        "metadata_net_coverage":net["available"],
        "unreconciled_net_return_gt_gross_count":
            issues["net_return_exceeds_gross_price_return_by_more_than_1bp"],
        "unreconciled_price_down_metadata_net_positive_count":
            issues["price_loss_but_positive_metadata_net"],
        "missing_entry_exit_order_link_count":
            issues["missing_entry_or_exit_order_link"],
        "metadata_net_max_percent":net["max_pct"],
        "price_gross_max_percent":gross["max_pct"],
        "profit_flip_confirmed_from_intraday":False,
        "return_definition_verified":False,
        "broker_execution_verified":False,
        "promotion_allowed":False,
        "next_checks":[
            "Confirm what metadata.net_return represents (units, cost basis, leveraged denominator)",
            "Independently reconcile entry/exit quantities, actual fee currency and broker fill timestamps",
            "Match broker entry/exit timestamps to 15m price paths before MFE/MAE claims",
        ]
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--source",default="research/regime_countertrend/reports/neon_mirror_audit_20261102.json")
    p.add_argument("--out",default="results/regime_countertrend/mirror_snapshot")
    a=p.parse_args()
    result=audit(json.loads(Path(a.source).read_text()))
    path=Path(a.out);path.mkdir(parents=True,exist_ok=True)
    (path/"decision.json").write_text(json.dumps(result,indent=2))
    print(json.dumps(result))
if __name__=="__main__":main()
