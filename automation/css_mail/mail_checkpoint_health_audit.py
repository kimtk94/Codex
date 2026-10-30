#!/usr/bin/env python3
"""Read-only QQ mail checkpoint audit: active ingest vs historical archive.

Reads only checkpoint keys and dates, never message subjects, recipients or bodies.
Source freshness, message freshness and archive-backfill completeness are distinct.
"""
import datetime as dt
import json
import os
import re
import sys
import urllib.parse
from google.oauth2 import service_account
from google.auth.transport.requests import AuthorizedSession

BOOK=os.getenv("CSS_SHEET_ID","1753nq7_zX-6ae7srmJryHrFECEG5L9Mjf7JvjrbFxVY")
THRESHOLD_HOURS=int(os.getenv("MAIL_FRESHNESS_THRESHOLD_HOURS","24"))
MESSAGE_THRESHOLD_HOURS=int(os.getenv("MAIL_MESSAGE_FRESHNESS_THRESHOLD_HOURS","48"))
CHECKPOINT=re.compile(r"[^|\\s]+\\|[0-9]+\\|[0-9]+")


def read(session,tab,area):
    rng=urllib.parse.quote("'"+tab+"'!"+area,safe="")
    resp=session.get("https://sheets.googleapis.com/v4/spreadsheets/"+BOOK+"/values/"+rng,timeout=75)
    resp.raise_for_status()
    return resp.json().get("values",[])


def parse_time(raw):
    try:
        stamp=dt.datetime.fromisoformat(str(raw).replace("Z","+00:00"))
        if stamp.tzinfo is None:
            stamp=stamp.replace(tzinfo=dt.timezone.utc)
        return stamp.astimezone(dt.timezone.utc)
    except (ValueError,TypeError,OverflowError):
        return None


def newest(rows):
    return max((t for r in rows if r and (t:=parse_time(r[0]))),default=None)


def evaluate(ingest_keys,fetch_dates,message_dates,legacy_dates,now,
             ingest_limit=THRESHOLD_HOURS,message_limit=MESSAGE_THRESHOLD_HOURS):
    if now.tzinfo is None: raise ValueError("AUDIT_NOW_REQUIRES_TIMEZONE")
    keys=[str(x) for x in ingest_keys if x]
    latest_fetch=newest(fetch_dates)
    latest_mail=newest(message_dates)
    latest_legacy=newest(legacy_dates)
    duplicate=len(keys)-len(set(keys))
    invalid=sum(CHECKPOINT.fullmatch(k) is None for k in keys)
    def hours(timestamp):
        return round((now-timestamp).total_seconds()/3600,1) if timestamp else None
    fetch_age=hours(latest_fetch)
    mail_age=hours(latest_mail)
    legacy_age=hours(latest_legacy)
    blockers=[]
    if not keys: blockers.append("ACTIVE_INGEST_EMPTY")
    if duplicate: blockers.append("DUPLICATE_ACTIVE_CHECKPOINT_KEYS")
    if invalid: blockers.append("MALFORMED_ACTIVE_CHECKPOINT_KEYS")
    if fetch_age is None or fetch_age>ingest_limit or fetch_age< -1:
        blockers.append("ACTIVE_FETCH_NOT_FRESH")
    if mail_age is None or mail_age>message_limit or mail_age< -1:
        blockers.append("ACTIVE_MAIL_NOT_FRESH")
    if latest_mail and latest_legacy and latest_mail<latest_legacy:
        blockers.append("ACTIVE_MAIL_BEHIND_LEGACY_ARCHIVE")
    warnings=[]
    if legacy_age is None:
        warnings.append("LEGACY_ARCHIVE_DATE_UNVERIFIED")
    elif legacy_age>ingest_limit:
        warnings.append("LEGACY_ARCHIVE_STALE_REVIEW")
    return {
        "source_of_truth":"CSS Git Ingest",
        "legacy_role":"archive_backfill_read_only",
        "ingest_rows":len(keys),
        "ingest_last_fetch_utc":str(latest_fetch),
        "ingest_last_mail_utc":str(latest_mail),
        "legacy_last_mail_utc":str(latest_legacy),
        "ingest_fetch_age_h":fetch_age,
        "ingest_mail_age_h":mail_age,
        "legacy_mail_age_h":legacy_age,
        "duplicate_ingest_keys":duplicate,
        "malformed_ingest_keys":invalid,
        "limit_h":ingest_limit,
        "message_limit_h":message_limit,
        "status":"BLOCKED" if blockers else ("PASS_WITH_ARCHIVE_REVIEW" if warnings else "PASS"),
        "blocking_issues":blockers,
        "nonblocking_archive_reviews":warnings,
    }


def audit():
    raw=os.environ.get("CKD_DRIVE_SA_JSON")
    if not raw:raise RuntimeError("SHEET_CREDENTIAL_MISSING")
    cred=service_account.Credentials.from_service_account_info(
        json.loads(raw),scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
    session=AuthorizedSession(cred)
    ingest_keys=read(session,"CSS Git Ingest","A1:A50000")
    ingest_fetch=read(session,"CSS Git Ingest","O1:O50000")
    ingest_received=read(session,"CSS Git Ingest","F1:F50000")
    legacy_uids=read(session,"All Emails","A1:A45000")
    legacy_dates=read(session,"All Emails","C1:C45000")
    if not ingest_keys or ingest_keys[0]!=["ingest_key"] or not ingest_fetch or ingest_fetch[0]!=["fetched_at_utc"] or not ingest_received or ingest_received[0]!=["received_at"]:
        raise RuntimeError("INGEST_SCHEMA_MISMATCH")
    if not legacy_uids or legacy_uids[0][0].lower()!="uid" or not legacy_dates or legacy_dates[0][0]!="received_at":
        raise RuntimeError("LEGACY_SCHEMA_MISMATCH")
    keys=[r[0] for r in ingest_keys[1:] if r and r[0]]
    result=evaluate(keys,ingest_fetch[1:],ingest_received[1:],legacy_dates[1:],
                    dt.datetime.now(dt.timezone.utc))
    result["legacy_rows"]=sum(bool(r and r[0]) for r in legacy_uids[1:])
    print("CSS_MAIL_CHECKPOINT_HEALTH "+json.dumps(result,sort_keys=True))
    if result["blocking_issues"]:
        print("CSS_MAIL_CHECKPOINT_UNHEALTHY",file=sys.stderr)
        return 2
    if result["nonblocking_archive_reviews"]:
        print("CSS_MAIL_LEGACY_ARCHIVE_REVIEW_REQUIRED",file=sys.stderr)
    print("CSS_MAIL_CHECKPOINT_HEALTH_PASS")
    return 0

if __name__=="__main__":
    try:sys.exit(audit())
    except Exception as exc:
        print("CSS_MAIL_CHECKPOINT_AUDIT_ERROR "+type(exc).__name__+":"+str(exc)[:160],file=sys.stderr)
        sys.exit(1)
