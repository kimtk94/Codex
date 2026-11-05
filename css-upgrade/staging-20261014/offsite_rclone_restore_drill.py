#!/usr/bin/env python3
"""Read-only rclone offsite backup verification for Novogene CSS.
Only copyto remote->temp, never delete/sync remote or change live DB/service.
"""
import argparse
import hashlib
import os
import re
import shutil
import sqlite3
import subprocess
import tempfile
import time
from pathlib import Path

REMOTE="gdrive:Novogene_CSS/server_backup"
PATTERNS={
    "project":re.compile(r"^css_project_manager_\d{8}_\d{6}\.sqlite3$"),
    "mail":re.compile(r"^mail_sync_fast_\d{8}_\d{6}\.sqlite3$"),
}
LIMITS={"project":(20*2**20,700*2**20),"mail":(100*2**20,2*2**30)}

def execute(args,timeout=90):
    done=subprocess.run(args,capture_output=True,text=True,timeout=timeout)
    if done.returncode:
        # Never print stderr raw; it might contain paths/tokens.
        raise RuntimeError("COMMAND_FAILED_"+args[1].replace("-","_").upper())
    return done.stdout

def checksum(path):
    d=hashlib.md5()
    with open(path,"rb") as f:
        for chunk in iter(lambda:f.read(4*2**20),b""):
            d.update(chunk)
    return d.hexdigest()

def remote_checksum(bin,filename):
    result=execute([bin,"md5sum",REMOTE+"/"+filename],timeout=120)
    for line in result.splitlines():
        m=re.match(r"^([0-9a-fA-F]{32})\s+",line)
        if m:
            return m.group(1).lower()
    raise RuntimeError("REMOTE_MD5_NOT_AVAILABLE")

def open_readonly(path):
    c=sqlite3.connect(f"file:{path.resolve()}?mode=ro",uri=True,timeout=35)
    c.execute("PRAGMA query_only=ON")
    return c

def inspect(path,kind):
    db=open_readonly(path)
    try:
        check=db.execute("PRAGMA integrity_check").fetchone()[0]
        if check!="ok":
            raise RuntimeError("SQLITE_INTEGRITY_"+kind)
        if db.execute("PRAGMA foreign_key_check").fetchone():
            raise RuntimeError("SQLITE_FOREIGN_KEY_"+kind)
        tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if (kind=="project" and len(tables)<5) or (kind=="mail" and len(tables)<1):
            raise RuntimeError("SQLITE_TOO_FEW_TABLES_"+kind)
        if kind=="project":
            mandatory=["contract_sif_skips","mail_ledger","project_timeline"]
        else:
            mandatory=[x for x in ("messages","emails","mail","mail_ledger","email_messages",
                  "mail_messages","metadata","mail_sync_state","processed_messages") if x in tables]
        if kind=="project" and not set(mandatory).issubset(tables):
            raise RuntimeError("PROJECT_SCHEMA_MISSING")
        counts={}
        for name in mandatory:
            counts[name]=db.execute('SELECT COUNT(*) FROM "'+name+'"').fetchone()[0]
        if kind=="mail" and not any(counts.values()):
            # Unknown mail schema is allowed, but we must still verify nonempty tables.
            counts["nonempty_table_count"]=sum(
                1 for name in tables if re.fullmatch("[a-zA-Z_][a-zA-Z_0-9]*",name)
                and db.execute(f'SELECT 1 FROM "{name}" LIMIT 1').fetchone()
            )
            if counts["nonempty_table_count"]<1:
                raise RuntimeError("MAIL_BACKUP_SEEMS_EMPTY")
        return len(tables),counts
    finally:
        db.close()

def run():
    p=argparse.ArgumentParser()
    p.add_argument("--max-minutes",type=float,default=13)
    args=p.parse_args()
    now=time.monotonic()
    binary=shutil.which("rclone")
    if not binary:raise RuntimeError("RCLONE_UNAVAILABLE")
    names=execute([binary,"lsf",REMOTE,"--max-depth","1","--files-only"],timeout=120).splitlines()
    selected={}
    for kind,pattern in PATTERNS.items():
        matches=sorted(x.strip() for x in names if pattern.fullmatch(x.strip()))
        if not matches:raise RuntimeError("BACKUP_MISSING_"+kind)
        selected[kind]=matches[-1]
    print("RCLONE_SELECTED_LATEST_BACKUPS_PASS",flush=True)
    print("RCLONE_PROJECT_BACKUP",selected["project"],flush=True)
    print("RCLONE_MAIL_BACKUP",selected["mail"],flush=True)
    if shutil.disk_usage("/tmp").free < 2*2**30:
        raise RuntimeError("TEMP_DISK_FREE_LESS_THAN_2GIB")
    with tempfile.TemporaryDirectory(prefix="novogene-rclone-offsite-restore-") as td:
        root=Path(td)
        for kind in ("project","mail"):
            if time.monotonic()-now>args.max_minutes*60:
                raise RuntimeError("RESTORE_TIME_BUDGET_EXCEEDED")
            name=selected[kind]
            original=root/name
            restored=root/(kind+".restored.sqlite3")
            src=REMOTE+"/"+name
            execute([binary,"copyto",src,str(original),"--retries","2",
                     "--low-level-retries","3","--stats","0","--log-level","ERROR"],timeout=720)
            n=original.stat().st_size
            lo,hi=LIMITS[kind]
            if not lo<=n<=hi:
                raise RuntimeError("OFFSITE_SIZE_OUT_OF_RANGE_"+kind)
            print("OFFSITE_DOWNLOAD_PASS",kind,"BYTES",n,flush=True)
            remote_md5=remote_checksum(binary,name)
            if remote_md5!=checksum(original):
                raise RuntimeError("OFFSITE_CHECKSUM_MISMATCH_"+kind)
            print("OFFSITE_MD5_MATCH_PASS",kind,flush=True)
            table_count,counts=inspect(original,kind)
            with open_readonly(original) as source:
                dest=sqlite3.connect(str(restored))
                try:
                    source.backup(dest,pages=4096,sleep=0.03)
                finally:
                    dest.close()
            table_count2,counts2=inspect(restored,kind)
            if table_count!=table_count2 or counts!=counts2:
                raise RuntimeError("OFFSITE_RESTORED_COUNTS_MISMATCH_"+kind)
            print("OFFSITE_RESTORE_INTEGRITY_FK_PASS",kind,flush=True)
            print("OFFSITE_RESTORED_TABLE_COUNT",kind,table_count,flush=True)
            for k,v in counts.items():
                print("OFFSITE_RESTORED_COUNT",kind,k,v,flush=True)
            original.unlink()
            restored.unlink()
        print("FULL_OFFSITE_PROJECT_MAIL_RESTORE_PASS",flush=True)
        print("NO_PRODUCTION_DB_SHEET_MAIL_OR_DRIVE_MUTATION",flush=True)
    print("TEMP_RESTORE_FILES_REMOVED_PASS",flush=True)

if __name__=="__main__":
    run()
