"""Run a fixed, side-effect-free two-step CI job with evidence checkpoints."""
import json
from pathlib import Path
from .gate import evaluate
from .executors import EXECUTORS

def main() -> None:
    out = Path("artifacts")
    out.mkdir(exist_ok=True)
    jobs = [
        {"id": "plan-policy-integrity", "action": "research.analysis_qc", "needs": []},
        {"id": "qc-report", "action": "research.docs_web_update", "needs": ["plan-policy-integrity"]},
    ]
    completed = set()
    results = []
    for job in jobs:
        if not all(dep in completed for dep in job["needs"]):
            raise RuntimeError("dependency_not_verified")
        if not evaluate(job["action"])["allowed"]:
            raise RuntimeError("policy_denied")
        # Hardcoded dispatch prevents untrusted job specifications from selecting arbitrary modules/commands.
        result = EXECUTORS[job["id"]](out)
        if job["id"] == "plan-policy-integrity" and result.get("valid") is not True:
            raise RuntimeError("qc_verification_failed")
        if job["id"] == "qc-report" and result.get("verified_input") is not True:
            raise RuntimeError("report_verification_failed")
        completed.add(job["id"])
        results.append({"id": job["id"], "state": "DONE", "evidence": result})
    (out / "executor-result.json").write_text(json.dumps({"kind": "actual_ci_plan_qc", "production_effects": False, "jobs": results}, indent=2)+"\n")
    print(json.dumps(results, indent=2))

if __name__ == "__main__":
    main()
