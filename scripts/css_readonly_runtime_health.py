"""Aggregate-only, read-only CSS runtime audit for the authorized server.

Never imports operational CSS/Collector, writes DB, changes services, or
prints project/customer/mail content. This verifies health indicators, not
a full G12/G16 release or mail delivery proof.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sqlite3
from pathlib import Path

ROOT = Path("/home/taehoon/services/novogene-css")
UTC = dt.timezone.utc
MAX_LOG_BYTES = 256_000
TARGETS = {
    "project_database": "css_project_manager.sqlite3",
    "mail_database": "mail_sync_fast.sqlite3",
    "project_run": "css_project_manager_run_log.json",
    "mail_run": "all_email_fast_run_log.json",
}
EXCLUDE_DIRS = frozenset({
    ".git", ".venv", "venv", "__pycache__", "node_modules",
    "backup", "backups", "archive", "archives", ".cache",
})


def parse_utc(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(UTC) if parsed.tzinfo else None


def age_minutes(value, now):
    instant = parse_utc(value)
    if instant is None:
        return None
    age = (now - instant).total_seconds() / 60
    return round(age, 2) if age >= -5 else None


def interpret_runlog(info, *, kind, now):
    """Only known aggregate fields are inspected; never echo source fields."""
    out = {"status": "UNVERIFIED", "age_minutes": None, "fresh": False}
    if not isinstance(info, dict):
        return out
    raw_time = info.get("run_at") if kind == "project" else info.get("updated_at")
    age = age_minutes(raw_time, now)
    out["age_minutes"] = age
    if age is None:
        out["status"] = "INVALID_TIMESTAMP"
        return out
    max_age = 120 if kind == "project" else 30
    out["fresh"] = age <= max_age
    if kind == "project":
        status = info.get("status")
        if status in ("SUCCESS", "FAILED", "RUNNING", "PARTIAL"):
            out["status"] = status if out["fresh"] else "STALE_" + status
        else:
            out["status"] = "UNKNOWN_STATUS"
        return out

    # Collector historically logs counts without a top-level status.
    # Consistent counts are indirect evidence of the sync stage only,
    # NOT confirmation of end-to-end mail delivery.
    keys = ("total_candidates", "processed_count", "queued_count",
            "sheet_saved_count", "pending_count", "failed_count")
    if not all(type(info.get(k)) is int and info[k] >= 0 for k in keys):
        out["status"] = "MISSING_COUNTERS"
        return out
    total, processed, queued, saved, pending, failed = (info[k] for k in keys)
    consistent = (failed == 0 and pending == 0 and
                  processed == total and queued == total and saved == total)
    if consistent:
        out["status"] = "COUNTS_CONSISTENT_NOT_EXPLICIT_SUCCESS" if out["fresh"] else "STALE_COUNTS_CONSISTENT"
    else:
        out["status"] = "COUNTS_NEED_REVIEW"
    return out


def inventory(root):
    matches = {name: [] for name in TARGETS}
    if not root.is_dir():
        return matches
    for here, dirs, files in os.walk(root, followlinks=False):
        depth = len(Path(here).relative_to(root).parts)
        dirs[:] = [] if depth >= 6 else [
            d for d in dirs if d.lower() not in EXCLUDE_DIRS
            and not (Path(here) / d).is_symlink()
        ]
        for name in TARGETS:
            if name in files:
                path = Path(here) / name
                if not path.is_symlink() and path.is_file():
                    matches[name].append(path)
    return matches


def inspect_db(path):
    if path is None:
        return {"integrity": "NOT_FOUND", "foreign_keys": "NOT_VERIFIED", "tables": None}
    try:
        con = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=3)
        try:
            con.execute("PRAGMA query_only=ON")
            integrity = con.execute("PRAGMA quick_check(1)").fetchone()[0]
            foreign = con.execute("PRAGMA foreign_key_check").fetchone()
            tables = con.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
            ).fetchone()[0]
            return {
                "integrity": "PASS" if integrity == "ok" else "FAIL",
                "foreign_keys": "PASS" if foreign is None else "FAIL",
                "tables": tables,
            }
        finally:
            con.close()
    except (OSError, sqlite3.Error, ValueError):
        return {"integrity": "NOT_VERIFIED", "foreign_keys": "NOT_VERIFIED", "tables": None}


def inspect_log(path, kind, now):
    if path is None:
        return {"status": "NOT_FOUND", "age_minutes": None, "fresh": False}
    try:
        if path.stat().st_size > MAX_LOG_BYTES:
            return {"status": "OVERSIZE", "age_minutes": None, "fresh": False}
        obj = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {"status": "UNREADABLE", "age_minutes": None, "fresh": False}
    return interpret_runlog(obj, kind=kind, now=now)


def audit(root=ROOT, now=None):
    now = now or dt.datetime.now(UTC)
    if now.tzinfo is None:
        raise ValueError("timezone-aware now required")
    now = now.astimezone(UTC)
    found = inventory(root)
    selected = {
        alias: sorted(found[name], key=lambda p: p.stat().st_mtime, reverse=True)[0]
        if found[name] else None
        for alias, name in TARGETS.items()
    }
    dbs = {
        alias: inspect_db(selected[alias])
        for alias in ("project_database", "mail_database")
    }
    runs = {
        "project": inspect_log(selected["project_run"], "project", now),
        "mail": inspect_log(selected["mail_run"], "mail", now),
    }
    runtime_healthy = (
        all(x["integrity"] == "PASS" and x["foreign_keys"] == "PASS" for x in dbs.values())
        and runs["project"]["status"] == "SUCCESS"
        and runs["mail"]["status"] == "COUNTS_CONSISTENT_NOT_EXPLICIT_SUCCESS"
    )
    return {
        "audit_utc": now.isoformat(),
        "scope": "READ_ONLY_AGGREGATES_ONLY",
        "source_file_found": {alias: selected[alias] is not None for alias in TARGETS},
        "databases": dbs,
        "run_logs": runs,
        "runtime_indicators": "CONSISTENT" if runtime_healthy else "NEEDS_REVIEW",
        "mail_delivery_confirmed": False,
        "g12_full_engine_tested": False,
        "g16_full_sink_isolation_tested": False,
        "production_deploy_authorized": False,
        "production_files_modified": False,
    }


if __name__ == "__main__":
    print(json.dumps(audit(), sort_keys=True, ensure_ascii=True, separators=(",", ":")))
