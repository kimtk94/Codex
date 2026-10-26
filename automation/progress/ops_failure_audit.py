"""Read-only failure detection and recovery candidates, not a notification receipt."""
import json
from pathlib import Path

def classify(runs):
    ordered=sorted((r for r in runs if r.get("event")=="schedule" and r.get("status")=="completed"),key=lambda x:x.get("created_at") or "")
    failed=[r for r in ordered if r.get("conclusion") in {"failure","timed_out","cancelled"}]
    incidents=[]
    for r in failed:
        later=[s for s in ordered if (s.get("created_at") or "")>(r.get("created_at") or "") and s.get("conclusion")=="success"]
        incidents.append({"failed_run_id":r.get("id"),"recovery_run_id":later[0].get("id") if later else None,
                          "state":"FOLLOWED_BY_SUCCESS" if later else "UNRESOLVED"})
    return incidents

def make_report(workflows):
    incidents={k:classify(v) for k,v in workflows.items()}
    return {"incidents_by_workflow":incidents,"alert_delivery":"NOT_VERIFIED",
            "failure_injection":"NOT_VERIFIED",
            "recovery_test":"NOT_VERIFIED",
            "note":"A later successful run is a recovery candidate, not proof of notification receipt or state restoration"}

def main():
    # Static dry-run: live observation belongs to ops_live_collector.
    report=make_report({})
    out=Path("progress-audit/ops-failure-audit.json")
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report,indent=2))
    print("OPS_FAILURE_AUDIT_BASELINE",report["alert_delivery"])

if __name__=="__main__":
    main()
