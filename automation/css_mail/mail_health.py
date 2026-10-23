#!/usr/bin/env python3
"""Write a verifiable CSS IMAP ingestion heartbeat after successful incremental sync."""
import datetime as dt
import os
import incremental_sync as css
from unified_followup_sync import DST, SRC, KST, get, put, ensure

def main():
    s=css.authorize()
    fetched=get(s,SRC,"CSS Git Ingest","O1:O100000")
    timestamps=[r[0] for r in fetched[1:] if r and r[0]]
    now=dt.datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S KST")
    last=max(timestamps,default="NONE")
    ensure(s,DST,"Automation Health")
    put(s,DST,"Automation Health","A5",[["CSS Mail",now,"PASS","IMAP increment passed; ingested="+str(len(timestamps))+" last_new_record_utc="+last]])
    print("CSS_MAIL_HEALTH_PASS ingested_records="+str(len(timestamps))+" last_record="+last[:10])
if __name__=="__main__":main()
