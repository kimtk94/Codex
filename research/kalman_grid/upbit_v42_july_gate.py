"""Read-only July maintenance-aware data gate, BTC and ETH."""
import argparse,json,csv
from pathlib import Path
from upbit_data_audit_v28 import audit
from upbit_maintenance_v42 import gap_audit
def validate(path,market):
    q=audit(path,1,"2026-07-01T00:00:00Z","2026-07-31T23:59:00Z")
    g=gap_audit(path,market)
    remaining_expected=q["expected"]-g["approved_maintenance_missing_minutes"]
    adjusted_coverage=(q["rows"]/remaining_expected if remaining_expected>0 else 0)
    valid=(g["approved_maintenance_missing_minutes"]==290 and
           q["rows"]<=remaining_expected and adjusted_coverage>=.99 and
           g["max_nonmaintenance_gap_minutes"]<=5 and
           q["start"]=="2026-07-01T00:00:00+00:00" and
           q["end"]=="2026-07-31T23:59:00+00:00")
    # Base BLOCKED is expected due known outage; do not lower its threshold.
    return {"market":market,"status":"PASS_WITH_DOCUMENTED_MAINTENANCE" if valid else "BLOCKED_DATA_QUALITY",
            "raw_status":q["status"],"adjusted_coverage_pct":round(adjusted_coverage*100,3),
            "data":q,"gaps":g}
def main():
    p=argparse.ArgumentParser();p.add_argument("--input-dir",required=True)
    p.add_argument("--output",required=True);a=p.parse_args()
    results=[validate(Path(a.input_dir)/f"{market}_1m_history.csv",market) for market in ("KRW-BTC","KRW-ETH")]
    dest=Path(a.output);dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(results,indent=2))
    print(json.dumps([{"market":r["market"],"status":r["status"],"adjusted_coverage_pct":r["adjusted_coverage_pct"]} for r in results]))
    if any(r["status"]!="PASS_WITH_DOCUMENTED_MAINTENANCE" for r in results):raise SystemExit(2)
if __name__=="__main__":main()
