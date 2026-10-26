"""Ops-01 evidence assessment. Distinguish green PR CI from scheduled production success."""
import json
from pathlib import Path

REQUIRED = ("progress_audit", "evidence_publisher", "gate_gap_sync")

def assess(records, sheet_snapshot):
    checks = {}
    for key in REQUIRED:
        runs = records.get(key, [])
        scheduled = [r for r in runs if r.get("event") == "schedule" and r.get("conclusion") == "success"]
        checks[key] = {"pr_ci_success": any(r.get("event") == "pull_request" and r.get("conclusion") == "success" for r in runs),
                       "scheduled_success_count": len(scheduled),
                       "three_scheduled_successes": len({r.get("id") for r in scheduled}) >= 3}
    posted = sheet_snapshot.get("state") == "READ_OK" and bool(sheet_snapshot.get("verified_publish_receipt"))
    return {"task_A47": "CANDIDATE_EVIDENCE" if checks["progress_audit"]["pr_ci_success"] else "NOT_VERIFIED",
            "task_A48": "NOT_VERIFIED",
            "gate_OPS_01": "NOT_VERIFIED",
            "sheet_publish_readback": "OBSERVED" if posted else "NOT_OBSERVED",
            "workflow_checks": checks,
            "missing_requirements": [k for k,v in checks.items() if not v["three_scheduled_successes"]] +
              ([] if posted else ["sheet_publish_readback"]) + ["failure_injection","alert_receipt","explicit_review"],
            "note": "No acceptance promotion; scheduled runs and live Sheet readback must be independently verified"}

def main():
    # Only CI facts separately corroborated are allowed. No fake schedule runs.
    result=assess({}, {})
    dest=Path("progress-audit/ops01-evidence.json")
    dest.parent.mkdir(exist_ok=True)
    dest.write_text(json.dumps(result,indent=2))
    print("OPS01_EVIDENCE",result["gate_OPS_01"],result["sheet_publish_readback"])

if __name__ == "__main__":
    main()
