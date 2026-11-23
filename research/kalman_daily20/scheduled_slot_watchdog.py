#!/usr/bin/env python3
"""Independent GitHub-only heartbeat: BOTH Daily20 scheduled slots must exist.

No Drive credentials, signal writes, model execution, or broker calls.
A successful daily research run alone is NOT proof that the two scheduled
02:40/04:40 UTC slots each occurred and independently replayed first-seal data.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, time, timedelta, timezone
import json
import os
from pathlib import Path
import re

from ops_readiness import api, parse_first_seal_check, safe_job_log

VERSION = "daily20-scheduled-two-slot-heartbeat-v1"
ROOT = "https://api.github.com/repos/kimtk94/Codex"
WORKFLOW = "kalman-daily20.yml"
FIRST = "40 2 * * 2-6"
SECOND = "40 4 * * 2-6"
SLOTS = (FIRST, SECOND)
FIRST_ELIGIBLE_AUDIT_DAY = date(2026, 11, 24)
REQUIRED_JOBS = ("contracts", "restore-drive-cache",
                 "daily-research", "persist-google-drive")
AUDIT_AFTER_UTC = time(hour=6, minute=15)
# Suppress listing raw GitHub logs and tokens in reports.
READY_RE = re.compile(
    r"DAILY20_TWO_PASS_PHASE_READY\s+"
    r"(?P<session>\d{4}-\d{2}-\d{2})\s+"
    r"(?P<mode>[A-Z0-9_]+)\s+slot\s+"
    r"(?P<slot>40 [24] \* \* 2-6)\s*$"
)
POST_RE = re.compile(
    r"DAILY20_TWO_PASS_INTEGRITY_HOLD\s+"
    r"(?P<session>\d{4}-\d{2}-\d{2})\s+"
    r"mode\s+(?P<mode>[A-Z0-9_]+)\s+"
    r"status\s+(?P<status>[A-Z0-9_]+)\s+"
    r"changed\s+(?P<changed>True|False)\s+"
    r"new\s+(?P<new>\d+)\s*$"
)


def ensure(ok, code):
    if not ok:
        raise ValueError("SLOT_WATCHDOG_" + code)


def one_record(log, pattern):
    entries = [m.groupdict() for line in log.splitlines()
               if (m := pattern.search(line))]
    return entries[0] if len(entries) == 1 else None


def job_evidence(run, jobs, research_log, publisher_log):
    ready = one_record(research_log, READY_RE)
    post = one_record(research_log, POST_RE)
    readback = parse_first_seal_check(publisher_log)
    by_name = {j["name"]: j for j in jobs}
    missing_jobs = [name for name in REQUIRED_JOBS if
                    by_name.get(name, {}).get("conclusion") != "success"]
    remote_readback = (
        "\"DAILY20_DRIVE_READBACK\"" in publisher_log and
        "\"status\": \"READBACK_VERIFIED\"" in publisher_log and
        "\"session\": \"" + (ready["session"] if ready else "INVALID") + "\"" in publisher_log
    )
    # The report keeps only whitelisted, research-safe summary fields.
    return {
        "run_id": run.get("id"),
        "run_url": run.get("html_url"),
        "created_at": run.get("created_at"),
        "status": run.get("status"),
        "conclusion": run.get("conclusion"),
        "event": run.get("event"),
        "head_branch": run.get("head_branch"),
        "head_sha": run.get("head_sha"),
        "slot": ready["slot"] if ready else None,
        "session": ready["session"] if ready else None,
        "mode": ready["mode"] if ready else None,
        "post": post,
        "first_seal_readback": readback,
        "remote_drive_readback": remote_readback,
        "missing_successful_jobs": missing_jobs,
    }


def evaluate(target_date, *, expected_session, new_session_due, runs, now):
    ensure(isinstance(target_date, date) and
           not isinstance(target_date, datetime) and
           target_date >= FIRST_ELIGIBLE_AUDIT_DAY,
           "NOT_FIRST_ELIGIBLE_AUDIT_DATE")
    ensure(target_date.weekday() in (1, 2, 3, 4, 5),
           "AUDIT_NOT_TUESDAY_TO_SATURDAY")
    ensure(now.tzinfo is not None and
           now.astimezone(timezone.utc).date() == target_date and
           now.astimezone(timezone.utc).time().replace(tzinfo=None) >= AUDIT_AFTER_UTC,
           "AUDIT_BEFORE_TWO_SLOTS_DUE")
    ensure(isinstance(expected_session, str)
           and date.fromisoformat(expected_session) <= target_date,
           "INVALID_EXPECTED_MARKET_SESSION")
    ensure(type(new_session_due) is bool, "EXPECTED_SESSION_FLAG_INVALID")
    problems = []
    by_slot = {slot: [] for slot in SLOTS}
    unknown = []
    seen_ids = set()
    for item in runs:
        run_id = item.get("run_id")
        ensure(type(run_id) is int and run_id not in seen_ids,
               "DUPLICATE_OR_INVALID_GITHUB_RUN")
        seen_ids.add(run_id)
        run_time = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
        ensure(run_time.tzinfo is not None, "SCHEDULED_RUN_DATE_MISSING_TZ")
        ensure(run_time.astimezone(timezone.utc).date() == target_date,
               "RUN_FROM_ANOTHER_DATE")
        # Push, workflow_dispatch, or PR success cannot replace a scheduled run.
        if item.get("event") != "schedule" or item.get("head_branch") != "main":
            problems.append("NON_SCHEDULED_RUN_MUST_NOT_COUNT:" + str(run_id))
            continue
        slot = item.get("slot")
        if slot not in by_slot:
            unknown.append(run_id)
            continue
        by_slot[slot].append(item)
    if unknown:
        problems.append("SCHEDULED_RUN_WITHOUT_ROLE_EVIDENCE")
    for slot in SLOTS:
        items = by_slot[slot]
        if len(items) == 0:
            problems.append("MISSING_FIRST_SLOT" if slot == FIRST else
                            "MISSING_SECOND_SLOT")
        elif len(items) != 1:
            problems.append("AMBIGUOUS_FIRST_SLOT" if slot == FIRST else
                            "AMBIGUOUS_SECOND_SLOT")
    if not by_slot[FIRST] and not by_slot[SECOND]:
        problems.append("BOTH_SCHEDULED_SLOTS_MISSING")
    first = by_slot[FIRST][0] if len(by_slot[FIRST]) == 1 else None
    second = by_slot[SECOND][0] if len(by_slot[SECOND]) == 1 else None
    expected_modes = (
        ("FIRST_GENUINE_SEAL_EXPECTED", "SAME_SESSION_REPLAY_EXPECTED")
        if new_session_due else
        ("SAME_SESSION_REPLAY_EXPECTED", "SAME_SESSION_REPLAY_EXPECTED")
    )
    for slot, item, mode, count in (
        (FIRST, first, expected_modes[0], 60 if new_session_due else 0),
        (SECOND, second, expected_modes[1], 0),
    ):
        if item is None:
            continue
        mark = "FIRST" if slot == FIRST else "SECOND"
        if (item.get("conclusion") != "success" or
            item.get("status") != "completed" or
            item.get("missing_successful_jobs")):
            problems.append(mark + "_WORKFLOW_OR_JOB_FAILED")
        if item.get("session") != expected_session or item.get("mode") != mode:
            problems.append(mark + "_WRONG_SESSION_OR_ROLE")
        post = item.get("post")
        if not isinstance(post, dict) or any((
            post.get("session") != expected_session,
            post.get("mode") != mode,
            post.get("new") != str(count),
        )):
            problems.append(mark + "_POSTFLIGHT_MISSING_OR_WRONG_COUNT")
        if item.get("remote_drive_readback") is not True:
            problems.append(mark + "_DRIVE_READBACK_NOT_VERIFIED")
        seal = item.get("first_seal_readback")
        if not isinstance(seal, dict) or any((
            seal.get("session") != expected_session,
            seal.get("current") is not True,
            seal.get("deep", 0) < 1,
            seal.get("status") !=
              "NEW_SESSION_ORIGINAL_INPUTS_AND_EVENTS_ATTESTED_RESEARCH_HOLD",
            not isinstance(seal.get("snapshot_sha256"), str),
        )):
            problems.append(mark + "_ORIGINAL_FIRST_SEAL_REMOTE_PROOF_MISSING")
        elif (new_session_due and slot == FIRST and
              seal.get("original_run") != item["run_id"]):
            problems.append("FIRST_ORIGINAL_RUN_PROVENANCE_NOT_FIRST_JOB")
        elif (not new_session_due or slot == SECOND) and (
              not isinstance(seal.get("original_run"), int) or
              seal["original_run"] >= item["run_id"]):
            problems.append(mark + "_ORIGINAL_RUN_NOT_EARLIER")
    if first is not None and second is not None:
        if first["run_id"] >= second["run_id"]:
            problems.append("FIRST_MUST_PRECEDE_SECOND_RUN")
        if first.get("head_sha") != second.get("head_sha"):
            problems.append("CODE_SHA_CHANGED_BETWEEN_REPLAYS")
        fseal, sseal = (first.get("first_seal_readback"),
                        second.get("first_seal_readback"))
        if (not isinstance(fseal, dict) or not isinstance(sseal, dict) or
            fseal.get("original_run") != sseal.get("original_run") or
            fseal.get("snapshot_sha256") != sseal.get("snapshot_sha256")):
            problems.append("INDEPENDENT_REPLAY_DID_NOT_PRESERVE_ORIGINAL_SEAL")
        if new_session_due and isinstance(sseal, dict) and (
                sseal.get("original_run") != first["run_id"]):
            problems.append("SECOND_REPLAY_NOT_LINKED_TO_FIRST_RUN")
    # If a new date is not due (NYSE holiday), the original session is
    # expected to have been sealed on a prior market day, never today.
    status = "PASS" if not problems else "FAIL"
    return {
        "version": VERSION,
        "status": status, "research_only": True,
        "production_writes": False, "live_execution": False,
        "strategy_promoted": False,
        "scientific_approval": "HOLD",
        "target_utc_date": target_date.isoformat(),
        "last_completed_xnys_session": expected_session,
        "new_xnys_session_due": new_session_due,
        "first_scheduled_slot": FIRST, "second_scheduled_slot": SECOND,
        "first_run_id": first["run_id"] if first else None,
        "second_run_id": second["run_id"] if second else None,
        "first_mode": first["mode"] if first else None,
        "second_mode": second["mode"] if second else None,
        "expected_first_new_signals": 60 if new_session_due else 0,
        "expected_second_new_signals": 0,
        "unclassified_scheduled_run_ids": unknown,
        "problem_codes": sorted(set(problems)),
        "source_run_summaries": [
            {k: v for k, v in run.items() if k not in
             ("post", "first_seal_readback")}
            for run in runs
        ],
    }


def audit_calendar(now):
    import exchange_calendars as xc
    import pandas as pd
    from daily20 import last_completed_nyse
    utc = now.astimezone(timezone.utc)
    previous = utc.date() - timedelta(days=1)
    cal = xc.get_calendar("XNYS")
    expected_session = str(last_completed_nyse(utc))
    new_session_due = bool(cal.is_session(pd.Timestamp(previous)))
    return expected_session, new_session_due


def collect_schedule_runs(token, target_date):
    root = ROOT
    # The GitHub REST list workflow runs endpoint supports the created filter.
    # Date scoped to this UTC audit day; never use a stale older PASS.
    url = (f"{root}/actions/workflows/{WORKFLOW}/runs"
           f"?branch=main&event=schedule&created={target_date.isoformat()}"
           f"&per_page=100")
    listing = api(url, token)
    ensure(isinstance(listing, dict) and
           isinstance(listing.get("workflow_runs"), list),
           "GITHUB_RUNS_API_INVALID")
    raw = listing["workflow_runs"]
    ensure(len(raw) < 100, "GITHUB_RUN_PAGINATION_REQUIRED")
    results = []
    for run in raw:
        if run.get("event") != "schedule" or run.get("head_branch") != "main":
            continue
        info = api(f"{root}/actions/runs/{run['id']}/jobs?per_page=100", token)
        jobs = info.get("jobs", []) if isinstance(info, dict) else []
        ensure(isinstance(jobs, list) and len(jobs) < 100,
               "GITHUB_JOBS_PAGINATION_REQUIRED")
        names = {j.get("name"): j.get("id") for j in jobs}
        research_log, research_error = safe_job_log(
            root, names.get("daily-research"), token, "daily-research")
        publisher_log, publisher_error = safe_job_log(
            root, names.get("persist-google-drive"), token, "persist-google-drive")
        result = job_evidence(run, jobs, research_log, publisher_log)
        result["log_access_error_codes"] = [
            e for e in (research_error, publisher_error) if e
        ]
        results.append(result)
    return results


def create_report(*, now, token):
    target = now.astimezone(timezone.utc).date()
    expected, due = audit_calendar(now)
    entries = collect_schedule_runs(token, target)
    report = evaluate(target, expected_session=expected,
                      new_session_due=due, runs=entries, now=now)
    if any(r.get("log_access_error_codes") for r in entries):
        report["status"] = "FAIL"
        report["problem_codes"] = sorted(set(report["problem_codes"] +
                                             ["GITHUB_JOB_LOG_UNAVAILABLE"]))
    return report


def summary(report):
    lines = [
        "## Daily20 scheduled first-seal / independent replay watchdog",
        f"- Target UTC day: {report.get('target_utc_date', 'UNKNOWN')}",
        f"- Latest complete XNYS session: {report.get('last_completed_xnys_session')}",
        f"- New XNYS session due: {report.get('new_xnys_session_due')}",
        f"- First slot 02:40 UTC: {report.get('first_run_id')}",
        f"- Second slot 04:40 UTC: {report.get('second_run_id')}",
        f"- Scheduled heartbeat: **{report['status']}**",
        f"- Scientific approval: HOLD (independent source certification not implied)",
        f"- Failure codes: {', '.join(report.get('problem_codes', [])) or 'none'}",
        "- This watchdog reads GitHub only; never writes forecasts, journals or Drive.",
        "",
    ]
    return "\n".join(lines)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", required=True)
    a = p.parse_args()
    now = datetime.now(timezone.utc)
    outfile = Path(a.out)
    outfile.parent.mkdir(parents=True, exist_ok=True)
    try:
        token = os.environ.get("GH_TOKEN", "")
        ensure(bool(token), "GITHUB_READ_TOKEN_MISSING")
        report = create_report(now=now, token=token)
    except (RuntimeError, ValueError, OSError, KeyError,
            TypeError) as exc:
        # A transient API or calendar failure should never produce a green
        # heartbeat. Avoid echoing URL tokens or remote response bodies.
        report = {
            "version": VERSION, "status": "FAIL",
            "target_utc_date": now.date().isoformat(),
            "research_only": True, "live_execution": False,
            "strategy_promoted": False, "production_writes": False,
            "scientific_approval": "HOLD",
            "problem_codes": ["WATCHDOG_INPUT_OR_NETWORK_UNAVAILABLE",
                              type(exc).__name__],
        }
    outfile.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    md = summary(report)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(md)
    print(md)
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
