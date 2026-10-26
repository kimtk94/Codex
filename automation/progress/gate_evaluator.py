"""Read-only gate evaluation: never infer acceptance from CI/PR alone."""
import json
from pathlib import Path

MANIFEST = Path("automation/progress/acceptance_manifest.json")

def evaluate(manifest, signed_records):
    """Return per-gate verdict. Require complete explicit signed evidence per task."""
    verdicts = []
    for gate_id, gate in manifest["gates"].items():
        required = set(gate["required"])
        missing = []
        for task_id in gate["tasks"]:
            rec = signed_records.get(task_id)
            if not isinstance(rec, dict) or rec.get("gate_id") != gate_id:
                missing.append({"task_id":task_id, "reason":"NO_SIGNED_TASK_RECORD"})
                continue
            if rec.get("decision") != "ACCEPTED" or not rec.get("reviewer") or not rec.get("reviewed_at"):
                missing.append({"task_id":task_id, "reason":"NO_EXPLICIT_REVIEW_APPROVAL"})
                continue
            evidence = rec.get("evidence")
            if not isinstance(evidence, dict) or any(not evidence.get(field) for field in required):
                missing.append({"task_id":task_id, "reason":"INCOMPLETE_REQUIRED_EVIDENCE"})
        verdicts.append({"gate_id":gate_id,"task_count":len(gate["tasks"]),
                         "state":"ACCEPTED" if not missing else "NOT_VERIFIED",
                         "missing":missing})
    return verdicts

def main():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    # No signed acceptance ledger has been authorized yet. Candidate PRs are deliberately excluded.
    verdicts = evaluate(manifest, {})
    folder = Path("progress-audit")
    folder.mkdir(exist_ok=True)
    (folder/"gate-summary.json").write_text(json.dumps(verdicts,indent=2),encoding="utf-8")
    print("GATE_AUDIT_OK",len(verdicts),"accepted",sum(x["state"]=="ACCEPTED" for x in verdicts))

if __name__ == "__main__":
    main()
