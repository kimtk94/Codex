#!/usr/bin/env python3
"""Host-run, read-only schedule delivery probe; never a signal or recovery writer."""
import argparse
from datetime import datetime, time as clock_time, timedelta, timezone
import json
import os
from pathlib import Path
import tempfile
import time

from schedule_delivery_audit import audit, api_get, FIRST_AUDIT_DAY, AUDIT_AFTER

VERSION = "kalman-external-schedule-probe-v2"
RETRY_DELAYS = (5, 15)
COUNT_OK = "DELIVERY_COUNT_OK_NOT_SEAL_PROOF"
WINDOW_OK = "DELIVERY_WINDOWS_OK_NOT_SEAL_PROOF"
# Proposed operational alert grace, not a GitHub SLA or scientific threshold.
WINDOW_GRACE_MINUTES = 50
SLOTS_UTC = {
    "kalman-daily20.yml": (clock_time(2, 40), clock_time(4, 40)),
    "kalman-daily20-slot-watchdog.yml": (clock_time(6, 25), clock_time(7, 25)),
}


def unavailable(now, status, reason, attempts=0):
    return {
        "observed_at_utc": now.isoformat() if now is not None else None,
        "target_utc_date": now.date().isoformat() if now is not None else None,
        "status": status, "reason": reason,
        "expected_schedule_deliveries": None if status == "NOT_DUE" else 4,
        "observed_schedule_deliveries": None, "api_evidence_complete": False,
        "api_attempts": attempts,
    }


def guard_fields(report):
    # An environment check cannot prove the identity or independence of a host.
    return {**report, "probe_version": VERSION,
            "independent_off_github_monitor": False,
            "host_independence_verified": False,
            "original_first_and_replay_roles_verified": False,
            "scientific_approval": "HOLD", "research_only": True,
            "production_writes": False, "live_execution": False,
            "strategy_promoted": False}


def assess_delivery_windows(report, now):
    """Check registration windows, not exact cron identity or original seal."""
    report = dict(report)
    report["delivery_count_status"] = report["status"]
    report["delivery_window_grace_minutes"] = WINDOW_GRACE_MINUTES
    report["delivery_windows_verified"] = False
    report["observed_within_window_deliveries"] = None
    report["delivery_window_observations"] = []
    report["out_of_window_run_ids"] = []
    if report.get("api_evidence_complete") is not True:
        return report

    observations = report["workflow_observations"]
    if (len(observations) != len(SLOTS_UTC)
            or {row["workflow"] for row in observations} != set(SLOTS_UTC)):
        raise ValueError("WINDOW_WORKFLOW_IDENTITY_INCOMPLETE")
    issues = list(report.get("problem_codes", []))
    windows = []
    unmatched = []
    matched_total = 0
    for row in observations:
        workflow = row["workflow"]
        ranges = []
        for nominal in SLOTS_UTC[workflow]:
            start = datetime.combine(now.date(), nominal, tzinfo=timezone.utc)
            ranges.append((start, start + timedelta(minutes=WINDOW_GRACE_MINUTES), []))
        for run in row["runs"]:
            stamp = datetime.fromisoformat(run["created_at"].replace("Z", "+00:00"))
            if stamp.tzinfo is None:
                raise ValueError("WINDOW_RUN_TIMESTAMP_UNVERIFIED")
            stamp = stamp.astimezone(timezone.utc)
            matches = [items for start, end, items in ranges
                       if start <= stamp <= end and stamp <= now]
            if len(matches) == 1:
                matches[0].append(run["run_id"])
                matched_total += 1
            else:
                unmatched.append(run["run_id"])
                issues.append({"workflow": workflow,
                               "code": "RUN_OUTSIDE_EXPECTED_REGISTRATION_WINDOWS",
                               "run_id": run["run_id"]})
        for start, end, items in ranges:
            status = "ONE_RUN_IN_WINDOW" if len(items) == 1 else (
                "MISSING_WINDOW" if not items else "MULTIPLE_RUNS_IN_WINDOW")
            windows.append({"workflow": workflow, "start_utc": start.isoformat(),
                            "end_utc": end.isoformat(), "run_ids": items,
                            "status": status})
            if status != "ONE_RUN_IN_WINDOW":
                issues.append({"workflow": workflow, "code": status,
                               "nominal_utc": start.isoformat()})
    report["delivery_window_observations"] = windows
    report["out_of_window_run_ids"] = unmatched
    report["observed_within_window_deliveries"] = matched_total
    report["problem_codes"] = issues
    report["delivery_windows_verified"] = (
        report["delivery_count_status"] == COUNT_OK
        and matched_total == 4 and not unmatched and not issues)
    report["status"] = (WINDOW_OK if report["delivery_windows_verified"]
                        else "SCHEDULE_DELIVERY_HOLD")
    return report


def probe(now, token, *, env, fetch=None, sleep=time.sleep):
    """Freeze one UTC observation date; retry only incomplete API evidence."""
    if now.tzinfo is None or now.utcoffset() is None:
        return guard_fields(unavailable(None, "API_EVIDENCE_UNAVAILABLE_HOLD",
                                        "CLOCK_WITHOUT_TIMEZONE"))
    now = now.astimezone(timezone.utc)
    if (str(env.get("GITHUB_ACTIONS", "")).lower() == "true"
            or bool(env.get("GITHUB_RUN_ID"))):
        return guard_fields(unavailable(now, "API_EVIDENCE_UNAVAILABLE_HOLD",
                                        "GITHUB_RUN_IS_NOT_EXTERNAL_HOST"))
    if (now.date() < FIRST_AUDIT_DAY or now.weekday() not in (1, 2, 3, 4, 5)
            or now.time().replace(tzinfo=None) < AUDIT_AFTER):
        return guard_fields(unavailable(now, "NOT_DUE",
                                        "TODAY_UTC_SLOTS_NOT_DUE"))
    if not isinstance(token, str) or not token.strip():
        return guard_fields(unavailable(now, "API_EVIDENCE_UNAVAILABLE_HOLD",
                                        "READ_ONLY_GITHUB_TOKEN_MISSING"))
    getter = fetch if fetch is not None else lambda path: api_get(path, token)
    report = None
    for attempt in range(1, len(RETRY_DELAYS) + 2):
        if attempt > 1:
            sleep(RETRY_DELAYS[attempt - 2])
        try:
            report = audit(now, getter)
            if report.get("target_utc_date") != now.date().isoformat():
                report = unavailable(now, "API_EVIDENCE_UNAVAILABLE_HOLD",
                                     "AUDIT_DATE_MISMATCH")
        except Exception:
            # Do not expose exception messages, response bodies or token.
            report = unavailable(now, "API_EVIDENCE_UNAVAILABLE_HOLD",
                                 "AUDIT_EXCEPTION")
        if report.get("api_evidence_complete") is True:
            break
    report["api_attempts"] = attempt
    try:
        report = assess_delivery_windows(report, now)
    except Exception:
        report = unavailable(now, "API_EVIDENCE_UNAVAILABLE_HOLD",
                             "WINDOW_EVIDENCE_UNVERIFIED", attempt)
    return guard_fields(report)


def exit_code(report):
    if (report["status"] == WINDOW_OK
            and report.get("api_evidence_complete") is True
            and report.get("delivery_windows_verified") is True
            and report.get("observed_schedule_deliveries") == 4
            and report.get("observed_within_window_deliveries") == 4):
        return 0  # Registration windows only; never scientific approval.
    return 3 if report["status"] == "NOT_DUE" else 2


def write_report(path, report):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8",
                                         dir=path.parent, delete=False) as handle:
            tmp = Path(handle.name)
            json.dump(report, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(tmp, path)
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)


def check_saved_report(path, now, *, max_age_minutes=45):
    """Read-only freshness check; not host identity, signature or seal proof."""
    result = {"heartbeat_status": "HEARTBEAT_UNKNOWN_HOLD",
              "reason": None, "target_utc_date": None,
              "report_age_seconds": None, "scientific_approval": "HOLD",
              "host_independence_verified": False,
              "original_first_and_replay_roles_verified": False,
              "production_writes": False, "live_execution": False}

    def hold(reason):
        return {**result, "reason": reason}, 2

    if now.tzinfo is None or now.utcoffset() is None:
        return hold("CLOCK_WITHOUT_TIMEZONE")
    now = now.astimezone(timezone.utc)
    result["target_utc_date"] = now.date().isoformat()
    if (now.date() < FIRST_AUDIT_DAY or now.weekday() not in (1, 2, 3, 4, 5)
            or now.time().replace(tzinfo=None) < AUDIT_AFTER):
        return {**result, "heartbeat_status": "NOT_DUE",
                "reason": "TODAY_UTC_SLOTS_NOT_DUE"}, 3
    if type(max_age_minutes) is not int or not 1 <= max_age_minutes <= 1440:
        return hold("INVALID_MAX_AGE")
    try:
        with Path(path).open("rb") as handle:
            payload = handle.read(1_048_577)
        if len(payload) > 1_048_576:
            return hold("REPORT_TOO_LARGE")
        report = json.loads(payload)
        if not isinstance(report, dict):
            return hold("MALFORMED_REPORT")
        if (report.get("probe_version") != VERSION
                or report.get("target_utc_date") != result["target_utc_date"]):
            return hold("WRONG_REPORT_VERSION_OR_DATE")
        stamp = datetime.fromisoformat(report["observed_at_utc"])
        if stamp.tzinfo is None or stamp.utcoffset() is None:
            return hold("UNVERIFIED_REPORT_TIMESTAMP")
        stamp = stamp.astimezone(timezone.utc)
        if stamp.date() != now.date() or stamp.time().replace(tzinfo=None) < AUDIT_AFTER:
            return hold("WRONG_OBSERVATION_DATE_OR_WINDOW")
        age = (now - stamp).total_seconds()
        result["report_age_seconds"] = age
        if age < 0:
            return hold("FUTURE_REPORT_TIMESTAMP")
        if age > max_age_minutes * 60:
            return hold("STALE_HEARTBEAT")
        if (report.get("scientific_approval") != "HOLD"
                or any(report.get(key) is not False for key in
                       ("production_writes", "live_execution", "strategy_promoted",
                        "host_independence_verified",
                        "original_first_and_replay_roles_verified"))):
            return hold("UNVERIFIED_REPORT_BOUNDARIES")
        if report.get("status") in ("API_EVIDENCE_UNAVAILABLE_HOLD",
                                    "SCHEDULE_DELIVERY_HOLD"):
            return {**result, "heartbeat_status": "FRESH_DELIVERY_HOLD",
                    "reason": report["status"]}, 2
        if exit_code(report) != 0:
            return hold("INCONSISTENT_REPORT_STATUS")
        # Re-evaluate the reported metadata before accepting a fresh success.
        rows = report["workflow_observations"]
        ids = []
        if not isinstance(rows, list) or len(rows) != 2:
            return hold("INCONSISTENT_REPORT_EVIDENCE")
        for row in rows:
            if (row["state"] != "active" or row["observed_deliveries"] != 2
                    or len(row["runs"]) != 2 or row["problems"]):
                return hold("INCONSISTENT_REPORT_EVIDENCE")
            for run in row["runs"]:
                if (type(run["run_id"]) is not int or run["run_id"] <= 0
                        or run["status"] != "completed"
                        or run["conclusion"] != "success"):
                    return hold("INCONSISTENT_REPORT_EVIDENCE")
                ids.append(run["run_id"])
        if len(set(ids)) != 4 or report.get("problem_codes") != []:
            return hold("INCONSISTENT_REPORT_EVIDENCE")
        checked = assess_delivery_windows({**report, "status": COUNT_OK}, stamp)
        if (exit_code(checked) != 0
                or checked["delivery_window_observations"]
                != report["delivery_window_observations"]):
            return hold("INCONSISTENT_REPORT_EVIDENCE")
        return {**result,
                "heartbeat_status": "FRESH_DELIVERY_WINDOWS_OK_NOT_SEAL_PROOF",
                "reason": "LOCAL_METADATA_ONLY"}, 0
    except FileNotFoundError:
        return hold("MISSING_HEARTBEAT")
    except (OSError, ValueError, TypeError, KeyError, AttributeError, OverflowError):
        return hold("UNREADABLE_OR_MALFORMED_HEARTBEAT")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--out", help="Local metadata JSON only")
    mode.add_argument("--check-existing", help="Read-only local heartbeat verification")
    parser.add_argument("--max-age-minutes", type=int, default=45)
    args = parser.parse_args()
    now = datetime.now(timezone.utc)
    if args.check_existing:
        verdict, code = check_saved_report(args.check_existing, now,
                                           max_age_minutes=args.max_age_minutes)
        print(json.dumps(verdict, sort_keys=True))
        return code
    report = probe(now, os.environ.get("GH_TOKEN", ""), env=os.environ)
    write_report(args.out, report)
    print(json.dumps(report, sort_keys=True))
    return exit_code(report)


if __name__ == "__main__":
    raise SystemExit(main())
