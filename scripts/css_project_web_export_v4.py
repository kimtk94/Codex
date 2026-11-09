#!/usr/bin/env python3
"""Private Google Sheet mirror -> versioned WEB_EXPORT_V4 projection.

This module makes no claim about original Feishu/QQ freshness. It writes to
one owned destination tab only and must verify source and sink independently.
No customer rows, credentials or exception messages are printed in CI.
"""
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import json
import os
import sys
from urllib.parse import quote

SOURCE_BOOK = "1Fo0Tc6PQ3Ek0-33lmegScM_z8ST-ShUYQ0K3kD4PqnI"
DEST_BOOK = "1753nq7_zX-6ae7srmJryHrFECEG5L9Mjf7JvjrbFxVY"
DEST_TAB = "WEB_EXPORT_V4"
KST = dt.timezone(dt.timedelta(hours=9))
COLUMNS = [
    "project_subproject_id", "amea", "institution", "service", "feishu_status",
    "css_legacy_stage", "css_legacy_last_email", "sample_count",
    "feishu_expected_completion", "expected_revenue_month", "invoice_count",
    "billing_classification", "mirror_source_status", "source_manifest_date",
]
ALLOWED_STATUS = "MIRROR_ONLY_NOT_ORIGINAL_FEISHU_VERIFIED"
MAX_ROWS = 1500
MAX_SYNC_HOURS = 48

def clean(v):
    return "" if v is None else str(v).strip()

def parse_kst(value):
    try:
        value = clean(value).replace(" KST", "")
        when = dt.datetime.fromisoformat(value)
        return when if when.tzinfo else when.replace(tzinfo=KST)
    except ValueError:
        return None

def build_snapshot(lifecycle, manifest, mail, now):
    if not lifecycle or lifecycle[0][:7] != [
        "Project / Sub-project", "AMEA", "Institution", "Customer", "Service",
        "Feishu Status (latest)", "CSS Stage (legacy)"]:
        raise ValueError("LIFECYCLE_SCHEMA_UNEXPECTED")
    if not 1 <= len(lifecycle) - 1 <= MAX_ROWS:
        raise ValueError("LIFECYCLE_SIZE_OUT_OF_RANGE")
    online = [r for r in manifest[1:] if r and clean(r[0]) == "Online-Project"]
    if len(online) != 1 or len(online[0]) < 5:
        raise ValueError("FEISHU_MANIFEST_UNVERIFIED")
    source_date = clean(online[0][1])
    sync_at = parse_kst(online[0][2])
    try:
        dt.date.fromisoformat(source_date)
    except ValueError as exc:
        raise ValueError("SOURCE_DATE_INVALID") from exc
    if sync_at is None or (now - sync_at).total_seconds() / 3600 > MAX_SYNC_HOURS:
        raise ValueError("FEISHU_MIRROR_SYNC_STALE")
    if sync_at > now + dt.timedelta(minutes=10):
        raise ValueError("FEISHU_MIRROR_SYNC_IN_FUTURE")
    if not mail or len(mail[0]) < 2 or len(mail) < 2:
        raise ValueError("MAIL_MIRROR_SOURCE_UNAVAILABLE")
    mail_at = parse_kst(mail[1][0])
    if mail_at is None or (now - mail_at).total_seconds() / 3600 > MAX_SYNC_HOURS:
        raise ValueError("MAIL_MIRROR_SYNC_STALE")
    if clean(mail[1][1]) not in ("WINDOW_CAUGHT_UP", "WINDOW_PARTIAL", "PARTIAL", "WINDOW_PENDING"):
        raise ValueError("MAIL_MIRROR_STATUS_UNKNOWN")
    unique = set()
    rows = []
    for item in lifecycle[1:]:
        key = clean(item[0]) if item else ""
        if not key or key in unique:
            raise ValueError("DUPLICATE_OR_MISSING_PROJECT_ID")
        unique.add(key)
        at = lambda i: clean(item[i]) if len(item) > i else ""
        rows.append([
            key, at(1), at(2), at(4), at(5), at(6), at(8),
            at(9), at(11), at(12), at(14), at(16),
            ALLOWED_STATUS, source_date,
        ])
    if int(clean(online[0][4])) < 1:
        raise ValueError("FEISHU_MANIFEST_EMPTY")
    content_hash = hashlib.sha256(json.dumps(rows, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    stamp = now.astimezone(KST).isoformat(timespec="seconds")
    header = [
        "WEB_EXPORT_V4", "MIRROR_ONLY", "source_sheet", "SFDC_Automation_Followup_2026",
        "feishu_source_date", source_date, "feishu_mirror_synced_at", sync_at.isoformat(),
        "mail_mirror_updated_at", mail_at.isoformat(), "sink_generated_at", stamp,
        "projects", str(len(rows)), "sha256", content_hash,
    ]
    return [header, COLUMNS] + rows, {
        "status": "MIRROR_READY_NOT_ORIGINAL_PROOF",
        "source_project_count": len(rows),
        "source_unique_project_ids": len(unique),
        "source_feishu_manifest_rows": int(clean(online[0][4])),
        "source_manifest_date": source_date,
        "source_mirror_sync_at": sync_at.isoformat(),
        "mail_mirror_updated_at": mail_at.isoformat(),
        "sha256": content_hash,
        "source_access": "PASS_MIRROR",
        "original_feishu_authenticated": False,
        "original_qq_authenticated": False,
        "financial_actual_certified": False,
    }

def encode_range(tab, range_part):
    return quote("'" + tab.replace("'", "''") + "'!" + range_part, safe="!'")

def session_from_secret():
    from google.oauth2.service_account import Credentials
    from google.auth.transport.requests import AuthorizedSession
    raw = os.getenv("GCP_SERVICE_ACCOUNT_JSON", "")
    if not raw:
        raise RuntimeError("MISSING_GOOGLE_AUTH")
    try:
        credentials = json.loads(raw)
    except ValueError:
        credentials = json.loads(base64.b64decode(raw))
    c = Credentials.from_service_account_info(credentials, scopes=[
        "https://www.googleapis.com/auth/spreadsheets"])
    return AuthorizedSession(c)

def request_json(session, method, url, **kwargs):
    response = session.request(method, url, timeout=55, **kwargs)
    response.raise_for_status()
    return response.json()

def fetch_source(session):
    prefix = "https://sheets.googleapis.com/v4/spreadsheets/" + SOURCE_BOOK
    metadata = request_json(session, "GET", prefix, params={
        "fields": "sheets(properties(title,gridProperties(rowCount)))"})
    sheets = {s["properties"]["title"]:s["properties"]["gridProperties"]["rowCount"]
              for s in metadata.get("sheets", [])}
    needed = {"BI Project Lifecycle Overview", "Feishu Source Manifest", "CSS Mail Backfill Status"}
    if not needed.issubset(sheets):
        raise ValueError("SOURCE_TABS_MISSING")
    count = sheets["BI Project Lifecycle Overview"]
    if count < 2 or count > 3000:
        raise ValueError("SOURCE_GRID_OUT_OF_BOUNDS")
    def read(tab, rng):
        return request_json(session, "GET", prefix + "/values/" + encode_range(tab, rng)).get("values", [])
    return (read("BI Project Lifecycle Overview", f"A1:Q{count}"),
            read("Feishu Source Manifest", "A1:G25"),
            read("CSS Mail Backfill Status", "A1:L5"))

def write_and_verify(session, table):
    prefix = "https://sheets.googleapis.com/v4/spreadsheets/" + DEST_BOOK
    meta = request_json(session, "GET", prefix, params={
        "fields": "sheets(properties(title,sheetId,gridProperties(rowCount,columnCount)))"})
    tab = next((s for s in meta.get("sheets", []) if s["properties"]["title"] == DEST_TAB), None)
    if tab is None:
        request_json(session, "POST", prefix + ":batchUpdate", json={
            "requests": [{"addSheet": {"properties": {
                "title": DEST_TAB, "gridProperties": {"rowCount": 2000, "columnCount": 18, "frozenRowCount": 2}}}}]})
        meta = request_json(session, "GET", prefix, params={
            "fields": "sheets(properties(title,sheetId,gridProperties(rowCount,columnCount)))"})
        tab = next((s for s in meta.get("sheets", []) if s["properties"]["title"] == DEST_TAB), None)
    if not tab:
        raise RuntimeError("DESTINATION_TAB_CREATE_FAILED")
    grid = tab["properties"]["gridProperties"]
    if grid["rowCount"] < len(table) + 2 or grid["columnCount"] < 16:
        raise RuntimeError("DESTINATION_GRID_TOO_SMALL")
    # Own exactly this tab; overwrite fixed bounded range to clear stale tail rows.
    padded = table + [[""] * 16 for _ in range(max(0, min(2000,grid["rowCount"]) - len(table)))]
    target = prefix + "/values/" + encode_range(DEST_TAB, "A1:P" + str(len(padded)))
    written = request_json(session, "PUT", target, params={"valueInputOption": "RAW"}, json={
        "range": "'" + DEST_TAB + "'!A1:P" + str(len(padded)),
        "majorDimension": "ROWS", "values": padded,
    })
    if written.get("updatedRows", 0) < len(table):
        raise RuntimeError("SHORT_SINK_WRITE")
    readback = request_json(session, "GET", prefix + "/values/" +
                            encode_range(DEST_TAB, "A1:P" + str(len(table))))
    actual = readback.get("values", [])
    if len(actual) != len(table):
        raise RuntimeError("SINK_ROW_COUNT_MISMATCH")
    for before, after in zip(table, actual):
        if [clean(v) for v in before] != [clean(v) for v in after]:
            raise RuntimeError("SINK_VALUE_MISMATCH")
    return {"sink_readback": "PASS_MIRROR_ONLY", "sink_row_count":len(actual)-2,
            "sink_tab":DEST_TAB, "sink_sheet_id":tab["properties"]["sheetId"],
            "sink_url": "https://docs.google.com/spreadsheets/d/" + DEST_BOOK +
                        "/edit#gid=" + str(tab["properties"]["sheetId"])}

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="never write destination")
    options = parser.parse_args()
    now = dt.datetime.now(KST)
    try:
        ses = session_from_secret()
        table, report = build_snapshot(*fetch_source(ses), now)
        if options.dry_run:
            report["sink_readback"] = "NOT_CHECKED_DRY_RUN"
        else:
            report.update(write_and_verify(ses, table))
        report["checked_at"] = now.isoformat()
    except Exception as exc:
        report = {"status": "BLOCK", "error_type": type(exc).__name__,
                  "error_message_logged": False, "sink_readback": "NOT_VERIFIED",
                  "checked_at": now.isoformat()}
    print(json.dumps(report, sort_keys=True, ensure_ascii=True))
    return 0 if report.get("sink_readback") == "PASS_MIRROR_ONLY" or (
        options.dry_run and report.get("sink_readback") == "NOT_CHECKED_DRY_RUN") else 2

if __name__ == "__main__":
    sys.exit(main())
