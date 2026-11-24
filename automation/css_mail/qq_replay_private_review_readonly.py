#!/usr/bin/env python3
"""Read-only privacy-preserving audit of private seven-invoice review sheet.

Review selections are non-authoritative: even seven REVIEW_OK values never
approve replay, advance a cursor, create receipts or touch financial ledgers.
Only aggregate counts/statuses may leave this process in stdout/Actions.
"""
from collections import Counter
from datetime import datetime, timezone
import json
import os
import re
import urllib.parse

if __package__:
    from .qq_replay_plan_readonly import PLAN_HEADER, validate_plan
    from .qq_replay_stage_request_readonly import REQUEST_HEADER, REQUEST_TAB, assess_requests
else:
    from qq_replay_plan_readonly import PLAN_HEADER, validate_plan
    from qq_replay_stage_request_readonly import REQUEST_HEADER, REQUEST_TAB, assess_requests

DEFAULT_CSS_SOURCE_SHEET_ID = "1753nq7_zX-6ae7srmJryHrFECEG5L9Mjf7JvjrbFxVY"

HEADER = [
    "No.", "Invoice Number", "Amount KRW", "Project ID", "H Project Number",
    "PO Reference", "Original PDF Filename", "IMAP UID", "UIDVALIDITY",
    "Evidence Status", "Extracted At UTC", "Current Status",
    "Review Selection (NOT WRITE APPROVAL)", "Reviewer",
    "Reviewed At", "Review Notes",
]
EXTRACT_HEADER = (
    "invoice_number", "amount_krw", "project_id", "h_project_number",
    "po_reference", "attachment_filename", "imap_uid", "validation_status",
    "extracted_at_utc", "ingest_key",
)
DECISIONS = ("HOLD", "REVIEW_OK", "REJECT")
REVIEW_TITLE = "QQ 2026 세금계산서 누락 7건 — 개별 검토 (HOLD, 저장 비활성)"
SHEET_MIME = "application/vnd.google-apps.spreadsheet"


def _integer(value):
    value = str(value).strip()
    if not re.fullmatch(r"[0-9]+", value):
        return None
    n = int(value)
    return n if n > 0 else None


def _table(rows, table):
    if not rows or not isinstance(rows, list) or not isinstance(rows[0], list):
        raise ValueError("REVIEW_TABLE_UNAVAILABLE")
    header = [str(x) for x in rows[0]]
    if len(header) != len(set(header)):
        raise ValueError("REVIEW_DUPLICATE_COLUMN")
    data = []
    for raw in rows[1:]:
        if not isinstance(raw,list):
            raise ValueError("REVIEW_ROW_INVALID")
        if any(str(x).strip() for x in raw):
            data.append({head:raw[i] if i<len(raw) else "" for i,head in enumerate(header)})
    if table == "review" and header != HEADER:
        raise ValueError("REVIEW_SCHEMA_CHANGED")
    if table == "plan" and tuple(header) != PLAN_HEADER:
        raise ValueError("RECOVERY_PLAN_SCHEMA_CHANGED")
    if table == "request" and tuple(header) != REQUEST_HEADER:
        raise ValueError("RECOVERY_REQUEST_SCHEMA_CHANGED")
    return data


def review_audit(review, extracts, stage, canonical, cursors, audits):
    """Check seven identity/UID/amount bindings using private local objects.

    Every return has zero execution authority, even when all selections are
    REVIEW_OK. Do not return private invoices or their hashes in diagnostics.
    """
    if len(review)!=7:
        raise ValueError("REVIEW_SCOPE_NOT_SEVEN")
    invoices=[str(r.get("Invoice Number","")).strip() for r in review]
    if len(set(invoices))!=7 or any(not re.fullmatch(r"[0-9]{10,15}",v) for v in invoices):
        raise ValueError("REVIEW_DUPLICATE_OR_INVALID_INVOICE")
    inbox=[x for x in cursors if str(x.get("year"))=="2026"
           and str(x.get("folder","")).upper()=="INBOX"]
    scans=[x for x in audits if str(x.get("year"))=="2026"]
    if len(inbox)!=1 or len(scans)!=1 or str(scans[0].get("status"))!="SCAN_COMPLETE":
        raise ValueError("REVIEW_CURSOR_OR_AUDIT_INVALID")
    epoch=str(inbox[0].get("uidvalidity") or "")
    uid_limit=_integer(inbox[0].get("last_uid"))
    try:
        scan_time=datetime.fromisoformat(str(scans[0].get("last_run_utc")).replace("Z","+00:00"))
    except (ValueError, TypeError):
        raise ValueError("REVIEW_SCAN_TIMESTAMP_INVALID") from None
    if not epoch.isdigit() or not uid_limit or scan_time.tzinfo is None:
        raise ValueError("REVIEW_CURSOR_EPOCH_INVALID")
    extracted={}
    for row in extracts:
        n=str(row.get("invoice_number") or "").strip()
        if n in extracted:
            raise ValueError("REVIEW_DUPLICATE_SOURCE_INVOICE")
        if n:
            extracted[n]=row
    sink_ids=[]
    for rows in (stage,canonical):
        values=[str(x.get("invoice_number") or "").strip() for x in rows]
        if len(values)!=len(set(values)):
            raise ValueError("REVIEW_DUPLICATE_SINK_INVOICE")
        sink_ids.extend(values)
    sink=set(sink_ids)
    counts=Counter({x:0 for x in DECISIONS})
    matched=0
    conflict=0
    for i,row in enumerate(review,1):
        invoice=invoices[i-1]
        option=str(row.get("Review Selection (NOT WRITE APPROVAL)") or "")
        if option not in DECISIONS:
            raise ValueError("REVIEW_SELECTION_INVALID")
        counts[option]+=1
        if (str(row.get("No.")) != str(i) or
                str(row.get("Current Status")) != "HOLD" or
                invoice in sink):
            conflict+=1
            continue
        ext=extracted.get(invoice)
        if ext is None or str(ext.get("validation_status"))!="FILENAME_PARSED":
            conflict+=1
            continue
        uid=_integer(ext.get("imap_uid"))
        amount=_integer(ext.get("amount_krw"))
        if not uid or uid>uid_limit or not amount:
            conflict+=1
            continue
        try:
            extraction=datetime.fromisoformat(str(ext.get("extracted_at_utc")).replace("Z","+00:00"))
        except (ValueError, TypeError):
            conflict+=1
            continue
        if extraction.tzinfo is None or extraction>scan_time:
            conflict+=1
            continue
        comparisons=(
            (_integer(row.get("Amount KRW")), amount),
            (str(row.get("Project ID") or ""),str(ext.get("project_id") or "")),
            (str(row.get("H Project Number") or ""),str(ext.get("h_project_number") or "")),
            (str(row.get("PO Reference") or ""),str(ext.get("po_reference") or "")),
            (str(row.get("Original PDF Filename") or ""),str(ext.get("attachment_filename") or "")),
            (str(row.get("IMAP UID") or ""),str(ext.get("imap_uid") or "")),
            (str(row.get("UIDVALIDITY") or ""),epoch),
            (str(row.get("Evidence Status") or ""),str(ext.get("validation_status") or "")),
            (str(row.get("Extracted At UTC") or ""),str(ext.get("extracted_at_utc") or "")),
        )
        if any(a!=b for a,b in comparisons):
            conflict+=1
            continue
        key=str(ext.get("ingest_key") or "")
        if epoch not in key or str(uid) not in key:
            conflict+=1
            continue
        matched+=1
    return {
        "status":"HOLD",
        "review_cases":len(review),
        "source_match_count":matched,
        "source_conflict_count":conflict,
        "review_hold_count":counts["HOLD"],
        "review_ok_count":counts["REVIEW_OK"],
        "review_reject_count":counts["REJECT"],
        "authenticated_approvals":0,
        "writer_exclusion_verified":0,
        "stage_writes":0,
        "cursor_writes":0,
        "canonical_writes":0,
        "review_is_execution_approval":False,
    }


def _read(session, sheet_id, tab, end):
    target=urllib.parse.quote("'" + tab.replace("'","''") + "'!A1:"+end, safe="")
    url="https://sheets.googleapis.com/v4/spreadsheets/"+sheet_id+"/values/"+target
    res=session.get(url,params={"valueRenderOption":"UNFORMATTED_VALUE"},timeout=75)
    res.raise_for_status()
    return res.json().get("values",[])


def _dict_rows(rows, tag):
    a=_table(rows,tag)
    return a


def _discover_review_id(session):
    """Discover one *already shared* owner-side sheet by exact title, read-only.

    Never print the title-matched file ID or any Drive metadata. Fail closed on
    missing/duplicate names. This is not an authenticated case approval.
    """
    q = ("name = '" + REVIEW_TITLE.replace("\\", "\\\\").replace("'", "\\'")
         + "' and mimeType = '" + SHEET_MIME + "' and trashed = false")
    response = session.get("https://www.googleapis.com/drive/v3/files",
                           params={"q":q,"fields":"files(id,name,mimeType),nextPageToken",
                                   "pageSize":20},timeout=50)
    response.raise_for_status()
    data = response.json()
    matches=[x for x in data.get("files",[])
             if x.get("name")==REVIEW_TITLE
             and x.get("mimeType")==SHEET_MIME
             and re.fullmatch(r"[A-Za-z0-9_-]{20,128}",str(x.get("id") or ""))]
    if len(matches)!=1 or data.get("nextPageToken"):
        raise ValueError("REVIEW_DISCOVERY_NOT_UNIQUE")
    return matches[0]["id"]


def main():
    # Credential is opt-in; an unconfigured or undiscoverable private review
    # file must remain HOLD, never authorize any stage write.
    review_id=os.getenv("QQ_REPLAY_REVIEW_SHEET_ID","").strip()
    source_id=(os.getenv("CSS_SHEET_ID") or DEFAULT_CSS_SOURCE_SHEET_ID).strip()
    credential=os.getenv("CKD_DRIVE_SA_JSON","").strip()
    if not credential:
        print("QQ_PRIVATE_REVIEW_AUDIT="+json.dumps({
            "status":"HOLD","reason":"REVIEW_READER_NOT_CONFIGURED",
            "authenticated_approvals":0,"stage_writes":0,"cursor_writes":0,
            "canonical_writes":0},sort_keys=True))
        return 0
    if review_id and not re.fullmatch(r"[A-Za-z0-9_-]{20,128}",review_id):
        print("QQ_PRIVATE_REVIEW_AUDIT="+json.dumps({
            "status":"HOLD","reason":"REVIEW_ID_INVALID",
            "authenticated_approvals":0,"stage_writes":0},sort_keys=True))
        return 0
    try:
        from google.auth.transport.requests import AuthorizedSession
        from google.oauth2 import service_account
        info=json.loads(credential)
        creds=service_account.Credentials.from_service_account_info(
            info,scopes=["https://www.googleapis.com/auth/spreadsheets.readonly",
                         "https://www.googleapis.com/auth/drive.metadata.readonly"])
        session=AuthorizedSession(creds)
        if not review_id:
            review_id=_discover_review_id(session)
        rev=_dict_rows(_read(session,review_id,"건별 검토","P8"),"review")
        recovery_plan=_dict_rows(
            _read(session,review_id,"복구 행 계획 (미실행)","K8"),"plan")
        request_rows=_dict_rows(
            _read(session,review_id,REQUEST_TAB,"N8"),"request")
        source_specs=(
            ("extracts","CSS Tax Invoice Extract","L1000"),
            ("stage","QQ 2026 Invoice Backfill","K3000"),
            ("canonical","CSS Tax Invoice List","N337"),
            ("cursors","QQ Backfill Cursor","E100"),
            ("audits","QQ Backfill Audit","H100"),
        )
        values={name:_dict_rows(_read(session,source_id,tab,end),"source")
                for name,tab,end in source_specs}
        result=review_audit(rev,**values)
        result.update(validate_plan(
            recovery_plan, rev, values["extracts"],
            values["stage"], values["canonical"]))
        result.update(assess_requests(
            request_rows, rev, recovery_plan,
            datetime.now(timezone.utc)))
    except (ValueError, KeyError, RuntimeError):
        result={"status":"HOLD","reason":"REVIEW_SCHEMA_OR_DATA_INVALID",
                "authenticated_approvals":0,"stage_writes":0,"cursor_writes":0}
    except Exception:
        # Never echo API exception text, URLs, identifiers or OAuth data.
        result={"status":"HOLD","reason":"REVIEW_READ_UNAVAILABLE",
                "authenticated_approvals":0,"stage_writes":0,"cursor_writes":0}
    print("QQ_PRIVATE_REVIEW_AUDIT="+json.dumps(result,sort_keys=True))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
