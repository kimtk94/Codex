#!/usr/bin/env python3
"""Read-only local Salesforce manual-Save journal health check.

No Salesforce/Playwright usage, no API, no CRM changes. No private IDs, names,
before-values, fingerprints or entire ledger contents printed to console.
"""
import argparse
import json
from collections import Counter
from pathlib import Path

from manual_save_journal import _private_path, _read


def summarize(path):
    """Summarize only state COUNTS; active or stale lock means not write-ready."""
    p = _private_path(path)
    data = _read(p)
    counts = Counter(e["state"] for e in data["entries"])
    lock_exists = p.with_name(p.name + ".lock").exists()
    unsafe_states = ("PENDING_WRITE", "WRITE_OUTCOME_UNKNOWN",
                     "READBACK_REQUIRED", "READBACK_MATCH_REVIEW_REQUIRED")
    need_review = sum(counts.get(v, 0) for v in unsafe_states)
    return {
        "version": "sfdc-save-journal-health-v1",
        "total_requests": len(data["entries"]),
        "state_counts": dict(sorted(counts.items())),
        "lock_present": lock_exists,
        "unresolved_operation_count": need_review,
        "status": "HOLD_MANUAL_RECOVERY_REQUIRED" if lock_exists or need_review else "LEDGER_READ_ONLY_VALID",
        "save_allowed": False,
        "salesforce_save_performed_by_check": False,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--ledger", default=str(
        Path.home() / ".sfdc_desktop" / "operation_ledger_private.json"))
    args = p.parse_args()
    report = summarize(args.ledger)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
