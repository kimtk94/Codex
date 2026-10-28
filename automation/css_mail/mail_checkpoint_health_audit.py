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
    ingest=read(s,"CSS Git Ingest","A1:R100000")
    legacy=read(s,"All Emails","A1:J50000")
    if not ingest or ingest[0][:5]!=["ingest_key","message_id","imap_uid","folder","uidvalidity"]:
        raise RuntimeError("INGEST_SCHEMA_MISMATCH")
    if not legacy or str(legacy[0][0]).lower() not in ("uid","imap_uid"):
        # A legacy header may differ; continue when timestamps are structurally valid.
        if len(legacy[0])<10: raise RuntimeError("LEGACY_SCHEMA_MISMATCH")
    entries=[r for r in ingest[1:] if len(r)>5 and r[0]]
    olds=[r for r in legacy[1:] if len(r)>2 and r[0]]
    keys=[r[0] for r in entries]
    duplicates=len(keys)-len(set(keys))
    malformed=sum(not re.fullmatch(r"[^|]+\\|[0-9]+\\|[0-9]+",r[0]) for r in entries)
    newest_ingest=max((t for r in entries if (t:=parse_time(r[14] if len(r)>14 else ""))),default=None)
    newest_legacy=max((t for r in olds if (t:=parse_time(r[2]))),default=None)
    now=dt.datetime.now(dt.timezone.utc)
    ingest_age=(now-newest_ingest).total_seconds()/3600 if newest_ingest else None
    legacy_age=(now-newest_legacy).total_seconds()/3600 if newest_legacy else None
    result={"ingest_rows":len(entries),"legacy_rows":len(olds),"ingest_last_fetch_utc":str(newest_ingest),
            "legacy_last_mail_utc":str(newest_legacy),"ingest_fetch_age_h":round(ingest_age,1) if ingest_age is not None else None,
            "legacy_mail_age_h":round(legacy_age,1) if legacy_age is not None else None,
            "duplicate_ingest_keys":duplicates,"malformed_ingest_keys":malformed,"limit_h":THRESHOLD_HOURS}
    print("CSS_MAIL_CHECKPOINT_HEALTH "+json.dumps(result,sort_keys=True))
    if duplicates or malformed or ingest_age is None or legacy_age is None or ingest_age>THRESHOLD_HOURS or legacy_age>THRESHOLD_HOURS:
        print("CSS_MAIL_CHECKPOINT_UNHEALTHY",file=sys.stderr)
        return 2
    print("CSS_MAIL_CHECKPOINT_HEALTH_PASS")
    return 0
if __name__=="__main__":
    try:sys.exit(audit())
    except Exception as e:
        print("CSS_MAIL_CHECKPOINT_AUDIT_ERROR "+type(e).__name__+":"+str(e)[:160],file=sys.stderr)
        sys.exit(1)
