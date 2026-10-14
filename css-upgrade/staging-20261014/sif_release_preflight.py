#!/usr/bin/env python3
"""Novogene CSS SIF release preflight; READ-ONLY on operational resources.

It runs no production module import, main(), mail collector, Google Sheet
write, database transaction, deployment, systemctl start or backup deletion.
Only a disposable temp copy is patched and reverse-patched.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

EXPECTED_SHA = "a7c395be330bc1128f8164cdac1d75a7c27fd35398e46ff5589271ebf0bae840"
EXPECTED_COMBINED_SHA = "d675a490007a75c69b7fa408076879e9a52a1078bcc62a32f6fe093da0a32555"
BASE = Path("/home/taehoon/services/novogene-css")
SOURCE = BASE / "app/Novogene_Mail_CSS_DashBoard_server.py"
MANDATORY_FUNCTIONS = {
    "collect_active_prepayment_project_ids",
    "build_contract_sif_skip_history",
    "sync_overview_prepayment_snoozes",
    "overwrite_dataframe_if_changed",
}
EXPLICIT_APPROVAL = False  # Deliberately immutable and not user-controlled in this preflight.


def safe_sqlite(path: Path):
    if not path.is_file():
        raise RuntimeError("DB_NOT_FOUND")
    if not path.resolve().is_relative_to(BASE.resolve()):
        raise RuntimeError("DB_OUTSIDE_EXPECTED_DIRECTORY")
    from urllib.parse import quote
    db = sqlite3.connect("file:" + quote(str(path.resolve()), safe="/") + "?mode=ro", uri=True, timeout=25)
    db.execute("PRAGMA query_only=ON")
    return db


def discover_db():
    direct = [
        BASE / "state/css_project_manager.sqlite3",
        BASE / "data/css_project_manager.sqlite3",
        BASE / "app/state/css_project_manager.sqlite3",
        BASE / "css_project_manager.sqlite3",
    ]
    found = next((p for p in direct if p.is_file() and p.stat().st_size > 4096), None)
    if found:
        return found
    for folder in (BASE / "state", BASE / "data"):
        if folder.is_dir():
            for p in folder.glob("**/css_project_manager.sqlite3"):
                if "backup" not in str(p).lower() and p.stat().st_size > 4096:
                    return p
    raise RuntimeError("NO_CURRENT_DB")


def require(test, name, checks):
    if not test:
        raise RuntimeError(name)
    checks.append(name)
    print("PREFLIGHT_PASS", name, flush=True)


def patch_preview(original: bytes, paths: list[Path], checks: list[str]):
    with tempfile.TemporaryDirectory(prefix="css-release-preflight-") as td:
        work = Path(td)
        staged = work / "Novogene_Mail_CSS_DashBoard.py"
        staged.write_bytes(original)
        for patch in paths:
            for flags in (("--check", "--whitespace=error"), ("--whitespace=error",)):
                result = subprocess.run(["git", "apply", *flags, str(patch.resolve())],
                    cwd=td, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                    timeout=75)
                require(result.returncode == 0, "PATCH_" + patch.stem + "_" +
                        ("CHECK" if "--check" in flags else "APPLY"), checks)
        candidate = staged.read_bytes()
        require(hashlib.sha256(candidate).hexdigest() == EXPECTED_COMBINED_SHA,
                "COMBINED_CANDIDATE_SHA", checks)
        old = ast.parse(original)
        new = ast.parse(candidate)
        old_funcs = {node.name for node in ast.walk(old) if isinstance(node, ast.FunctionDef)}
        new_funcs = {node.name for node in ast.walk(new) if isinstance(node, ast.FunctionDef)}
        require(old_funcs.issubset(new_funcs), "EXISTING_FUNCTION_SET_PRESERVED", checks)
        require(MANDATORY_FUNCTIONS.issubset(new_funcs), "REQUIRED_FUNCTIONS_PRESENT", checks)
        compile(new, "staged-css.py", "exec")
        require(True, "CANDIDATE_PYTHON_COMPILABLE", checks)
        for patch in reversed(paths):
            for flags in (("-R", "--check"), ("-R",)):
                result = subprocess.run(["git", "apply", *flags, str(patch.resolve())],
                    cwd=td, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    text=True, timeout=75)
                require(result.returncode == 0, "REVERSE_" + patch.stem + "_" +
                        ("CHECK" if "--check" in flags else "APPLY"), checks)
        require(staged.read_bytes() == original, "BYTE_EXACT_ROLLBACK", checks)
        return {
            "existing_function_count": len(old_funcs),
            "candidate_sha256": EXPECTED_COMBINED_SHA,
        }


def database_audit(checks):
    db_path = discover_db()
    conn = safe_sqlite(db_path)
    try:
        require(conn.execute("PRAGMA quick_check").fetchone()[0] == "ok", "DB_READONLY_QUICK_CHECK", checks)
        require(not conn.execute("PRAGMA foreign_key_check").fetchmany(1), "DB_READONLY_FK_CHECK", checks)
        table_names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        required = {"contract_sif_skips","overview_project_snoozes","project_timeline","mail_ledger"}
        require(required.issubset(table_names), "DB_SCHEMA_REQUIRED_TABLES", checks)
        total, active = conn.execute("SELECT COUNT(*), COALESCE(SUM(is_active),0) FROM contract_sif_skips").fetchone()
        modes = dict(conn.execute("SELECT LOWER(COALESCE(mode,'')), COUNT(*) "
                                  "FROM overview_project_snoozes GROUP BY LOWER(COALESCE(mode,''))"))
        snooze_total = sum(modes.values())
        # Extract ONLY aggregate counts. Never print customer names, emails, or IDs.
        require(total >= 5 and active >= 5, "HISTORY_ACTIVE_STATE_STILL_PRESENT", checks)
        return {"tables":len(table_names),"skip_total":int(total),"skip_active":int(active),
                "overview_snooze_total":snooze_total,
                "overview_modes":modes,
                "mail_ledger_rows":conn.execute("SELECT COUNT(*) FROM mail_ledger").fetchone()[0],
                "timeline_rows":conn.execute("SELECT COUNT(*) FROM project_timeline").fetchone()[0]}
    finally:
        conn.close()


def process_telemetry():
    result = {"css_processes":None,"collector_processes":None,
              "systemd_timer_status":"NOT_VERIFIED","css_schedule_lines":None,
              "free_temp_gib":round(shutil.disk_usage("/tmp").free / (1024**3),2)}
    try:
        proc = subprocess.run(["ps","-eo","args"],capture_output=True,text=True,timeout=6)
        if proc.returncode == 0:
            lines=[line.lower() for line in proc.stdout.splitlines()]
            result["css_processes"] = sum("novogene_mail_css_dashboard" in s for s in lines)
            result["collector_processes"] = sum("novogene_mail_collector" in s for s in lines)
    except Exception:
        pass
    try:
        result["systemd_timer_status"] = ("READABLE" if subprocess.run(
            ["systemctl","--user","list-timers","--all","--no-pager","--no-legend"],
            capture_output=True,text=True,timeout=8).returncode == 0 else "UNAVAILABLE")
    except Exception:
        pass
    lines = 0
    for root in (Path("/etc/cron.d"),Path("/home/taehoon/services/novogene-css")):
        if root.is_dir():
            files = list(root.glob("*.cron")) + list(root.glob("*.timer"))
            for path in files[:50]:
                try:
                    lines += sum("novogene" in line.lower() for line in path.read_text(errors="replace").splitlines())
                except Exception:
                    pass
    result["css_schedule_lines"] = lines
    return result


def main():
    args = argparse.ArgumentParser()
    args.add_argument("--first",required=True,type=Path)
    args.add_argument("--second",required=True,type=Path)
    args.add_argument("--third",required=True,type=Path)
    ns = args.parse_args()
    checks=[]
    require(SOURCE.is_file(),"PRODUCTION_SOURCE_EXISTS",checks)
    original = SOURCE.read_bytes()
    require(hashlib.sha256(original).hexdigest()==EXPECTED_SHA,"LIVE_SOURCE_EXPECTED_SHA",checks)
    require(b"v8.92.1-server-local-adc" in original,"LIVE_RUNTIME_VERSION",checks)
    patches=patch_preview(original,[ns.first,ns.second,ns.third],checks)
    db = database_audit(checks)
    telemetry = process_telemetry()
    require(hashlib.sha256(SOURCE.read_bytes()).hexdigest()==EXPECTED_SHA,
            "PRODUCTION_SOURCE_UNMODIFIED",checks)
    require(not EXPLICIT_APPROVAL,"PRODUCTION_DEPLOYMENT_REFUSED",checks)
    # Timestamp is UTC, server's local timezone is intentionally not assumed.
    report = {"timestamp_utc":datetime.now(timezone.utc).isoformat(),
              "checks_passed":len(checks),"checks":checks,
              "candidate":patches,"database_readonly":db,
              "runtime_readonly":telemetry,
              "deployment_eligibility":"BLOCKED_PENDING_EXPLICIT_AUTHORIZATION",
              "source_modified":False,"database_modified":False,
              "production_sheet_accessed":False,"mail_sent":False,
              "backup_deleted":False}
    print("CSS_RELEASE_PREFLIGHT_JSON",json.dumps(report,ensure_ascii=False,sort_keys=True),flush=True)
    print("NO_PRODUCTION_MUTATIONS",True,flush=True)


if __name__=="__main__":
    main()
