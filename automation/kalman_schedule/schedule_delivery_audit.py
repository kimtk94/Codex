#!/usr/bin/env python3
"""Read-only audit of GitHub schedule delivery, not a scientific seal attestation.

A separate event path can observe absence of BOTH Daily20 and watchdog schedules.
It still depends on GitHub, so an external monitor is separately required.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, time, timedelta, timezone
import json
import os
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

ROOT = "https://api.github.com/repos/kimtk94/Codex"
WORKFLOWS = ("kalman-daily20.yml", "kalman-daily20-slot-watchdog.yml")
FIRST_AUDIT_DAY = date(2026, 11, 24)
AUDIT_AFTER = time(8, 15)  # all four intended UTC slots plus 50 min grace
EXPECTED_PER_WORKFLOW = 2
VERSION = "kalman-schedule-delivery-audit-v1"


def latest_due_day(now):
    if now.tzinfo is None:
        raise ValueError("AUDIT_CLOCK_WITHOUT_TIMEZONE")
    now = now.astimezone(timezone.utc)
    day = now.date()
    if now.time().replace(tzinfo=None) < AUDIT_AFTER:
        day -= timedelta(days=1)
    while day.weekday() not in (1, 2, 3, 4, 5):
        day -= timedelta(days=1)
    if day < FIRST_AUDIT_DAY:
        raise ValueError("NO_ELIGIBLE_AUDIT_DAY")
    return day


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward an Actions read token to a redirected URL.
        return None


def api_get(path, token):
    if not path.startswith("/actions/workflows/"):
        raise ValueError("UNEXPECTED_API_PATH")
    req = Request(ROOT + path, headers={
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    with build_opener(NoRedirect()).open(req, timeout=25) as response:
        return json.load(response)


def check_workflow(filename, day, fetch):
    metadata = fetch("/actions/workflows/" + filename)
    if (metadata.get("path") != ".github/workflows/" + filename
            or type(metadata.get("id")) is not int
            or not isinstance(metadata.get("state"), str)):
        raise ValueError("UNVERIFIED_WORKFLOW_IDENTITY")
    workflow_id = metadata["id"]
    query = urlencode({"branch": "main", "event": "schedule",
                       "created": day.isoformat(), "per_page": 100})
    listing = fetch(f"/actions/workflows/{workflow_id}/runs?{query}")
    runs = listing.get("workflow_runs")
    count = listing.get("total_count")
    if not isinstance(runs, list) or type(count) is not int or count != len(runs) or count >= 100:
        raise ValueError("INCOMPLETE_OR_PAGINATED_RUN_LIST")
    evidence = []
    seen = set()
    for run in runs:
        run_id = run.get("id")
        if (type(run_id) is not int or run_id in seen
                or run.get("workflow_id") != workflow_id
                or run.get("event") != "schedule"
                or run.get("head_branch") != "main"):
            raise ValueError("UNVERIFIED_OR_DUPLICATE_SCHEDULE_RUN")
        created = datetime.fromisoformat(run["created_at"].replace("Z", "+00:00"))
        if created.tzinfo is None or created.astimezone(timezone.utc).date() != day:
            raise ValueError("RUN_OUTSIDE_TARGET_UTC_DAY")
        seen.add(run_id)
        evidence.append({"run_id": run_id, "created_at": run["created_at"],
                         "status": run.get("status"), "conclusion": run.get("conclusion"),
                         "head_sha": run.get("head_sha")})
    problems = []
    if metadata["state"] != "active":
        problems.append("WORKFLOW_NOT_ACTIVE")
    if count < EXPECTED_PER_WORKFLOW:
        problems.append("MISSING_SCHEDULE_DELIVERY")
    elif count > EXPECTED_PER_WORKFLOW:
        problems.append("EXCESS_SCHEDULE_RUNS_UNCLASSIFIED")
    if any(r["status"] != "completed" or r["conclusion"] != "success" for r in evidence):
        problems.append("SCHEDULE_RUN_INCOMPLETE_OR_UNSUCCESSFUL")
    return {"workflow": filename, "workflow_id": workflow_id,
            "state": metadata["state"], "expected_deliveries": EXPECTED_PER_WORKFLOW,
            "observed_deliveries": count, "runs": evidence,
            "problems": problems}


def audit(now, fetch):
    day = latest_due_day(now)
    rows = []
    api_failures = []
    for filename in WORKFLOWS:
        try:
            rows.append(check_workflow(filename, day, fetch))
        except (ValueError, TypeError, KeyError, OSError, AttributeError) as exc:
            # Do not print response bodies, headers or credentials.
            api_failures.append({"workflow": filename, "error_type": type(exc).__name__})
    observed = sum(r["observed_deliveries"] for r in rows)
    problems = [{"workflow": r["workflow"], "code": p}
                for r in rows for p in r["problems"]]
    complete = len(rows) == len(WORKFLOWS) and not api_failures
    return {
        "version": VERSION,
        "observed_at_utc": now.astimezone(timezone.utc).isoformat(),
        "target_utc_date": day.isoformat(),
        "source": "GITHUB_ACTIONS_WORKFLOW_STATE_AND_SCHEDULE_EVENT_API",
        "status": ("API_EVIDENCE_UNAVAILABLE_HOLD" if not complete else
                   "SCHEDULE_DELIVERY_HOLD" if problems else "DELIVERY_COUNT_OK_NOT_SEAL_PROOF"),
        "api_evidence_complete": complete,
        "expected_schedule_deliveries": 4,
        "observed_schedule_deliveries": observed if complete else None,
        "workflow_observations": rows, "problem_codes": problems,
        "api_failures": api_failures,
        "original_first_and_replay_roles_verified": False,
        "scientific_approval": "HOLD",
        "independent_off_github_monitor": False,
        "research_only": True, "production_writes": False,
        "live_execution": False, "strategy_promoted": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    parser.add_argument("--report-only", action="store_true",
                        help="PR: classify the actual incident without failing due to its existence")
    args = parser.parse_args()
    token = os.environ.get("GH_TOKEN", "")
    if not token:
        raise SystemExit("GITHUB_READ_TOKEN_MISSING")
    report = audit(datetime.now(timezone.utc), lambda path: api_get(path, token))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    # No credentials or raw API payloads printed.
    print(json.dumps(report, sort_keys=True))
    if not report["api_evidence_complete"]:
        return 2
    if args.report_only:
        return 0
    return 0 if report["status"] == "DELIVERY_COUNT_OK_NOT_SEAL_PROOF" else 2


if __name__ == "__main__":
    raise SystemExit(main())
