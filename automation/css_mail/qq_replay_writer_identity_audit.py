#!/usr/bin/env python3
"""Strict owner-private Drive principal snapshot compare. GET only, always HOLD.

Never print actual email, permission ID, file ID, token or raw exception in
PUBLIC Codex logs. Matching Google Drive roles is NOT exclusive write access.
"""
from collections import Counter
import json
import os
import re
from .qq_replay_private_review_readonly import (
    DEFAULT_CSS_SOURCE_SHEET_ID, _discover_review_id, _read
)
from .qq_replay_writer_access_audit import fetch_permissions

TAB="Writer 권한 기준 (미승인)"
HEADER=("No.","Principal Email (private)","Permission Type",
        "Permission Role","Observed Baseline","Owner Review","Notes")
BASELINE_LABEL="2026-11-23 baseline"
REVIEWS=("PENDING","ACCEPT","REJECT")

def _hold(reason,**updates):
    out={
      "status":"HOLD","reason_code":reason,
      "baseline_principal_count":0,"live_principal_count":0,
      "identity_snapshot_exact_match":0,"identity_match_count":0,
      "identity_missing_count":0,"identity_unexpected_count":0,
      "owner_review_pending_count":0,"owner_review_accept_count":0,
      "owner_review_reject_count":0,
      "owner_review_authorized_execution":0,"identity_allowlist_verified":0,
      "all_external_writers_excluded":0,"actual_qq_stage_writes":0,
      "actual_cursor_writes":0,"actual_canonical_writes":0,
      "can_execute_replay":False,
    }
    out.update(updates)
    return out

def _email(x):
    if not isinstance(x,str):
        return None
    x=x.lower().strip()
    return x if re.fullmatch(r"[^@\s]+@[^@\s]+\.[a-z]{2,}",x) else None

def _rows_from_sheet(values):
    if (not isinstance(values,list) or not values or
        not isinstance(values[0],list) or tuple(values[0])!=HEADER):
        raise ValueError("PRIVATE_IDENTITY_SHEET_SCHEMA_INVALID")
    out=[]
    for row in values[1:]:
        if not isinstance(row,list) or len(row)>len(HEADER):
            raise ValueError("PRIVATE_IDENTITY_SHEET_ROW_INVALID")
        if any(str(v).strip() for v in row):
            full=row+[""]*(len(HEADER)-len(row))
            out.append(dict(zip(HEADER,full)))
    return out

def compare_identity_snapshot(snapshot,permissions):
    """Email+type+role exact match in private memory, counts only in output."""
    if not isinstance(snapshot,list) or len(snapshot)!=4:
        return _hold("PRIVATE_IDENTITY_BASELINE_INVALID")
    base=set()
    reviews=Counter()
    for i,row in enumerate(snapshot,1):
        if not isinstance(row,dict):
            return _hold("PRIVATE_IDENTITY_BASELINE_INVALID")
        email=_email(row.get("Principal Email (private)"))
        role=row.get("Permission Role")
        typ=row.get("Permission Type")
        flag=row.get("Owner Review")
        if (str(row.get("No."))!=str(i) or not email or typ!="user" or
            role not in ("owner","writer") or
            row.get("Observed Baseline")!=BASELINE_LABEL or flag not in REVIEWS):
            return _hold("PRIVATE_IDENTITY_BASELINE_INVALID")
        item=(email,typ,role)
        if item in base:
            return _hold("PRIVATE_IDENTITY_BASELINE_INVALID")
        base.add(item)
        reviews[flag]+=1
    if (len({x[0] for x in base})!=4 or
        sum(x[2]=="owner" for x in base)!=1 or
        sum(x[2]=="writer" for x in base)!=3):
        return _hold("PRIVATE_IDENTITY_BASELINE_INVALID")
    common={"baseline_principal_count":4,
            "owner_review_pending_count":reviews["PENDING"],
            "owner_review_accept_count":reviews["ACCEPT"],
            "owner_review_reject_count":reviews["REJECT"]}
    if not isinstance(permissions,list) or not 1<=len(permissions)<=1000:
        return _hold("LIVE_PERMISSION_INVENTORY_INVALID",**common)
    live=set();ids=set()
    for record in permissions:
        if not isinstance(record,dict):
            return _hold("LIVE_PERMISSION_INVENTORY_INVALID",**common)
        e=_email(record.get("emailAddress"))
        role=record.get("role");typ=record.get("type");pid=record.get("id")
        if (not e or typ!="user" or role not in ("owner","writer") or
            not isinstance(pid,str) or not pid or pid in ids or
            record.get("deleted") is True):
            return _hold("LIVE_PERMISSION_INVENTORY_INVALID",**common)
        ids.add(pid)
        item=(e,typ,role)
        if item in live:
            return _hold("LIVE_PERMISSION_INVENTORY_INVALID",**common)
        live.add(item)
    common.update({"live_principal_count":len(live),
                   "identity_match_count":len(base&live),
                   "identity_missing_count":len(base-live),
                   "identity_unexpected_count":len(live-base),
                   "identity_snapshot_exact_match":int(base==live)})
    return _hold("PRIVATE_SNAPSHOT_MATCHED_BUT_UNAPPROVED_HOLD"
                 if base==live else "WRITER_IDENTITY_DRIFT_HOLD",**common)

def main():
    secret=(os.getenv("CKD_DRIVE_SA_JSON") or "").strip()
    source=(os.getenv("CSS_SHEET_ID") or DEFAULT_CSS_SOURCE_SHEET_ID).strip()
    review=(os.getenv("QQ_REPLAY_REVIEW_SHEET_ID") or "").strip()
    if not secret or not source:
        result=_hold("PRIVATE_IDENTITY_MONITOR_NOT_CONFIGURED")
    else:
        try:
            from google.auth.transport.requests import AuthorizedSession
            from google.oauth2 import service_account
            creds=service_account.Credentials.from_service_account_info(
                json.loads(secret),
                scopes=["https://www.googleapis.com/auth/spreadsheets.readonly",
                        "https://www.googleapis.com/auth/drive.metadata.readonly"])
            sess=AuthorizedSession(creds)
            if not review:
                review=_discover_review_id(sess)
            if not re.fullmatch(r"[A-Za-z0-9_-]{20,128}",review):
                raise ValueError("PRIVATE_REVIEW_ID_INVALID")
            values=_read(sess,review,TAB,"G5")
            snapshot=_rows_from_sheet(values)
            live=fetch_permissions(sess,source)
            result=compare_identity_snapshot(snapshot,live)
        except Exception:
            result=_hold("PRIVATE_IDENTITY_MONITOR_READ_UNAVAILABLE")
    print("QQ_WRITER_IDENTITY_AUDIT="+json.dumps(result,sort_keys=True))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
