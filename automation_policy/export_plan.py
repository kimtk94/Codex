"""Export dependency plan evidence; no execution of business workflows."""
import json
from pathlib import Path
from .plan import Step, ready, validate

def main():
    spec = json.loads((Path(__file__).parent / "plan_example.json").read_text())
    if spec.get("mode") != "plan_only":
        raise ValueError("only_plan_mode_supported")
    if any(step.get("executor") != "not_connected" for step in spec["steps"]):
        raise ValueError("unexpected_executor")
    steps = [Step(s["id"], s["action"], tuple(s.get("needs", []))) for s in spec["steps"]]
    report = {"mode": "plan_only", "execution_performed": False,
              "topological_order": validate(steps), "ready_without_prior_results": ready(steps, set()),
              "steps": spec["steps"]}
    path = Path("artifacts/harness-plan.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))

if __name__ == "__main__":
    main()
