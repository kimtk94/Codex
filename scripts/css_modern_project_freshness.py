#!/usr/bin/env python3
"""Read-only current CSS project mirror health. Never publish customer rows.

The retired server's CSS Project Dashboard/WEB_EXPORT is NOT a live source.
This guard checks the maintained BI Project Lifecycle Overview -> WEB_EXPORT_V4
Google Sheets mirror. It does not certify original QQ/Feishu or SFDC.
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import json
from pathlib import Path
import sys
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "masteros" / "web" / "scripts" / "css_projects_local.py"
VALID = frozenset(("PASS_MIRROR_ONLY", "PARTIAL_MIRROR", "SINK_LAG",
                   "STALE", "SOURCE_UNAVAILABLE"))
COUNTS = ("source_count", "sink_count", "source_sink_mismatch_count",
          "missing_project_count", "unexpected_project_count")
TIMES = ("checked_at", "source_synced_at", "sink_generated_at",
         "mail_mirror_updated_at", "source_manifest_date")
MAIL_WINDOWS = frozenset(("WINDOW_CAUGHT_UP", "WINDOW_PARTIAL", "PARTIAL", "WINDOW_PENDING"))
SAFE_MESSAGE = {
    "PASS_MIRROR_ONLY": "SCOPED_GOOGLE_MIRROR_PARITY_NOT_ORIGINAL_PROOF",
    "PARTIAL_MIRROR": "MAIL_WINDOW_INCOMPLETE_MIRROR_ONLY",
    "SINK_LAG": "MODERN_PROJECT_MIRROR_SINK_LAG",
    "STALE": "MODERN_PROJECT_MIRROR_STALE",
    "SOURCE_UNAVAILABLE": "MODERN_MIRROR_SOURCE_UNAVAILABLE",
}


def bounded_count(value):
    if type(value) is not int or not 0 <= value <= 1500:
        return None
    return value


def summarize(report):
    """Explicit allowlist: strip all individual project, client, and secret fields."""
    if not isinstance(report, dict):
        raise ValueError("INVALID_MIRROR_REPORT")
    state = report.get("status")
    if state not in VALID:
        raise ValueError("UNKNOWN_MIRROR_STATUS")
    # main's older local reader reports PASS_MIRROR_ONLY even if the
    # bounded mail backfill is PARTIAL. Do not depend on merging PR #806
    # first: this guard independently requires and evaluates the window.
    window = report.get("mail_window_state")
    if state != "SOURCE_UNAVAILABLE" and window not in MAIL_WINDOWS:
        raise ValueError("MAIL_WINDOW_NOT_VERIFIED")
    if state == "PASS_MIRROR_ONLY" and window != "WINDOW_CAUGHT_UP":
        state = "PARTIAL_MIRROR"
    if (report.get("original_feishu_verified") is True
            or report.get("original_qq_verified") is True
            or report.get("sfdc_save_verified") is True
            or report.get("financial_actual_certified") is True):
        raise ValueError("UNPROVEN_BUSINESS_SOURCE_CERTIFICATION")
    counts = {k: bounded_count(report.get(k)) for k in COUNTS}
    if state in ("PASS_MIRROR_ONLY", "PARTIAL_MIRROR", "SINK_LAG", "STALE"):
        if counts["source_count"] is None or counts["sink_count"] is None:
            raise ValueError("MIRROR_ROW_COUNT_UNAVAILABLE")
    if state == "PASS_MIRROR_ONLY":
        if (counts["source_count"] != counts["sink_count"]
                or not counts["source_count"]
                or any(counts[k] != 0 for k in COUNTS[2:])):
            raise ValueError("FALSE_MIRROR_PARITY")
    result = {
        "status": state,
        "diagnostic": SAFE_MESSAGE[state],
        "legacy_css_project_dashboard": "RETIRED_NOT_A_SOURCE",
        "legacy_web_export": "RETIRED_NOT_A_SOURCE",
        "project_scope": "GOOGLE_SHEET_LIFECYCLE_TO_WEB_EXPORT_V4_ONLY",
        "qq_original_source_verified": False,
        "feishu_original_source_verified": False,
        "sfdc_object_readback_verified": False,
        "business_source_sink_verification": "NOT_VERIFIED",
        "read_only": True,
        "mail_window_state": window if window in MAIL_WINDOWS else "NOT_VERIFIED",
    }
    result.update(counts)
    for key in TIMES:
        value = report.get(key)
        result[key] = value[:50] if isinstance(value, str) else None
    return result


def attach_verified_mail_window(module, report):
    """Recover the backfill window omitted by the unmerged legacy reader.

    Re-read only A2:B2, and require the same timestamp used by the first
    mirror evaluation. A concurrent row change is not a verified snapshot.
    When PR #806 is eventually merged, use its existing window field.
    """
    if not isinstance(report, dict) or report.get("status") == "SOURCE_UNAVAILABLE":
        return report
    if "mail_window_state" in report:
        return report
    client = module.session()  # Existing Google Sheets readonly scope.
    area = quote("'CSS Mail Backfill Status'!A2:B2", safe="!'")
    url = ("https://sheets.googleapis.com/v4/spreadsheets/" + module.SRC
           + "/values/" + area)
    response = client.get(url, timeout=28)
    response.raise_for_status()
    rows = response.json().get("values", [])
    if len(rows) != 1 or len(rows[0]) < 2:
        raise ValueError("MAIL_WINDOW_ROW_MISSING")
    when = module.when(rows[0][0])
    if when is None or when.isoformat() != report.get("mail_mirror_updated_at"):
        raise ValueError("MAIL_WINDOW_READ_RACE")
    result = dict(report)
    result["mail_window_state"] = rows[0][1]
    return result


def read_modern_mirror():
    # Import by file path rather than turning the local Next.js app into a
    # server-side job. google_fetch is Google Sheets READ-ONLY and reports
    # in-memory customer rows only to summarize(), never to GitHub logs.
    if not MODULE.is_file():
        return {"status": "SOURCE_UNAVAILABLE", "error_type": "NO_LOCAL_READER"}
    spec = importlib.util.spec_from_file_location("css_projects_local", MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return attach_verified_mail_window(module, module.google_fetch())


def main():
    try:
        output = summarize(read_modern_mirror())
    except Exception as exc:
        # Error details and customer-originated messages are never persisted.
        output = summarize({"status": "SOURCE_UNAVAILABLE"})
        output["diagnostic"] = "GUARD_EXECUTION_"+(
            "INVALID_MIRROR_CONTRACT" if isinstance(exc, ValueError)
            else "READ_UNAVAILABLE")
    output["monitor_checked_at_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
    print(json.dumps(output, sort_keys=True, ensure_ascii=True))
    return 0 if output["status"] == "PASS_MIRROR_ONLY" else 2


if __name__ == "__main__":
    sys.exit(main())
