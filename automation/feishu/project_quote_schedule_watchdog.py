#!/usr/bin/env python3
"""Read-only GitHub Actions schedule heartbeat for Feishu Quote-first sync.

A successful historical run is NOT evidence that the schedule is currently
executing. This checks the last *scheduled* invocation, not PR/dispatch runs.
Does not read/write customer records or trigger Feishu/SFDC/QQ actions.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
import urllib.error
import urllib.request

UTC = dt.timezone.utc
WORKFLOW = "feishu-project-quote-operations.yml"
MAX_SCHEDULE_GAP_HOURS = 8.0
EXPECTED_INTERVAL_HOURS = 2.0
MAX_SKEW_MINUTES = 5


def stamp(raw):
    if not isinstance(raw, str):
        raise ValueError("INVALID_RUN_TIMESTAMP")
    value = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if value.tzinfo is None:
        raise ValueError("NAIVE_RUN_TIMESTAMP")
    return value.astimezone(UTC)


def classify(payload, now=None):
    now = now or dt.datetime.now(UTC)
    if now.tzinfo is None:
        raise ValueError("NAIVE_NOW")
    if not isinstance(payload, dict) or not isinstance(payload.get("workflow_runs"), list):
        raise ValueError("WORKFLOW_RUN_SCHEMA")
    runs = [r for r in payload["workflow_runs"]
            if isinstance(r, dict) and r.get("event") == "schedule"]
    if not runs:
        return {"status": "NO_SCHEDULED_RUN", "scheduled_runs": 0,
                "max_gap_hours": MAX_SCHEDULE_GAP_HOURS,
                "original_feishu_verified": False,
                "source_mirror_verified": False}
    ordered = sorted(runs, key=lambda r: stamp(r.get("created_at")), reverse=True)
    last = ordered[0]
    age = (now.astimezone(UTC) - stamp(last["created_at"])).total_seconds() / 3600
    if age < -MAX_SKEW_MINUTES / 60:
        raise ValueError("SCHEDULE_TIMESTAMP_IN_FUTURE")
    state = str(last.get("status") or "").lower()
    outcome = str(last.get("conclusion") or "").lower()
    if age > MAX_SCHEDULE_GAP_HOURS:
        status = "MISSED_SCHEDULE"
    elif state in {"queued", "in_progress", "waiting", "pending"}:
        status = "RUN_IN_PROGRESS"
    elif state == "completed" and outcome == "success":
        status = "RECENT_SCHEDULE_SUCCESS"
    elif state == "completed":
        status = "LAST_SCHEDULE_FAILED"
    else:
        status = "UNKNOWN_RUN_STATE"
    successes = [r for r in ordered
                 if r.get("status") == "completed" and r.get("conclusion") == "success"]
    return {
        "status": status,
        "scheduled_runs": len(ordered),
        "last_schedule_at_utc": stamp(last["created_at"]).isoformat(),
        "last_schedule_age_hours": round(max(0, age), 2),
        "last_schedule_state": state,
        "last_schedule_conclusion": outcome or "NOT_FINISHED",
        "last_success_at_utc": stamp(successes[0]["created_at"]).isoformat() if successes else None,
        "expected_interval_hours": EXPECTED_INTERVAL_HOURS,
        "max_gap_hours": MAX_SCHEDULE_GAP_HOURS,
        "original_feishu_verified": False,
        "source_mirror_verified": False,
    }


def fetch_runs(repo, token):
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        raise ValueError("INVALID_GITHUB_REPOSITORY")
    url = ("https://api.github.com/repos/" + repo + "/actions/workflows/" +
           WORKFLOW + "/runs?per_page=100")
    headers = {"Accept": "application/vnd.github+json",
               "User-Agent": "CSS-Feishu-Schedule-Watchdog",
               "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        headers["Authorization"] = "Bearer " + token
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=20) as response:
        if response.status != 200:
            raise RuntimeError("GITHUB_WORKFLOW_API_UNAVAILABLE")
        return json.load(response)


def main():
    try:
        payload = fetch_runs(os.getenv("GITHUB_REPOSITORY", ""),
                             os.getenv("GITHUB_TOKEN", ""))
        result = classify(payload)
    except Exception as exc:
        # Never expose request headers, credentials, or raw server responses.
        result = {"status": "MONITOR_UNAVAILABLE",
                  "error_type": type(exc).__name__,
                  "original_feishu_verified": False,
                  "source_mirror_verified": False}
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    summary = os.getenv("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as handle:
            handle.write("### Feishu Quote-first schedule heartbeat\n\n")
            handle.write("Status: **" + result["status"] + "**. ")
            handle.write("Scheduled source run is monitored independently of data freshness.\n\n")
            handle.write("GitHub schedule success never verifies original Feishu/QQ/SFDC or sink parity.\n")
    if result["status"] not in {"RECENT_SCHEDULE_SUCCESS", "RUN_IN_PROGRESS"}:
        sys.exit(2)


if __name__ == "__main__":
    main()
