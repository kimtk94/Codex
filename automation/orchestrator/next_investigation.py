#!/usr/bin/env python3
"""Carry out ONE bounded, read-only next investigation selected by Autonomous Next.

Only GitHub Actions failed-job log classification is supported. No arbitrary
commands, source data writes, private logfile excerpts, or automatic retries.
Failure diagnostics are fixed enums; raw logs are NEVER written to artifacts.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import urllib.error
import urllib.request

from original_source_evidence import API, REPO, StripTokenOnRedirect, req
from priority import load_policy

MAX_LOG_BYTES = 2_000_000
MAX_JOBS = 3
NEXT_ACTION = "INSPECT_FAILURE_LOGS_READ_ONLY"
DIAGNOSTICS = (
    ("CANONICAL_LIFECYCLE_GROSS_COUNT_MISMATCH", "REVENUE_ISSUED_VS_LIFECYCLE_MISMATCH"),
    ("CANONICAL_AUTHORITY_PARITY_MISMATCH", "REVENUE_AUTHORITY_PARITY_MISMATCH"),
    ("CANONICAL_VAT_PARITY_MISMATCH", "REVENUE_VAT_PARITY_MISMATCH"),
    ("MONTHLY_AUTHORITY_FAIL_CLOSED", "REVENUE_AUTHORITY_GUARD"),
    ("SOURCE_UNAVAILABLE", "SOURCE_ACCESS_UNAVAILABLE"),
    ("SHEETS_READ_FAILED", "GOOGLE_SHEETS_READ_FAILED"),
    ("MISSING_GCP_SERVICE_ACCOUNT_JSON", "GOOGLE_SHEETS_CREDENTIAL_UNAVAILABLE"),
    ("HTTP Error 429", "GITHUB_OR_PROVIDER_RATE_LIMIT"),
    ("HTTP Error 403", "SOURCE_ACCESS_FORBIDDEN"),
    ("TimeoutExpired", "JOB_TIMEOUT"),
)
OUTPUT_STATES = frozenset({
    "NOT_APPLICABLE", "FAILED_JOB_DIAGNOSTIC_FOUND", "FAILED_JOB_UNCLASSIFIED",
    "FAILED_JOB_LOG_UNAVAILABLE", "FAILED_RUN_NO_FAILED_JOB", "FAILED_RUN_FETCH_UNAVAILABLE",
    "INVALID_PRIORITIZATION",
})


def safe_report(state, *, workflow=None, run_id=None, classification=None,
                inspected_jobs=0):
    return {
        "schema_version": 1,
        "state": state,
        "scope": "GITHUB_ACTIONS_FAILED_JOB_LOG_CLASSIFICATION_ONLY",
        "workflow": workflow,
        "run_url": f"https://github.com/{REPO}/actions/runs/{run_id}"
                   if type(run_id) is int and run_id > 0 else None,
        "diagnostic_code": classification,
        "inspected_failed_jobs": inspected_jobs,
        "raw_logs_persisted": False,
        "business_source_sink_verification": "NOT_VERIFIED",
        "auto_execute_business_writes": False,
        "auto_retry_runs": False,
        "auto_merge_pr": False,
    }


def read_jobs(run_id, token):
    url = API + f"/actions/runs/{run_id}/jobs?per_page=100"
    with urllib.request.urlopen(req(url, token), timeout=20) as response:
        data = response.read(400_001)
    if len(data) > 400_000:
        raise ValueError("JOBS_RESPONSE_TOO_LARGE")
    return json.loads(data)


def read_log(job_id, token):
    url = API + f"/actions/jobs/{job_id}/logs"
    with urllib.request.build_opener(StripTokenOnRedirect).open(
            req(url, token), timeout=25) as response:
        if not response.geturl().startswith("https://"):
            raise ValueError("UNSAFE_LOG_REDIRECT")
        data = response.read(MAX_LOG_BYTES + 1)
    if len(data) > MAX_LOG_BYTES:
        raise ValueError("FAILED_JOB_LOG_TOO_LARGE")
    return data.decode("utf-8", errors="replace")


def selected(prioritization):
    """Return only the user-approved investigation kind, never arbitrary work."""
    if not isinstance(prioritization, dict):
        raise ValueError("INVALID_PRIORITY_DOCUMENT")
    if (prioritization.get("repository") != REPO
            or prioritization.get("business_source_sink_verification") != "NOT_VERIFIED"
            or prioritization.get("auto_execute_business_writes") is not False
            or prioritization.get("auto_merge_pr") is not False):
        raise ValueError("UNTRUSTED_PRIORITY_DOCUMENT")
    selected = prioritization.get("next_review")
    queue = prioritization.get("queue")
    if not isinstance(selected, dict) or not isinstance(queue, list) or len(queue) != 9:
        raise ValueError("INVALID_PRIORITY_QUEUE")
    if sum(x.get("domain") == selected.get("domain") for x in queue if isinstance(x, dict)) != 1:
        raise ValueError("INVALID_PRIORITY_SELECTION")
    match = next(x for x in queue if x.get("domain") == selected["domain"])
    if match != selected:
        raise ValueError("PRIORITY_SELECTION_DRIFT")
    # Non-log actions remain recommendations; they are NOT executed here.
    if selected.get("next_safe_action") != NEXT_ACTION:
        return None
    if selected.get("signal") != "CI_FAILED":
        raise ValueError("NON_FAILED_RUN_CANNOT_BE_INSPECTED")
    run_id, workflow = selected.get("run_id"), selected.get("workflow")
    allowed = {x["workflow"] for x in load_policy()["domains"]}
    if type(run_id) is not int or run_id < 1 or workflow not in allowed:
        raise ValueError("UNTRUSTED_RUN_ID_OR_WORKFLOW")
    if selected.get("run_url") != f"https://github.com/{REPO}/actions/runs/{run_id}":
        raise ValueError("UNTRUSTED_RUN_LINK")
    return (workflow, run_id)


def investigate(prioritization, *, fetch_jobs=read_jobs, fetch_log=read_log, token=None):
    try:
        choice = selected(prioritization)
    except (ValueError, TypeError, KeyError):
        return safe_report("INVALID_PRIORITIZATION")
    if choice is None:
        return safe_report("NOT_APPLICABLE")
    workflow, run_id = choice
    token = os.getenv("GITHUB_TOKEN", "") if token is None else token
    try:
        response = fetch_jobs(run_id, token)
        jobs = response.get("jobs")
        if not isinstance(jobs, list):
            raise ValueError("INVALID_JOBS_RESPONSE")
        failed = [x for x in jobs if isinstance(x, dict) and x.get("conclusion") == "failure"]
        if not failed:
            return safe_report("FAILED_RUN_NO_FAILED_JOB", workflow=workflow, run_id=run_id)
        inspected = 0
        for item in failed[:MAX_JOBS]:
            job_id = item.get("id")
            if type(job_id) is not int or job_id <= 0:
                raise ValueError("INVALID_FAILED_JOB_ID")
            log = fetch_log(job_id, token)
            inspected += 1
            for snippet, label in DIAGNOSTICS:
                if snippet in log:
                    return safe_report("FAILED_JOB_DIAGNOSTIC_FOUND",
                                       workflow=workflow, run_id=run_id,
                                       classification=label, inspected_jobs=inspected)
        return safe_report("FAILED_JOB_UNCLASSIFIED", workflow=workflow, run_id=run_id,
                           inspected_jobs=inspected)
    except (OSError, ValueError, KeyError, TypeError, urllib.error.HTTPError):
        return safe_report("FAILED_JOB_LOG_UNAVAILABLE" if 'inspected' in locals()
                           else "FAILED_RUN_FETCH_UNAVAILABLE",
                           workflow=workflow, run_id=run_id)


def write_receipt(receipt: dict, path: Path):
    if receipt.get("state") not in OUTPUT_STATES:
        raise ValueError("UNEXPECTED_INSPECTION_RESULT")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "## Autonomous Next — one read-only failed-job inspection",
        f"- State: **{receipt['state']}**",
        f"- Diagnostic: **{receipt['diagnostic_code'] or 'NONE'}**",
        f"- Run: {receipt['run_url'] or 'NOT_APPLICABLE'}",
        "- Raw logs, customer data and amounts: **NOT STORED**",
        "- QQ/Feishu/SFDC source-to-sink acceptance: **NOT VERIFIED**",
        "- No workflow dispatch, Feishu writes, SFDC saves, customer emails or PR merges.",
    ]
    output = "\n".join(lines) + "\n"
    print(output)
    if os.getenv("GITHUB_STEP_SUMMARY"):
        with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf-8") as f:
            f.write(output)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--priority", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=Path("autonomous-next-inspection/inspection.json"))
    args = ap.parse_args()
    try:
        priority_doc = json.loads(args.priority.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        priority_doc = {}
    result = investigate(priority_doc)
    write_receipt(result, args.out)
    return 0 if result["state"] != "INVALID_PRIORITIZATION" else 2


if __name__ == "__main__":
    raise SystemExit(main())
