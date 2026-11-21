#!/usr/bin/env python3
"""Mirror SFDC Lead + personal QQ email evidence into a dedicated Feishu table.

No Account normalization, no telephone/visit inference, no email sending,
no SFDC writes, no deletes. Existing Feishu rows may only be updated in the
fields owned by this mirror. Default mode is read-only. Verified Lead snapshot deployment uses the guarded CI commit gate.
"""
import argparse
import base64
import datetime as dt
import json
import os
import sys
from collections import Counter

from google.oauth2 import service_account
from googleapiclient.discovery import build
from sales_home_links import API, pages, request, require, require_success, extract_token

SHEET = "1Fo0Tc6PQ3Ek0-33lmegScM_z8ST-ShUYQ0K3kD4PqnI"
TAB = "Lead My Sent Audit"
TABLE = "Lead · 메일 연락 및 Description"
FIELDS = [
    "Lead ID", "고객명", "Account (고객 입력 원문)", "Email",
    "Lead Created", "Lead Status", "Description", "Description 있음",
    "내 메일 연락 여부", "연락 구분", "생성 후 발송 횟수",
    "생성 전 발송 횟수", "최근 발송일", "메일 증거 Message-ID",
    "메일 수신 유형", "처리 방향", "메일 원본 확인시각", "Feishu 반영시각",
]
MANUAL_FIELDS = ("검토 완료", "메일 발송 예정", "재연락 필요")
SOURCE = [
    "Lead ID", "Customer", "Institution", "Email", "Created Date",
    "Lead Status", "Description", "Description Class", "My Mail Status",
    "My Sent After Lead", "My Sent Before Lead", "Last Sent Ever",
    "QQ Message-ID (Evidence)", "To / CC", "Follow-up Action",
    "Latest QQ Outbound Checked",
]

def norm(x):
    if isinstance(x, list):
        return " ".join(norm(v) for v in x).strip()
    if isinstance(x, dict):
        return str(x.get("text") or x.get("value") or "").strip()
    return str(x or "").strip()

def transform(header, rows):
    if any(x not in header for x in SOURCE):
        raise RuntimeError("LEAD_SOURCE_SCHEMA_MISSING")
    idx = {key: header.index(key) for key in SOURCE}
    desired = {}
    for row in rows:
        def cell(name):
            j = idx[name]
            return norm(row[j]) if j < len(row) else ""
        key = cell("Lead ID")
        if not key:
            continue
        if key in desired:
            raise RuntimeError("DUPLICATE_LEAD_ID")
        description = cell("Description")
        mail = cell("My Mail Status")
        if mail not in {
            "SENT_AFTER_LEAD_CONFIRMED", "SENT_BEFORE_LEAD_ONLY",
            "NO_PERSONAL_OUTBOUND_EVIDENCE"
        }:
            raise RuntimeError("UNEXPECTED_PERSONAL_MAIL_STATUS")
        try:
            after = int(cell("My Sent After Lead"))
            before = int(cell("My Sent Before Lead"))
        except ValueError:
            raise RuntimeError("INVALID_MAIL_COUNT") from None
        if after < 0 or before < 0:
            raise RuntimeError("NEGATIVE_MAIL_COUNT")
        if (mail == "SENT_AFTER_LEAD_CONFIRMED") != (after > 0):
            raise RuntimeError("MAIL_STATUS_COUNT_CONFLICT")
        if mail == "SENT_BEFORE_LEAD_ONLY" and (before <= 0 or after):
            raise RuntimeError("PRIOR_MAIL_STATUS_COUNT_CONFLICT")
        if mail == "NO_PERSONAL_OUTBOUND_EVIDENCE" and (after or before):
            raise RuntimeError("NO_EVIDENCE_COUNT_CONFLICT")
        label = ("발송 확인 (Lead 생성 후)" if after else
                 "Lead 생성 전만 발송" if before else
                 "메일 발송 증거 없음")
        action = ("기존 메일 확인 / Follow-up 검토" if after else
                  "생성 이후 메일 발송 검토" if before else
                  "Description 검토 후 첫 메일 검토" if description else
                  "공통 안내 메일 검토")
        desired[key] = {
            "Lead ID": key, "고객명": cell("Customer"),
            "Account (고객 입력 원문)": cell("Institution"),
            "Email": cell("Email"), "Lead Created": cell("Created Date"),
            "Lead Status": cell("Lead Status"), "Description": description,
            "Description 있음": "있음" if description else "없음",
            "내 메일 연락 여부": "발송 확인" if after else "미확인",
            "연락 구분": label,
            "생성 후 발송 횟수": str(after), "생성 전 발송 횟수": str(before),
            "최근 발송일": cell("Last Sent Ever"),
            "메일 증거 Message-ID": cell("QQ Message-ID (Evidence)"),
            "메일 수신 유형": cell("To / CC"),
            "처리 방향": action,
            "메일 원본 확인시각": cell("Latest QQ Outbound Checked"),
        }
    if len(desired) < 450:
        raise RuntimeError("LEAD_COUNT_UNEXPECTEDLY_SMALL")
    return desired

def assert_manual_preserved(previous, current, fields):
    """Guard user-owned checkbox values after automated source-field upserts.

    Only source-owned fields may be written by this mirror; checked user states
    must survive changes to mail evidence, Description or customer information.
    """
    if any(name in FIELDS for name in MANUAL_FIELDS):
        raise RuntimeError("MANUAL_FIELD_OWNERSHIP_CONFLICT")
    active = [name for name in MANUAL_FIELDS if name in fields]
    if any(fields[name] != 7 for name in active):
        raise RuntimeError("MANUAL_FIELD_TYPE_CHANGED")
    for key, record in previous.items():
        if key not in current:
            raise RuntimeError("LEAD_MANUAL_PREVIOUS_ROW_DISAPPEARED")
        old = record.get("fields") or {}
        after = current[key]
        for field in active:
            before_value = old.get(field)
            after_value = after.get(field)
            if type(before_value) not in (bool, type(None)):
                raise RuntimeError("MANUAL_PREVIOUS_VALUE_TYPE_INVALID")
            if type(after_value) not in (bool, type(None)):
                raise RuntimeError("MANUAL_READBACK_VALUE_TYPE_INVALID")
            if (before_value is True) != (after_value is True):
                raise RuntimeError("LEAD_MANUAL_SELECTION_OVERWRITTEN")
    return len(previous)

def sheets_data():
    raw = os.environ.get("NBA_GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if not raw:
        raise RuntimeError("GOOGLE_CREDENTIALS_MISSING")
    try:
        cfg = json.loads(raw)
    except ValueError:
        cfg = json.loads(base64.b64decode(raw))
    cred = service_account.Credentials.from_service_account_info(
        cfg, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
    api = build("sheets", "v4", credentials=cred, cache_discovery=False)
    result = api.spreadsheets().values().get(
        spreadsheetId=SHEET, range="'"+TAB+"'!A1:T12000",
        valueRenderOption="FORMATTED_VALUE").execute()
    rows = result.get("values") or []
    if not rows:
        raise RuntimeError("LEAD_SOURCE_EMPTY")
    desired = transform(rows[0], rows[1:])
    # A stale or absent mail source cannot certify 'not contacted'.
    stamps = [r.get("메일 원본 확인시각") for r in desired.values()]
    if not all(stamps):
        raise RuntimeError("MAIL_SOURCE_TIMESTAMP_MISSING")
    from dateutil.parser import isoparse
    try:
        latest = min(isoparse(s) for s in stamps)
        if latest.tzinfo is None:
            raise ValueError("No timezone")
        age = dt.datetime.now(dt.timezone.utc) - latest.astimezone(dt.timezone.utc)
    except (ValueError, TypeError):
        raise RuntimeError("MAIL_SOURCE_TIMESTAMP_INVALID") from None
    if not dt.timedelta(0) <= age <= dt.timedelta(hours=72):
        raise RuntimeError("MAIL_SOURCE_STALE")
    return desired

def auth():
    ans = request("POST", "/open-apis/auth/v3/tenant_access_token/internal",
        body={"app_id": require("FEISHU_APP_ID"),
              "app_secret": require("FEISHU_APP_SECRET")})
    return extract_token(ans)

def sync(desired, apply):
    token = auth()
    tables = {x["name"]: x["table_id"] for x in pages(API+"/tables", token)}
    tid = tables.get(TABLE)
    if not tid:
        if not apply:
            print("TABLE_MISSING_DRY_RUN=true")
            return
        ans = require_success(request("POST", API+"/tables", token=token,
            body={"table": {"name": TABLE, "default_view_name": "전체 Lead",
                "fields": [{"field_name": x, "type": 1} for x in FIELDS]}}),
            "CREATE_LEAD_TABLE")
        tid = ans.get("table_id") or (ans.get("table") or {}).get("table_id")
        if not tid:
            raise RuntimeError("CREATED_TABLE_ID_MISSING")
    root = API+"/tables/"+tid
    fields = {x["field_name"]: x["type"] for x in pages(root+"/fields", token)}
    missing = [x for x in FIELDS if x not in fields]
    if missing:
        if not apply:
            print("MISSING_FIELDS="+",".join(missing))
            return
        for key in missing:
            require_success(request("POST", root+"/fields", token=token,
                body={"field_name": key, "type": 1}), "CREATE_LEAD_FIELD")
    if any(fields.get(x,1) != 1 for x in FIELDS):
        raise RuntimeError("EXISTING_FIELD_TYPE_CONFLICT")
    existing = {}
    for row in pages(root+"/records", token):
        key = norm((row.get("fields") or {}).get("Lead ID"))
        if not key or key in existing:
            raise RuntimeError("FEISHU_LEAD_ID_INTEGRITY")
        existing[key] = row
    creates, updates = [], []
    now = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(timespec="seconds")
    for key, payload in desired.items():
        old = existing.get(key)
        if old is None:
            creates.append({"fields": dict(payload, **{"Feishu 반영시각": now})})
        elif any(norm((old.get("fields") or {}).get(k)) != v for k,v in payload.items()):
            updates.append({"record_id":old["record_id"],
                            "fields":dict(payload, **{"Feishu 반영시각":now})})
    counts = Counter(x["연락 구분"]+" / Description "+x["Description 있음"] for x in desired.values())
    print("LEAD_MAIL_DESCRIPTION_PLAN="+json.dumps({
        "total":len(desired), "existing":len(existing),
        "create":len(creates), "update":len(updates),
        "retained_not_deleted":len(set(existing)-set(desired)),
        "groups":dict(counts)},ensure_ascii=False))
    if not apply:
        print("DRY_RUN_NO_WRITES=true")
        return
    for name, items in (("batch_create",creates), ("batch_update",updates)):
        for start in range(0,len(items),100):
            require_success(request("POST",root+"/records/"+name,token=token,
                                    body={"records":items[start:start+100]}),name)
    observed = {norm((r.get("fields") or {}).get("Lead ID")):(r.get("fields") or {})
                for r in pages(root+"/records", token)}
    if any(key not in observed or any(norm(observed[key].get(k)) != v for k,v in values.items())
           for key,values in desired.items()):
        raise RuntimeError("FEISHU_LEAD_READBACK_MISMATCH")
    preserved = assert_manual_preserved(existing, observed, fields)
    print("LEAD_MANUAL_SELECTION_PRESERVED="+str(preserved), flush=True)
    print("FEISHU_LEAD_MAIL_DESCRIPTION_READBACK=PASS")

if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args=parser.parse_args()
    try:
        sync(sheets_data(),args.apply)
    except Exception as exc:
        print("LEAD_FEISHU_FAILED="+str(exc),file=sys.stderr)
        sys.exit(1)
