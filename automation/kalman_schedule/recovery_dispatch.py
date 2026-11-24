#!/usr/bin/env python3
"""One-time reviewed, actual-time research recovery, never a scheduled seal.

Only dispatch the existing main Daily20 workflow before the following XNYS
open. No Drive or broker credentials, no historical signal reconstruction.
The target workflow independently rechecks the explicit session at admission.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, time, timedelta, timezone
import json
import os
from pathlib import Path
import sys
from time import sleep
from urllib.parse import urlencode
from urllib.request import Request, build_opener

from schedule_delivery_audit import ROOT, NoRedirect, api_get

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "research/kalman_daily20"))
from daily20 import last_completed_nyse
from forward_shadow import check_signal_admission

VERSION = "kalman-reviewed-recovery-dispatch-v1"
WORKFLOW_ID = 425141580
WORKFLOW_FILE = "kalman-daily20.yml"
REQUEST_PATH = Path("automation/kalman_schedule/recovery_requests/2026-11-24.json")
MIN_DISPATCH_BUFFER_MINUTES = 120
AFTER_SCHEDULE_GRACE = time(8, 15)
ACTIVE_STATES = ("queued", "in_progress", "waiting", "pending", "requested")


def require(condition, code):
    if not condition:
        raise ValueError(code)


def verify_recovery_clock(session, utc_day, now, *, min_minutes=0):
    require(now.tzinfo is not None, "RECOVERY_CLOCK_WITHOUT_TIMEZONE")
    now = now.astimezone(timezone.utc)
    target = date.fromisoformat(session)
    day = date.fromisoformat(utc_day)
    require(str(target) == session and str(day) == utc_day,
            "RECOVERY_REQUEST_NOT_ISO_DATE")
    require(now.date() == day and day.weekday() in (1, 2, 3, 4, 5),
            "RECOVERY_REQUEST_EXPIRED_OR_WRONG_DAY")
    require(now.time().replace(tzinfo=None) >= AFTER_SCHEDULE_GRACE,
            "RECOVERY_TOO_EARLY_FOR_MISSING_SCHEDULE_DECISION")
    require(str(last_completed_nyse(now)) == session,
            "RECOVERY_TARGET_NOT_LATEST_COMPLETED_XNYS")
    # Require a genuinely new session for this day, not a holiday replay.
    require(target == day - timedelta(days=1), "RECOVERY_NOT_NEW_SESSION")
    admitted, next_open = check_signal_admission(session, now)
    next_stamp = datetime.fromisoformat(next_open)
    require(admitted and now + timedelta(minutes=min_minutes) < next_stamp,
            "RECOVERY_ADMISSION_WINDOW_OR_BUFFER_EXPIRED")
    return next_stamp


def load_request(path):
    request = json.loads(Path(path).read_text())
    require(request.get("version") == VERSION
            and request.get("classification") == "ACTUAL_TIME_MANUAL_RESEARCH_RECOVERY"
            and request.get("research_only") is True
            and request.get("live_execution") is False
            and request.get("production_writes") is False
            and request.get("scheduled_seal_credit") is False
            and request.get("historical_reseal") is False
            and request.get("requested_role") == "FIRST_IF_ABSENT"
            and request.get("incident") == 1045
            and request.get("target_utc_day") == Path(path).stem,
            "RECOVERY_REQUEST_GOVERNANCE_INVALID")
    return request


def exact_runs(fetch, **filters):
    query = urlencode({"branch": "main", "per_page": 100, **filters})
    listing = fetch(f"/actions/workflows/{WORKFLOW_ID}/runs?{query}")
    runs = listing.get("workflow_runs")
    total = listing.get("total_count")
    require(isinstance(runs, list) and type(total) is int
            and total == len(runs) and total < 100, "RECOVERY_RUN_LIST_INCOMPLETE")
    ids = set()
    for r in runs:
        require(type(r.get("id")) is int and r["id"] not in ids
                and r.get("workflow_id") == WORKFLOW_ID
                and r.get("head_branch") == "main",
                "RECOVERY_RUN_IDENTITY_INVALID")
        ids.add(r["id"])
    return runs


def decide(request, now, fetch):
    session = request["session"]
    day = request["target_utc_day"]
    next_open = verify_recovery_clock(session, day, now,
                                      min_minutes=MIN_DISPATCH_BUFFER_MINUTES)
    meta = fetch("/actions/workflows/" + WORKFLOW_FILE)
    require(meta.get("id") == WORKFLOW_ID
            and meta.get("path") == ".github/workflows/" + WORKFLOW_FILE
            and meta.get("state") == "active",
            "RECOVERY_TARGET_WORKFLOW_NOT_VERIFIED_ACTIVE")
    runs = exact_runs(fetch, created=day)
    for r in runs:
        stamp = datetime.fromisoformat(r["created_at"].replace("Z", "+00:00"))
        require(stamp.tzinfo is not None and str(stamp.astimezone(timezone.utc).date()) == day,
                "RECOVERY_RUN_OUTSIDE_TARGET_DAY")
    active_ids = {r["id"] for r in runs if r.get("status") != "completed"}
    for state in ACTIVE_STATES:
        active_ids.update(r["id"] for r in exact_runs(fetch, status=state))
    codes = []
    if any(r.get("event") in ("schedule", "workflow_dispatch") for r in runs):
        codes.append("ORIGINAL_SCHEDULE_OR_MANUAL_EVENT_ALREADY_EXISTS")
    if any(r.get("status") == "completed" and r.get("conclusion") == "success" for r in runs):
        codes.append("SUCCESSFUL_MAIN_RUN_REQUIRES_REVIEW")
    if active_ids:
        codes.append("MAIN_RESEARCH_RUN_ACTIVE")
    return {
        "version": VERSION, "session": session, "target_utc_day": day,
        "observed_at_utc": now.astimezone(timezone.utc).isoformat(),
        "next_open_utc": next_open.isoformat(), "min_dispatch_buffer_minutes": MIN_DISPATCH_BUFFER_MINUTES,
        "status": "RECOVERY_DISPATCH_ELIGIBLE" if not codes else "RECOVERY_NOT_DISPATCHED_HOLD",
        "blockers": codes, "active_main_run_ids": sorted(active_ids),
        "existing_main_runs": [{"id": r["id"], "event": r.get("event"),
                               "status": r.get("status"), "conclusion": r.get("conclusion")}
                              for r in runs],
        "dispatch_accepted": False, "scientific_approval": "HOLD",
        "scheduled_seal_credit": False, "research_only": True, "live_execution": False,
        "production_writes": False, "historical_reseal": False,
        "requested_event": "workflow_dispatch", "target_workflow_id": WORKFLOW_ID,
    }


def dispatch(token, request):
    payload = json.dumps({"ref": "main", "inputs": {
        "recovery_session": request["session"],
        "recovery_utc_day": request["target_utc_day"],
    }}).encode()
    req = Request(ROOT + f"/actions/workflows/{WORKFLOW_ID}/dispatches",
                  data=payload, method="POST", headers={
                      "Authorization": "Bearer " + token,
                      "Accept": "application/vnd.github+json",
                      "Content-Type": "application/json",
                      "X-GitHub-Api-Version": "2022-11-28",
                  })
    # No retry after POST: network ambiguity must be resolved by reading runs.
    with build_opener(NoRedirect()).open(req, timeout=30) as response:
        require(response.status in (200, 204), "RECOVERY_DISPATCH_NOT_ACCEPTED")
        return response.status


def save(out, report):
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, sort_keys=True))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", required=True)
    p.add_argument("--execute", action="store_true")
    args = p.parse_args()
    try:
        token = os.environ.get("GH_TOKEN", "")
        require(bool(token), "GITHUB_TOKEN_MISSING")
        request = load_request(REQUEST_PATH)
        if args.execute:
            require(os.environ.get("GITHUB_REPOSITORY") == "kimtk94/Codex"
                    and os.environ.get("GITHUB_REF") == "refs/heads/main"
                    and os.environ.get("GITHUB_EVENT_NAME") == "push",
                    "RECOVERY_DISPATCH_FORBIDDEN_OUTSIDE_REVIEWED_MAIN_PUSH")
        for attempt in range(13):
            report = decide(request, datetime.now(timezone.utc),
                            lambda path: api_get(path, token))
            if report["blockers"] != ["MAIN_RESEARCH_RUN_ACTIVE"] or not args.execute:
                break
            if attempt < 12:
                sleep(30)
        if report["status"] != "RECOVERY_DISPATCH_ELIGIBLE" or not args.execute:
            save(args.out, report)
            return 2 if args.execute else 0
        # Revalidate wall clock and all run evidence immediately before POST.
        report = decide(request, datetime.now(timezone.utc), lambda path: api_get(path, token))
        if report["status"] != "RECOVERY_DISPATCH_ELIGIBLE":
            save(args.out, report)
            return 2
        # Record intent before a potentially ambiguous network response.
        save(args.out, report)
        report["http_status"] = dispatch(token, request)
        report["dispatch_accepted"] = True
        report["status"] = "RECOVERY_DISPATCH_ACCEPTED_NOT_EXECUTION_PROOF"
        save(args.out, report)
        return 0
    except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError) as exc:
        save(args.out, {"version": VERSION, "status": "RECOVERY_BLOCKED_OR_UNKNOWN_HOLD",
                        "error_type": type(exc).__name__,
                        "dispatch_accepted": None,
                        "scheduled_seal_credit": False, "research_only": True,
                        "live_execution": False, "production_writes": False,
                        "scientific_approval": "HOLD"})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
