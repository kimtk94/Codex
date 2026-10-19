"""CI-only, side-effect-free Harness smoke run producing JSON evidence."""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from .queue import Queue, Task

def main():
    q = Queue()
    tasks = [
        Task("research-smoke", "research.analysis_qc"),
        Task("docs-smoke", "research.docs_web_update"),
        Task("backtest-smoke", "kalman.backtest"),
        Task("live-order-deny", "kalman.live_order"),
        Task("db-schema-deny", "database.schema_change"),
        Task("customer-mail-deny", "css.email_send"),
    ]
    for task in tasks:
        q.add(task)
        decision = q.claim(task.task_id)
        if decision["claimed"]:
            # In-memory smoke verifier ONLY; not a real business-task executor.
            q.result(task.task_id, execution_ok=True, verified=True)
    report = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "kind": "isolated_policy_smoke_only",
        "commit_sha": os.environ.get("GITHUB_SHA", "local"),
        "tasks": [{"id":t.task_id,"action":t.action,"state":t.state,"attempts":t.attempts} for t in tasks],
    }
    output = Path("artifacts/automation-policy-smoke.json")
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    expected = ["DONE","DONE","DONE","BLOCKED_EXTERNAL","BLOCKED_EXTERNAL","BLOCKED_EXTERNAL"]
    actual = [t.state for t in tasks]
    print(json.dumps(report,indent=2))
    return 0 if actual == expected else 1

if __name__ == "__main__":
    sys.exit(main())
