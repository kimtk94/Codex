#!/usr/bin/env python3
"""Conservative static QQ 2026 invoice replay writer-surface audit.

This is NOT an authorization, transactional lock or exhaustive call-graph proof.
Read only checked-out source files and print a fixed, identifier-free summary.
"""
import json
from pathlib import Path
import re
import sys

TARGET = "QQ 2026 Invoice Backfill"
MAIN_WORKFLOW = "qq-2026-invoice-backfill.yml"
LEGACY_WRITER = "automation/css_mail/qq_historical_invoice_backfill.py"
SAFE_WRITER = "automation/css_mail/qq_historical_invoice_backfill_2026_safe.py"
LEGACY_INVOCATION = re.compile(
    r"\bpython(?:3)?\s+" + re.escape(LEGACY_WRITER) + r"\b")
APPLY_MODE = re.compile(
    r"(?m)^\s*BACKFILL_WRITE_MODE:\s*['\x22]?APPLY(?:['\x22]|\s|$)")
PREVIEW_MODE = re.compile(
    r"(?m)^\s*BACKFILL_WRITE_MODE:\s*['\x22]?PREVIEW(?:['\x22]|\s|$)")
YEAR_2025 = re.compile(
    r"(?m)^\s*BACKFILL_YEAR:\s*['\x22]?2025(?:['\x22]|\s|$)")
BACKFILL_JOB = re.compile(r"(?m)^  backfill:\s*$")


def assess(workflows, scripts):
    """Pure conservative inventory; always HOLD until external writers ruled out."""
    if MAIN_WORKFLOW not in workflows:
        raise ValueError("REPLAY_2026_WORKFLOW_MISSING")
    if SAFE_WRITER not in scripts or LEGACY_WRITER not in scripts:
        raise ValueError("REPLAY_BACKFILL_WRITER_SOURCE_MISSING")
    main = workflows[MAIN_WORKFLOW]
    unsafe = 0
    bounded_2025 = 0
    source_entrypoints = 0
    suspicious = 0
    reasons = set()
    if not PREVIEW_MODE.search(main):
        reasons.add("PREVIEW_NOT_PINNED")
    if APPLY_MODE.search(main) or BACKFILL_JOB.search(main):
        reasons.add("APPLY_WORKFLOW_ENABLED")
    if "BACKFILL_STAGE_WRITES_APPROVED" in main:
        reasons.add("STAGE_APPROVAL_FLAG_IN_WORKFLOW")
    if SAFE_WRITER not in main:
        reasons.add("PREVIEW_SOURCE_ENTRYPOINT_UNVERIFIED")
    if "safe-preview:" not in main:
        reasons.add("PREVIEW_JOB_MISSING")
    for name, content in workflows.items():
        if name == MAIN_WORKFLOW:
            source_entrypoints += 1
            continue
        # An exact 2026 stage tab in an independent workflow is a potential
        # bypass of the target-specific preview gate, regardless of whether
        # it presently appears under a manually dispatched job.
        if TARGET in content:
            suspicious += 1
            reasons.add("INDEPENDENT_2026_STAGE_REFERENCE")
        if LEGACY_INVOCATION.search(content):
            source_entrypoints += 1
            if YEAR_2025.search(content) and TARGET not in content:
                bounded_2025 += 1
            else:
                unsafe += 1
                reasons.add("LEGACY_WRITER_NOT_YEAR_PINNED")
        if APPLY_MODE.search(content) and SAFE_WRITER in content:
            unsafe += 1
            reasons.add("SECONDARY_APPLY_ROUTE")
    # Assert source-level 2026 hard HOLD exists, not just a PREVIEW setting
    # in GitHub Actions. This is a conservative static code check.
    if ("def guard_2026_stage_apply(" not in scripts[SAFE_WRITER]
            or "guard_2026_stage_apply(mode,requested_year,TAB)" not in scripts[SAFE_WRITER]
            or "QQ_2026_APPLY_HARD_HOLD_WRITER_EXCLUSION_UNVERIFIED" not in scripts[SAFE_WRITER]):
        reasons.add("2026_SOURCE_HARD_HOLD_MISSING")
    if ("def guard_legacy_2026_target(" not in scripts[LEGACY_WRITER]
            or "guard_legacy_2026_target(requested_year,TAB)" not in scripts[LEGACY_WRITER]
            or "QQ_LEGACY_2026_APPLY_HARD_HOLD_UNVERIFIED_WRITER" not in scripts[LEGACY_WRITER]):
        reasons.add("LEGACY_2026_SOURCE_HARD_HOLD_MISSING")
    if ("def google_sheet_scopes(mode):" not in scripts[SAFE_WRITER]
            or 'scopes=google_sheet_scopes(mode)' not in scripts[SAFE_WRITER]
            or 'https://www.googleapis.com/auth/spreadsheets.readonly' not in scripts[SAFE_WRITER]):
        reasons.add("PREVIEW_READONLY_OAUTH_SCOPE_MISSING")
    if not re.search(r"mode\s*==\s*['\x22]APPLY['\x22]",
                     scripts[SAFE_WRITER]):
        # Cannot assume writer behavior is unchanged; this audit is for the
        # known 2026-safe writer, and unknown branches require review.
        reasons.add("SAFE_WRITER_GATE_UNRECOGNIZED")
    # Any source writer retaining an APPLY path is a potential manual route.
    # No GitHub concurrency group protects against direct API/script writers.
    return {
        "status": "HOLD",
        "workflow_count": len(workflows),
        "known_source_entrypoints": source_entrypoints,
        "bounded_2025_legacy_entries": bounded_2025,
        "unbounded_legacy_entries": unsafe,
        "independent_2026_stage_references": suspicious,
        "blocking_rule_count": len(reasons),
        "blocking_rule_codes": sorted(reasons),
        "writer_exclusion_verified": 0,
        "cross_workflow_lock_verified": 0,
        "atomic_cas_verified": 0,
        "approval_authenticated": 0,
        "stage_writes": 0,
        "cursor_writes": 0,
        "canonical_writes": 0,
    }


def scan(root):
    root = Path(root).resolve()
    workflow_dir = root / ".github" / "workflows"
    if not workflow_dir.is_dir():
        raise ValueError("REPLAY_WORKFLOW_DIRECTORY_MISSING")
    workflows = {
        f.name: f.read_text(encoding="utf-8")
        for f in sorted(workflow_dir.iterdir())
        if f.is_file() and f.suffix in (".yml", ".yaml")
    }
    scripts = {
        f: (root / f).read_text(encoding="utf-8")
        for f in (SAFE_WRITER, LEGACY_WRITER)
    }
    return assess(workflows, scripts)


def main():
    try:
        result = scan(Path(__file__).resolve().parents[2])
    except (ValueError, OSError):
        result = {
            "status": "BLOCK",
            "error_code": "REPLAY_STATIC_AUDIT_UNAVAILABLE",
            "writer_exclusion_verified": 0,
            "stage_writes": 0,
        }
        print("QQ_REPLAY_WRITER_AUDIT=" + json.dumps(result, sort_keys=True))
        return 2
    print("QQ_REPLAY_WRITER_AUDIT=" + json.dumps(result, sort_keys=True))
    return 1 if result["blocking_rule_count"] else 0


if __name__ == "__main__":
    sys.exit(main())
