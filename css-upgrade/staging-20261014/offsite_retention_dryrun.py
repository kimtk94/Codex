#!/usr/bin/env python3
"""Read-only full rclone backup inventory + tiered retention DRY RUN.

Prints aggregates; never calls rclone delete, purge, sync, move or cleanup.
"""
import json
import re
import shutil
import subprocess
from collections import defaultdict
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo

REMOTE="gdrive:Novogene_CSS/server_backup"
RULE=re.compile(r"^(mail_sync_fast|css_project_manager)_(\d{8})_(\d{6})\.sqlite3$")
KST=ZoneInfo("Asia/Seoul")

def scan():
    b=shutil.which("rclone")
    if not b:raise RuntimeError("RCLONE_NOT_FOUND")
    cmd=[b,"lsjson",REMOTE,"--files-only","--max-depth","1","--no-mimetype","--no-modtime"]
    x=subprocess.run(cmd,text=True,capture_output=True,timeout=240)
    if x.returncode:
        raise RuntimeError("RCLONE_READ_INVENTORY_FAILED")
    files=json.loads(x.stdout)
    result=[]
    for file in files:
        name=file.get("Name") or file.get("Path") or ""
        match=RULE.fullmatch(name)
        if not match or file.get("IsDir") is True:
            continue
        kind,day,clock=match.groups()
        ts=datetime.strptime(day+clock,"%Y%m%d%H%M%S").replace(tzinfo=KST)
        n=int(file.get("Size") or 0)
        if n<=0:raise RuntimeError("INVALID_NONPOSITIVE_BACKUP_SIZE")
        result.append(dict(name=name,kind=kind,ts=ts,bytes=n))
    return result

def retention(records,now):
    chosen=set()
    future_count=0
    for kind in ("mail_sync_fast","css_project_manager"):
        rr=sorted((x for x in records if x["kind"]==kind),key=lambda x:x["ts"],reverse=True)
        if not rr:raise RuntimeError("BACKUP_TYPE_MISSING_"+kind)
        chosen.update(x["name"] for x in rr[:2])
        buckets={}
        for x in rr:
            age=now-x["ts"]
            if age.total_seconds()<0:
                chosen.add(x["name"])
                future_count+=1
                continue
            if age<=timedelta(hours=24):
                key=("hour",x["ts"].strftime("%Y-%m-%d-%H"))
            elif age<=timedelta(days=14):
                key=("day",x["ts"].strftime("%Y-%m-%d"))
            elif age<=timedelta(days=56):
                iso=x["ts"].isocalendar()
                key=("week",str(iso.year)+"-"+str(iso.week))
            elif age<=timedelta(days=183):
                key=("month",x["ts"].strftime("%Y-%m"))
            else:
                # Old backup retention cannot be validated from current runtime;
                # retain one annual anchor, do not choose a deletion automatically.
                key=("annual_anchor",x["ts"].strftime("%Y"))
            # sorted newest-first => first seen representative for each bucket
            buckets.setdefault(key,x["name"])
        chosen.update(buckets.values())
    return chosen,future_count

def main():
    rows=scan()
    if not rows:raise RuntimeError("NO_OFFSITE_BACKUPS")
    now=datetime.now(KST)
    keep,future=retention(rows,now)
    print("RCLONE_FULL_BACKUP_INVENTORY_PASS")
    print("INVENTORY_ITEMS",len(rows))
    print("BACKUP_TIMESTAMPS_IN_FUTURE",future)
    print("BACKUP_POLICY","24h hourly / 14d daily / 56d weekly / 183d monthly / older annual")
    for kind in ("mail_sync_fast","css_project_manager"):
        rr=[x for x in rows if x["kind"]==kind]
        keepers=[x for x in rr if x["name"] in keep]
        possible=[x for x in rr if x["name"] not in keep]
        unique_dates=len(set(x["ts"].date() for x in rr))
        gib=lambda group:round(sum(x["bytes"] for x in group)/(1024**3),3)
        print("TYPE",kind,"BACKUPS",len(rr),"DATES",unique_dates,
              "TOTAL_GIB",gib(rr),"PROTECT",len(keepers),"PROTECTED_GIB",gib(keepers),
              "REVIEW_COUNT",len(possible),"REVIEW_GIB",gib(possible))
        print("TYPE",kind,"OLDEST",min(x["ts"] for x in rr).strftime("%Y-%m-%d"),
              "NEWEST",max(x["ts"] for x in rr).strftime("%Y-%m-%d"))
    print("REVIEW_ONLY_NO_FILES_DELETED",True)
    print("OLDEST_BACKUPS_AND_FULL_RESTORE_REQUIRED_BEFORE_RETENTION_APPROVAL",True)

if __name__=="__main__":
    main()
