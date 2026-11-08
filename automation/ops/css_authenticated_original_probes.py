#!/usr/bin/env python3
"""Read-only original QQ IMAP UID vs staging and original Feishu Sheets vs mirror.

This supplements (never overrides) the 9x2 business freshness policy.
A pass certifies *only* the named projection/UID coverage, not body MIME,
Salesforce object saves, eTax issuance, paid invoices or dashboard KPIs.
No customer-level rows, keys or message content are written to logs/artifacts.
"""
import base64
import datetime as dt
import imaplib
import json
import os
import re
from pathlib import Path
import sys
import urllib.parse
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "feishu"))
sys.path.insert(0, str(ROOT / "css_mail"))

SHEET_ID = "1Fo0Tc6PQ3Ek0-33lmegScM_z8ST-ShUYQ0K3kD4PqnI"
MAIL_BOOK = "1753nq7_zX-6ae7srmJryHrFECEG5L9Mjf7JvjrbFxVY"
MAX_GRID_ROWS = 10000
SOURCE_NAMES = {
    "Payment Outstanding": "Feishu Latest Outstanding",
    "Payment Receipt": "Feishu Latest Receipts",
    "Prepayments": "Feishu Latest Prepayments",
    "eTax Invoice": "Feishu Latest eTax",
}


def clean(value):
    """Only for in-memory parity; never log value contents."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def validate_mail_coverage(folders, staged_keys):
    """Separate source access from destination completeness; do not equate no data with no access."""
    if len(folders) != 2 or set(folders) != {"INBOX", "SENT"}:
        raise ValueError("ORIGINAL_MAIL_FOLDER_COVERAGE_MISSING")
    if not isinstance(staged_keys, list) or not staged_keys:
        raise ValueError("MAIL_STAGING_NOT_READ")
    if len(staged_keys) != len(set(staged_keys)):
        raise ValueError("MAIL_STAGING_DUPLICATE_UID_KEY")
    original = set()
    recent_original = set()
    scan_original = set()
    counts = {}
    for label, entry in folders.items():
        folder, validity, uids = entry["folder"], entry["uidvalidity"], entry["uids"]
        if not folder or not str(validity).isdigit() or not isinstance(uids, list):
            raise ValueError("ORIGINAL_MAIL_UID_EVIDENCE_INVALID")
        if len(uids) != len(set(uids)) or not all(str(uid).isdigit() for uid in uids):
            raise ValueError("ORIGINAL_MAIL_UID_LIST_INVALID")
        keys = {str(folder) + "|" + str(validity) + "|" + str(uid) for uid in uids}
        if keys & original:
            raise ValueError("ORIGINAL_MAIL_UID_NAMESPACE_CONFLICT")
        for field, collector in (("recent_uids", recent_original), ("scan_uids", scan_original)):
            members = entry.get(field)
            if not isinstance(members, list) or len(members) != len(set(members)):
                raise ValueError("ORIGINAL_MAIL_WINDOW_EVIDENCE_MISSING")
            if not all(str(uid).isdigit() for uid in members):
                raise ValueError("ORIGINAL_MAIL_WINDOW_UID_INVALID")
            window = {str(folder) + "|" + str(validity) + "|" + str(uid) for uid in members}
            if not window.issubset(keys):
                raise ValueError("ORIGINAL_MAIL_WINDOW_NOT_SUBSET_OF_ALL")
            collector.update(window)
        original |= keys
        counts[label] = len(uids)
    if not original:
        raise ValueError("ORIGINAL_MAILBOX_UNEXPECTED_EMPTY")
    staged = set(staged_keys)
    missing = len(original - staged)
    recent_missing = len(recent_original - staged)
    scan_missing = len(scan_original - staged)
    return {
        "original_mailboxes_queried": 2,
        "imap_uid_count": len(original),
        "imap_by_folder": counts,
        "staging_unique_keys": len(staged_keys),
        "covered_uid_count": len(original) - missing,
        "missing_uid_count": missing,
        "uid_coverage_state": "PASS_UID_ONLY" if missing == 0 else "HISTORICAL_SINK_LAG",
        "recent_3d_uid_count": len(recent_original),
        "recent_3d_missing_uid_count": recent_missing,
        "recent_3d_state": "PASS_UID_ONLY" if recent_missing == 0 else "SINK_LAG",
        "scan_60d_uid_count": len(scan_original),
        "scan_60d_missing_uid_count": scan_missing,
        "scan_60d_state": "PASS_UID_ONLY" if scan_missing == 0 else "SINK_LAG",
        "historical_outside_60d_uid_gap": len((original - scan_original) - staged),
        "mime_body_verified": False,
        "mailbox_history_scope": "CURRENT_IMAP_INBOX_AND_SENT_ONLY",
    }


def same_rows(source, mirror):
    """Exact projected string cells with trailing empty-cell normalization."""
    if len(source) != len(mirror):
        return False
    width = max((len(r) for r in source), default=0)
    if not width or any(not isinstance(r, list) for r in source + mirror):
        return False
    def normalize(row):
        if len(row) > width and any(clean(v) for v in row[width:]):
            return None
        return tuple(clean(v) for v in row[:width]) + ("",) * max(0, width - len(row))
    return all(normalize(a) == normalize(b) for a, b in zip(source, mirror))


def compare_feishu_projection(source, mirror_meta, mirror_grid):
    """The Feishu original is independently fetched, including all projected rows."""
    identity_ok = (source.get("sheet_id") == mirror_meta.get("id") and
                   source.get("source_date") == mirror_meta.get("date"))
    count_ok = (isinstance(mirror_meta.get("rows"), int)
                and source.get("row_count") == mirror_meta["rows"])
    schema_ok = source.get("schema") == mirror_meta.get("schema")
    content_ok = same_rows(source.get("projected_grid") or [], mirror_grid)
    parity = identity_ok and count_ok and schema_ok and content_ok
    return {
        "source_date": source.get("source_date"),
        "source_rows": source.get("row_count"),
        "mirror_rows": mirror_meta.get("rows"),
        "identity_parity": identity_ok,
        "row_count_parity": count_ok,
        "schema_parity": schema_ok,
        "content_parity": content_ok,
        "status": "PASS_SNAPSHOT_PROJECTION_ONLY" if parity else "SINK_LAG",
        "invoice_issue_dates_certified": False,
        "bank_payments_certified": False,
    }


def sheets_session():
    from google.oauth2 import service_account
    from google.auth.transport.requests import AuthorizedSession
    raw = os.environ.get("CKD_DRIVE_SA_JSON", "").strip()
    if not raw:
        raise RuntimeError("GOOGLE_READ_CREDENTIALS_MISSING")
    try:
        info = json.loads(raw)
    except (ValueError, TypeError):
        info = json.loads(base64.b64decode(raw))
    creds = service_account.Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
    return AuthorizedSession(creds)


def read_range(session, book, a1):
    url = "https://sheets.googleapis.com/v4/spreadsheets/" + book + "/values/" + urllib.parse.quote(a1, safe="")
    response = session.get(url, timeout=60)
    response.raise_for_status()
    rows = response.json().get("values")
    if not isinstance(rows, list):
        raise RuntimeError("GOOGLE_SHEET_RANGE_NOT_AVAILABLE")
    return rows


def latest_ingest_checkpoint(rows):
    if not rows or rows[0] != ["fetched_at_utc"]:
        raise ValueError("MAIL_INGEST_TIMESTAMP_SCHEMA_INVALID")
    parsed = []
    for row in rows[1:]:
        if not row or not row[0]:
            continue
        try:
            moment = dt.datetime.fromisoformat(str(row[0]).replace("Z", "+00:00"))
        except ValueError:
            raise ValueError("MAIL_INGEST_TIMESTAMP_MALFORMED") from None
        if moment.tzinfo is None:
            raise ValueError("MAIL_INGEST_TIMESTAMP_NAIVE")
        parsed.append(moment.astimezone(dt.timezone.utc))
    if not parsed:
        raise ValueError("MAIL_INGEST_TIMESTAMP_MISSING")
    return max(parsed)


def parse_internaldate(items):
    """Parse IMAP INTERNALDATE only; no SUBJECT, BODY, or identifying headers."""
    for item in items or []:
        pieces = [item] if isinstance(item, bytes) else (
            [v for v in item if isinstance(v, bytes)] if isinstance(item, tuple) else [])
        for piece in pieces:
            found = re.search(rb'INTERNALDATE "([^"]+)"', piece)
            if found:
                try:
                    return dt.datetime.strptime(
                        found.group(1).decode("ascii"), "%d-%b-%Y %H:%M:%S %z"
                    ).astimezone(dt.timezone.utc)
                except (ValueError, UnicodeDecodeError):
                    raise ValueError("IMAP_INTERNALDATE_INVALID") from None
    raise ValueError("IMAP_INTERNALDATE_MISSING")


def missing_arrival_buckets(arrivals, checkpoint, margin_seconds=300):
    """Classify missing mail against last successful header fetch checkpoint."""
    if not isinstance(checkpoint, dt.datetime) or checkpoint.tzinfo is None:
        raise ValueError("LATEST_INGEST_CHECKPOINT_UNVERIFIED")
    if not isinstance(margin_seconds, int) or margin_seconds < 0:
        raise ValueError("INVALID_INGEST_MARGIN")
    out = {"before_last_ingest": 0, "after_last_ingest": 0,
           "near_ingest_boundary": 0}
    checkpoint = checkpoint.astimezone(dt.timezone.utc)
    for when in arrivals:
        if not isinstance(when, dt.datetime) or when.tzinfo is None:
            raise ValueError("ARRIVAL_TIME_UNVERIFIED")
        age = (when.astimezone(dt.timezone.utc) - checkpoint).total_seconds()
        if age < -margin_seconds:
            out["before_last_ingest"] += 1
        elif age > margin_seconds:
            out["after_last_ingest"] += 1
        else:
            out["near_ingest_boundary"] += 1
    return out


def live_mail(session):
    from incremental_sync import folder_names
    rows = read_range(session, MAIL_BOOK, "'CSS Git Ingest'!A1:A100000")
    if not rows or rows[0] != ["ingest_key"]:
        raise RuntimeError("STAGING_UID_SCHEMA_INVALID")
    keys = [str(r[0]) for r in rows[1:] if r and r[0]]
    latest_fetch = latest_ingest_checkpoint(
        read_range(session, MAIL_BOOK, "'CSS Git Ingest'!O1:O100000")
    )
    stage_keys = set(keys)
    missing_arrivals = []
    per_folder_missing = {}
    address = os.environ["CSS_QQ_MAIL_ADDRESS"]
    code = os.environ["CSS_QQ_MAIL_AUTH_CODE"]
    if not address or not code:
        raise RuntimeError("QQ_CREDENTIAL_MISSING")
    results = {}
    with imaplib.IMAP4_SSL("imap.exmail.qq.com", 993, timeout=45) as im:
        if im.login(address, code)[0] != "OK":
            raise RuntimeError("QQ_LOGIN_FAILED")
        all_folders = folder_names(im)
        sent = next((f for f, t in all_folders if "\\sent" in t or f.lower()
                     in ("sent", "sent items", "sent messages")), None)
        if not sent:
            raise RuntimeError("QQ_SENT_FOLDER_UNAVAILABLE")
        for label, folder in (("INBOX", "INBOX"), ("SENT", sent)):
            if im.select('"' + folder.replace('"', '') + '"', readonly=True)[0] != "OK":
                raise RuntimeError("QQ_FOLDER_SELECT_FAILED")
            status, values = im.response("UIDVALIDITY")
            if status != "UIDVALIDITY" or not values or not values[0]:
                raise RuntimeError("QQ_UIDVALIDITY_MISSING")
            validity = values[0].decode("ascii", "strict")
            status, result = im.uid("SEARCH", None, "ALL")
            if status != "OK" or not result or result[0] is None:
                raise RuntimeError("QQ_FULL_UID_SEARCH_FAILED")
            ids = [v.decode("ascii", "strict") for v in result[0].split()]
            since = {}
            for days, window in ((3, "recent_uids"), (60, "scan_uids")):
                cutoff = (dt.datetime.now(dt.timezone.utc) -
                          dt.timedelta(days=days)).strftime("%d-%b-%Y")
                code, reply = im.uid("SEARCH", None, "SINCE", cutoff)
                if code != "OK" or not reply or reply[0] is None:
                    raise RuntimeError("QQ_WINDOW_UID_SEARCH_FAILED")
                since[window] = [v.decode("ascii", "strict") for v in reply[0].split()]
            missing_uids = [uid for uid in since["recent_uids"]
                            if folder + "|" + validity + "|" + uid not in stage_keys]
            per_folder_missing[label] = len(missing_uids)
            if len(missing_uids) > 100:
                raise RuntimeError("RECENT_UNCOLLECTED_OVER_DIAGNOSTIC_LIMIT")
            for missing_uid in missing_uids:
                fetch_status, fetch_items = im.uid("FETCH", missing_uid, "(INTERNALDATE)")
                if fetch_status != "OK":
                    raise RuntimeError("RECENT_MISSING_UID_INTERNALDATE_FETCH_FAILED")
                missing_arrivals.append(parse_internaldate(fetch_items))
            results[label] = {"folder": folder, "uidvalidity": validity,
                              "uids": ids, **since}
        im.logout()
    report = validate_mail_coverage(results, keys)
    bucket = missing_arrival_buckets(missing_arrivals, latest_fetch)
    if sum(bucket.values()) != report["recent_3d_missing_uid_count"]:
        raise RuntimeError("RECENT_MISSING_ARRIVAL_COUNT_MISMATCH")
    report["recent_3d_arrival_vs_last_ingest"] = bucket
    report["recent_3d_missing_by_folder"] = per_folder_missing
    report["last_header_fetch_utc"] = latest_fetch.isoformat()
    report["arrival_diagnostic_scope"] = "INTERNALDATE_ONLY_NO_MESSAGE_CONTENT"
    return report


def manifest_index(rows):
    if not rows or rows[0][:7] != ["Source", "Source Date", "Synced At KST", "Source ID", "Rows", "Schema", "Meaning"]:
        raise ValueError("FEISHU_MANIFEST_HEADER_INVALID")
    found = {}
    for r in rows[1:]:
        if not r or r[0] not in SOURCE_NAMES:
            continue
        name = str(r[0])
        if name in found:
            raise ValueError("DUPLICATE_FEISHU_MANIFEST_FORMAT")
        row_count = str(r[4]) if len(r) > 4 else ""
        if not row_count.isdigit():
            raise ValueError("FEISHU_MANIFEST_COUNT_INVALID")
        found[name] = {"date": str(r[1]), "id": str(r[3]),
                       "rows": int(row_count), "schema": str(r[5])}
    if set(found) != set(SOURCE_NAMES):
        raise ValueError("FEISHU_MANIFEST_FORMAT_INCOMPLETE")
    return found


def live_feishu(session):
    from sheets_tab_discovery import api, TOKEN
    from latest_four_formats import select
    from latest_source_sync import shape, text as feishu_text
    auth = api("/open-apis/auth/v3/tenant_access_token/internal",
        payload={"app_id": os.environ["FEISHU_APP_ID"],
                 "app_secret": os.environ["FEISHU_APP_SECRET"]})
    token = auth.get("tenant_access_token")
    if not token:
        raise RuntimeError("FEISHU_AUTH_FAILED")
    root = "/open-apis/sheets/v3/spreadsheets/" + urllib.parse.quote(TOKEN, safe="")
    tabs = api(root + "/sheets/query", token).get("sheets")
    if not isinstance(tabs, list):
        raise RuntimeError("FEISHU_ORIGINAL_SHEETS_UNAVAILABLE")
    selected, _ = select(tabs, dt.datetime.now(ZoneInfo("Asia/Seoul")).date())
    if selected is None:
        raise RuntimeError("FEISHU_LATEST_FORMATS_MISSING")
    manifest = manifest_index(read_range(session, SHEET_ID, "'Feishu Source Manifest'!A1:G12"))
    evidence = {}
    for fmt in SOURCE_NAMES:
        source = selected[fmt]
        tab = next((t for t in tabs if t.get("sheet_id") == source["sheet_id"]), None)
        if not tab:
            raise RuntimeError("FEISHU_ORIGINAL_TAB_ID_MISSING")
        row_count = int((tab.get("grid_properties") or {}).get("row_count") or MAX_GRID_ROWS)
        col_count = int((tab.get("grid_properties") or {}).get("column_count") or 52)
        if row_count < 1 or row_count > MAX_GRID_ROWS or col_count > 52:
            raise RuntimeError("FEISHU_ORIGINAL_GRID_UNBOUNDED")
        span = urllib.parse.quote(source["sheet_id"] + "!A1:AZ" + str(row_count), safe="!:")
        payload = api("/open-apis/sheets/v2/spreadsheets/" + urllib.parse.quote(TOKEN, safe="") +
                      "/values/" + span, token)
        grid = (payload.get("valueRange") or {}).get("values") or []
        if not grid:
            raise RuntimeError("FEISHU_ORIGINAL_GRID_EMPTY")
        header, rows, schema = shape([[feishu_text(v) for v in r] for r in grid])
        if not rows:
            raise RuntimeError("FEISHU_ORIGINAL_RECORDS_EMPTY")
        prepared = {"sheet_id": source["sheet_id"], "source_date": source["date"],
                    "row_count": len(rows), "schema": schema,
                    "projected_grid": [header] + rows}
        mirror = read_range(session, SHEET_ID,
                     "'" + SOURCE_NAMES[fmt] + "'!A1:AZ" + str(len(rows) + 2))
        evidence[fmt] = compare_feishu_projection(prepared, manifest[fmt], mirror)
    etax_date = dt.date.fromisoformat(evidence["eTax Invoice"]["source_date"])
    local = dt.datetime.now(ZoneInfo("Asia/Seoul")).date()
    evidence["eTax Invoice"]["source_month_matches_current_month"] = (
        (etax_date.year, etax_date.month) == (local.year, local.month)
    )
    evidence["eTax Invoice"]["current_month_issuance_proven"] = False
    return {
        "source_probe": "PASS_ORIGINAL_READ",
        "mirror_projection_status": "PASS" if all(x["status"] ==
            "PASS_SNAPSHOT_PROJECTION_ONLY" for x in evidence.values()) else "SINK_LAG",
        "formats": evidence,
        "scope": "ORIGINAL_FEISHU_SHEETS_VS_GOOGLE_MIRROR_ONLY",
        "live_base_payment_certified": False,
    }


def main():
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    result = {
        "checked_utc": now,
        "no_original_message_content_logged": True,
        "qq_mail": {"status": "SOURCE_UNAVAILABLE"},
        "feishu_sheets": {"status": "SOURCE_UNAVAILABLE"},
        "sfdc_object_readback": "NOT_CHECKED",
        "domain_business_pass": False,
    }
    try:
        session = sheets_session()
    except Exception as exc:
        result["sheet_read"] = {"status": "SOURCE_UNAVAILABLE", "error_type": type(exc).__name__}
        session = None
    if session:
        for name, func in (("qq_mail", live_mail), ("feishu_sheets", live_feishu)):
            try:
                obj = func(session)
                obj["status"] = "SOURCE_PROBED"
                result[name] = obj
            except Exception as exc:
                result[name] = {"status": "SOURCE_UNAVAILABLE",
                                "error_type": type(exc).__name__}
    path = Path("audit-results/css-authenticated-original-probes.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    mail = result["qq_mail"]
    feishu = result["feishu_sheets"]
    print("CSS_ORIGINAL_SOURCE_PROBES " + json.dumps({
        "qq_source": mail.get("status"),
        "qq_uid_coverage": mail.get("uid_coverage_state", "UNVERIFIED"),
        "qq_uid_gap_count": mail.get("missing_uid_count"),
        "qq_recent_3d_uid_gap": mail.get("recent_3d_missing_uid_count"),
        "qq_recent_3d_missing_by_folder": mail.get("recent_3d_missing_by_folder"),
        "qq_recent_3d_arrival_vs_last_ingest": mail.get("recent_3d_arrival_vs_last_ingest"),
        "qq_last_header_fetch_utc": mail.get("last_header_fetch_utc"),
        "qq_recent_3d_state": mail.get("recent_3d_state", "UNVERIFIED"),
        "qq_scan_60d_uid_gap": mail.get("scan_60d_missing_uid_count"),
        "qq_scan_60d_state": mail.get("scan_60d_state", "UNVERIFIED"),
        "qq_historical_outside_60d_gap": mail.get("historical_outside_60d_uid_gap"),
        "feishu_source": feishu.get("status"),
        "feishu_mirror": feishu.get("mirror_projection_status", "UNVERIFIED"),
        "eTax_dated_source": (feishu.get("formats") or {}).get("eTax Invoice", {}).get("source_date", "UNKNOWN"),
        "sfdc_object_readback": "NOT_CHECKED",
        "customer_data_writes": 0, "customer_mail_sends": 0,
        "business_acceptance_certified": False,
    }, sort_keys=True))
    summary = os.getenv("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as out:
            out.write("## Original QQ and Feishu vs mirror (read only)\n\n")
            out.write("| Check | Original probe | Projection/readback | Business acceptance |\n")
            out.write("|---|---|---|---|\n")
            out.write("| QQ IMAP current UID sets | " + mail.get("status", "UNVERIFIED") +
                      " | recent 3d " + mail.get("recent_3d_state", "UNVERIFIED") +
                      "; last 60d " + mail.get("scan_60d_state", "UNVERIFIED") +
                      "; full history " + mail.get("uid_coverage_state", "UNVERIFIED") +
                      " | Not certified: MIME/body |\n")
            out.write("| Original Feishu dated Sheets | " + feishu.get("status", "UNVERIFIED") +
                      " | " + feishu.get("mirror_projection_status", "UNVERIFIED") +
                      " | Not certified: invoicing/payment |\n")
            out.write("| SFDC objects | Not checked | Not checked | Not certified: Save |\n\n")
            out.write("Source access failures never count as NO_NEW_DATA. See sanitized artifact.\n")
    # Reporting must succeed even if the source is unavailable; each source has
    # explicit SOURCE_UNAVAILABLE evidence and can never be promoted to PASS.
    return 0


if __name__ == "__main__":
    sys.exit(main())
