#!/usr/bin/env python3
"""Two independent current Opportunity reloads -> baseline stability certificate.

Read-only, offline. Neither matching fields nor a time-separated pair proves
any Save took place. Customer record IDs and fields remain in local private
JSON only. Certificate holds only metadata and status, no raw business values.
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from capture_existing_opportunity_snapshot import compare_snapshots, validate_snapshot

MAX_GAP_SECONDS = 7200
MAX_AGE_SECONDS = 14400
MAX_FUTURE_SKEW_SECONDS = 120


def _time(snapshot):
    stamp = snapshot.get("captured_at_utc")
    if not isinstance(stamp, str):
        return None
    try:
        t = datetime.fromisoformat(stamp)
    except ValueError:
        return None
    return t.astimezone(timezone.utc) if t.tzinfo and t.utcoffset() is not None else None


def verify_pair(first, second, now=None):
    """An exact comparison of two separately captured Salesforce reloads."""
    result = {
        "version": "sfdc-independent-reloads-v1",
        "status": "HOLD_NOT_VERIFIED",
        "two_reload_baseline_consistent": False,
        "save_confirmed": False,
        "save_allowed": False,
        "salesforce_save_performed": False,
    }
    try:
        validate_snapshot(first)
        validate_snapshot(second)
    except ValueError:
        result["status"] = "HOLD_INVALID_SNAPSHOT"
        return result
    a, b = _time(first), _time(second)
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Comparison clock must be timezone aware")
    if a is None or b is None:
        result["status"] = "HOLD_UNTRUSTED_CAPTURE_TIME"
        return result
    dt = (b - a).total_seconds()
    if dt <= 0:
        result["status"] = "HOLD_NOT_TWO_SEQUENTIAL_RELOADS"
        return result
    age = (now - b).total_seconds()
    if (dt > MAX_GAP_SECONDS or age > MAX_AGE_SECONDS
            or age < -MAX_FUTURE_SKEW_SECONDS):
        result["status"] = "HOLD_STALE_OR_FUTURE_CAPTURE"
        return result
    status = compare_snapshots(first, second)
    if status != "SNAPSHOTS_MATCH_NOT_PROOF_OF_SAVE":
        result["status"] = status
        return result
    result["status"] = "TWO_RELOADED_BASELINES_MATCH_NOT_SAVE_PROOF"
    result["two_reload_baseline_consistent"] = True
    result["checked_field_count"] = len(second["current_field_values"])
    result["seconds_between_reloads"] = round(dt, 2)
    return result


def main():
    p = argparse.ArgumentParser()
    root = Path.home() / ".sfdc_desktop"
    p.add_argument("--first", required=True)
    p.add_argument("--second", required=True)
    p.add_argument("--output", default=str(root / "independent_reloads_audit_PRIVATE.json"))
    args = p.parse_args()
    # This checker must never output private source IDs to the terminal/CI.
    def read(filename):
        return json.loads(Path(filename).read_text(encoding="utf-8-sig"))
    result = verify_pair(read(args.first), read(args.second))
    out = Path(args.output)
    if (not out.is_absolute() or out.parent.resolve() != root.resolve()
            or not out.name.endswith("_PRIVATE.json") or out.exists()
            or out.is_symlink()):
        p.error("Comparison results must be new files in the local private directory")
    with out.open("x", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    print("INDEPENDENT RELOADS:", result["status"])
    print("SAVE CONFIRMED: FALSE")
    print("CUSTOMER DATA WRITTEN TO GITHUB: FALSE")
    print("PRIVATE RESULT:", out)


if __name__ == "__main__":
    main()
