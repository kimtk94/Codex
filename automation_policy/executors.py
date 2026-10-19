"""Explicitly allowlisted CI-only executors. No network or production actions."""
import json
from pathlib import Path

def run_qc(workdir: Path) -> dict:
    """Validate checked-in plan and policy consistency; real deterministic QC."""
    from .plan import Step, validate
    spec = json.loads((Path(__file__).parent / "plan_example.json").read_text(encoding="utf-8"))
    if spec.get("mode") != "plan_only":
        raise ValueError("unexpected_mode")
    steps = [Step(s["id"], s["action"], tuple(s.get("needs", []))) for s in spec["steps"]]
    order = validate(steps)
    if any(s["executor"] != "not_connected" for s in spec["steps"]):
        raise ValueError("unexpected_business_executor")
    evidence = {"check": "plan_policy_integrity", "valid": True, "ordered_ids": order}
    (workdir / "qc-evidence.json").write_text(json.dumps(evidence, indent=2)+"\n")
    return evidence

def create_qc_report(workdir: Path) -> dict:
    """Generate a report only from previously verified QC evidence."""
    evidence_path = workdir / "qc-evidence.json"
    evidence = json.loads(evidence_path.read_text())
    if evidence.get("valid") is not True or evidence.get("check") != "plan_policy_integrity":
        raise ValueError("unverified_qc")
    text = "# Harness CI QC Report\n\nPolicy/plan consistency: PASS\n\n"
    text += "Verified plan tasks: " + ", ".join(evidence["ordered_ids"]) + "\n\n"
    text += "This report does not represent an IS/CKD biological analysis or Kalman backtest.\n"
    (workdir / "qc-report.md").write_text(text)
    return {"report": "qc-report.md", "verified_input": True}

EXECUTORS = {"plan-policy-integrity": run_qc, "qc-report": create_qc_report}
