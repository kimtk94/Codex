#!/usr/bin/env python3
"""Fail closed when QQ mail staging is stale; never report PASS on a stale feed."""
import datetime as dt
import os
import sys
import incremental_sync as css
from unified_followup_sync import DST, SRC, KST, get, put, ensure

def parse_time(value):
    try:
        return dt.datetime.fromisoformat(str(value).strip().replace("Z","+00:00")).astimezone(dt.timezone.utc)
    except (ValueError, TypeError):
        return None

def main():
    s=css.authorize()
    rows=get(s,SRC,"CSS Git Ingest","F1:O100000")
    now_utc=dt.datetime.now(dt.timezone.utc)
    # Column F: original message date; O: ingestion timestamp.
    original=[parse_time(r[0]) for r in rows[1:] if len(r)>0 and r[0]]
    fetched=[parse_time(r[9]) for r in rows[1:] if len(r)>9 and r[9]]
    original=[v for v in original if v and v<=now_utc+dt.timedelta(days=1)]
    fetched=[v for v in fetched if v and v<=now_utc+dt.timedelta(days=1)]
    last_original=max(original,default=None)
    last_fetched=max(fetched,default=None)
    # A successful empty poll must not mask a stale source: alert if the
    # newest original message itself is more than 48 hours old.
    max_age=int(os.environ.get("CSS_MAIL_STALE_HOURS","48"))
    if not 1<=max_age<=168:
        raise ValueError("CSS_MAIL_STALE_HOURS must be 1..168")
    age=(now_utc-last_original).total_seconds()/3600 if last_original else float("inf")
    status="PASS" if age<=max_age else "FAIL_STALE"
    stamp=now_utc.astimezone(KST).strftime("%Y-%m-%d %H:%M:%S KST")
    desc=("latest_message="+(last_original.isoformat() if last_original else "NONE")+
          " latest_ingest="+(last_fetched.isoformat() if last_fetched else "NONE")+
          " age_hours="+(str(round(age,1)) if last_original else "unknown")+
          " stale_threshold_hours="+str(max_age))
    ensure(s,DST,"Automation Health")
    put(s,DST,"Automation Health","A5",[["CSS Mail",stamp,status,desc]])
    print("CSS_MAIL_HEALTH_"+status+" "+desc,flush=True)
    if status!="PASS":
        sys.exit(1)

if __name__=="__main__":
    main()
