"""Produce a bounded, actionable next-step report without remote side effects."""
import json
from pathlib import Path
from .plan import Step, ready, validate

def run():
    spec=json.loads((Path(__file__).parent/"plan_example.json").read_text())
    steps=[Step(s["id"],s["action"],tuple(s.get("needs",[]))) for s in spec["steps"]]
    order=validate(steps)
    report={"mode":"plan_only","execution_performed":False,"ready":ready(steps,set()),
            "blocked":[],"waiting":[],"order":order,"next_actions":[]}
    for step in spec["steps"]:
        if step.get("executor")!="not_connected":
            raise ValueError("unexpected_executor_configuration")
        report["blocked"].append({"id":step["id"],"reason":"EXECUTOR_NOT_CONNECTED"})
        report["next_actions"].append({"id":step["id"],"requirement":"Connect and independently verify a read-only executor"})
    Path("artifacts").mkdir(exist_ok=True)
    Path("artifacts/harness-next-actions.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report,indent=2))
if __name__=="__main__":
    run()
