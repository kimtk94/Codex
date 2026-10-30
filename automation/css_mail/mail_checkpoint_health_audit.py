#!/usr/bin/env python3
"""Read-only freshness and checkpoint consistency audit across QQ mail staging and legacy."""
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

def read(s,tab,area):
    rng=urllib.parse.quote("'"+tab+"'!"+area,safe="")
    resp=s.get("https://sheets.googleapis.com/v4/spreadsheets/"+BOOK+"/values/"+rng,timeout=75)
    resp.raise_for_status()
    return resp.json().get("values",[])

def parse_time(raw):
    try:
        return dt.datetime.fromisoformat(str(raw).replace("Z","+00:00")).astimezone(dt.timezone.utc)
    except (ValueError,TypeError):
        return None

def audit():
    cred=service_account.Credentials.from_service_account_info(json.loads(os.environ["CKD_DRIVE_SA_JSON"]),
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
    s=AuthorizedSession(cred)
    # Narrow column reads avoid fetching customer subjects/recipients/attachments.
    ingest_keys=read(s,"CSS Git Ingest","A1:A50000")
    ingest_fetch=read(s,"CSS Git Ingest","O1:O50000")
    ingest_received=read(s,"CSS Git Ingest","F1:F50000")
    legacy_uids=read(s,"All Emails","A1:A45000")
    legacy_dates=read(s,"All Emails","C1:C45000")
    if not ingest_keys or ingest_keys[0]!=["ingest_key"]:
        raise RuntimeError("INGEST_SCHEMA_MISMATCH")
    if not legacy_uids or legacy_uids[0][0].lower()!="uid":
        raise RuntimeError("LEGACY_SCHEMA_MISMATCH")
    keys=[r[0] for r in ingest_keys[1:] if r and r[0]]
    duplicates=len(keys)-len(set(keys))
    malformed=sum(not re.fullmatch(r"[^|]+\|[0-9]+\|[0-9]+",key) for key in keys)
    newest_ingest=max((t for r in ingest_fetch[1:] if r and (t:=parse_time(r[0]))),default=None)
    newest_legacy=max((t for r in legacy_dates[1:] if r and (t:=parse_time(r[0]))),default=None)
    stage_times=[t for r in ingest_received[1:] if r for t in [parse_time(r[0])] if t]
    newest_stage=max(stage_times,default=None)
    earliest_stage=min(stage_times,default=None)
    now=dt.datetime.now(dt.timezone.utc)
    ingest_age=(now-newest_ingest).total_seconds()/3600 if newest_ingest else None
    legacy_age=(now-newest_legacy).total_seconds()/3600 if newest_legacy else None
    stage_age=(now-newest_stage).total_seconds()/3600 if newest_stage else None
    archive_gap=(earliest_stage-newest_legacy).total_seconds()/3600 if earliest_stage and newest_legacy else None
    entries=keys
    olds=[r[0] for r in legacy_uids[1:] if r and r[0]]
    result={"ingest_rows":len(entries),"legacy_rows":len(olds),"ingest_last_fetch_utc":str(newest_ingest),
            "legacy_last_mail_utc":str(newest_legacy),"ingest_fetch_age_h":round(ingest_age,1) if ingest_age is not None else None,
            "legacy_mail_age_h":round(legacy_age,1) if legacy_age is not None else None,
            "stage_mail_age_h":round(stage_age,1) if stage_age is not None else None,
            "archive_to_ingest_gap_h":round(archive_gap,1) if archive_gap is not None else None,
            "duplicate_ingest_keys":duplicates,"malformed_ingest_keys":malformed,"limit_h":THRESHOLD_HOURS}
    print("CSS_MAIL_CHECKPOINT_HEALTH "+json.dumps(result,sort_keys=True))
    # Legacy All Emails is an archive. Require handoff coverage, not perpetual archive writes.
    # An ingestion heartbeat alone cannot certify that new mail was actually staged.
    if (duplicates or malformed or ingest_age is None or stage_age is None or archive_gap is None
            or ingest_age>THRESHOLD_HOURS or stage_age>THRESHOLD_HOURS
            or archive_gap>THRESHOLD_HOURS or stage_age < -12):
        print("CSS_MAIL_CHECKPOINT_UNHEALTHY",file=sys.stderr)
        return 2
    print("CSS_MAIL_CHECKPOINT_HEALTH_PASS")
    return 0
if __name__=="__main__":
    try:sys.exit(audit())
    except Exception as e:
        print("CSS_MAIL_CHECKPOINT_AUDIT_ERROR "+type(e).__name__+":"+str(e)[:160],file=sys.stderr)
        sys.exit(1)
