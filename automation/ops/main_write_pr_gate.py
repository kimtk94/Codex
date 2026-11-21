#!/usr/bin/env python3
"""Always-running pull-request gate for detectable Git writes to main.

This deliberately narrow control blocks known explicit/main-target and unknown
workflow pushes, plus non-fixture literal main references in directly referenced
scripts. It is NOT a complete indirect call-graph / token-security certification.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

from automation.ops.audit_indirect_git_writes import scan as scan_indirect
from automation.ops.audit_main_writes import scan_workflows as scan_direct


def evaluate(root: Path) -> dict:
    direct = scan_direct(root)
    indirect = scan_indirect(root)
    failures: list[str] = []
    if direct["workflow_files_scanned"] != indirect["workflow_count"]:
        failures.append("WORKFLOW_COVERAGE_MISMATCH")
    if direct["direct_main_write_count"]:
        failures.append("DIRECT_MAIN_WRITE")
    if direct["unknown_push_count"]:
        failures.append("UNKNOWN_PUSH_TARGET")
    if indirect["executable_main_write_candidates"]:
        failures.append("REFERENCED_SCRIPT_MAIN_WRITE_CANDIDATE")
    report = {
        "schema_version": 1,
        "timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "result": "BLOCK" if failures else "PASS_WITH_REVIEW_LIMITATIONS",
        "fail_reasons": failures,
        "workflow_count": direct["workflow_files_scanned"],
        "direct_main_writes": direct["direct_main_write_count"],
        "unknown_push_targets": direct["unknown_push_count"],
        "indirect_main_write_candidates": indirect["executable_main_write_candidates"],
        "indirect_inventory_status": indirect["status"],
        "write_permission_workflows": indirect["workflow_write_permission_count"],
        "limitations": [
            "A green check verifies only the enumerated static guard conditions",
            "Transitive imports, dynamic commands, external actions, and token inheritance remain under separate review",
            "This is not proof that main branch protection or a repository ruleset is enabled",
        ],
    }
    return report


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Fail-closed PR check for detectable main writes")
    p.add_argument("--root", type=Path, default=Path("."))
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args(argv)
    try:
        report = evaluate(args.root)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("MAIN_WRITE_PR_GATE:", report["result"])
        print("WORKFLOW_COUNT:", report["workflow_count"])
        for label in ("direct_main_writes", "unknown_push_targets", "indirect_main_write_candidates"):
            print(label.upper() + ":", report[label])
        for reason in report["fail_reasons"]:
            print("BLOCK_REASON:", reason)
        print("DISCLAIMER: Static signal gate only; indirect pathways remain REVIEW_REQUIRED.")
        return 1 if report["fail_reasons"] else 0
    except (OSError, ValueError, UnicodeError, KeyError, TypeError) as e:
        print("MAIN_WRITE_PR_GATE: AUDIT_INCOMPLETE", type(e).__name__, str(e)[:180])
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
