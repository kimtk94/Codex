"""Bounded in-process CI executor with fail-closed policy and verified dependencies."""
import json
from pathlib import Path
from .gate import evaluate
from .executors import EXECUTORS

JOBS = (
    {"id":"plan-policy-integrity","action":"research.analysis_qc","needs":()},
    {"id":"qc-report","action":"research.docs_web_update","needs":("plan-policy-integrity",)},
)

def execute(artifacts: Path, executors=None, max_attempts=2) -> dict:
    if max_attempts < 1 or max_attempts > 3:
        raise ValueError("invalid_retry_budget")
    executors = EXECUTORS if executors is None else executors
    artifacts.mkdir(parents=True,exist_ok=True)
    results={}
    for job in JOBS:
        name=job["id"]
        if any(results.get(dep,{}).get("state")!="DONE" for dep in job["needs"]):
            results[name]={"state":"BLOCKED_EXTERNAL","reason":"DEPENDENCY_NOT_VERIFIED","attempts":0}
            continue
        decision=evaluate(job["action"])
        if not decision["allowed"]:
            results[name]={"state":"BLOCKED_EXTERNAL","reason":decision["reason"],"attempts":0}
            continue
        if name not in executors:
            results[name]={"state":"BLOCKED_EXTERNAL","reason":"EXECUTOR_NOT_CONNECTED","attempts":0}
            continue
        result=None
        for attempt in range(1,max_attempts+1):
            try:
                evidence=executors[name](artifacts)
                if name=="plan-policy-integrity" and evidence.get("valid") is not True:
                    raise ValueError("QC_NOT_VERIFIED")
                if name=="qc-report" and evidence.get("verified_input") is not True:
                    raise ValueError("REPORT_NOT_VERIFIED")
                result={"state":"DONE","attempts":attempt,"evidence":evidence}
                break
            except Exception as exc:
                result={"state":"FAILED_TERMINAL" if attempt==max_attempts else "RETRY_WAIT",
                        "attempts":attempt,"reason":type(exc).__name__}
        results[name]=result
    report={"kind":"bounded_local_ci_execution","effects":"local_artifacts_only","jobs":results}
    (artifacts/"runner-evidence.json").write_text(json.dumps(report,indent=2)+"\n")
    return report

if __name__=="__main__":
    report=execute(Path("artifacts"))
    print(json.dumps(report,indent=2))
    if any(x["state"]!="DONE" for x in report["jobs"].values()):
        raise SystemExit(1)
