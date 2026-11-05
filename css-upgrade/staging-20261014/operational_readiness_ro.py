#!/usr/bin/env python3
"""Read-only CSS release operational readiness: immutable source, schedule and API budget."""
import ast,hashlib,json,os,re,shutil,subprocess,time
from pathlib import Path
SOURCE=Path("/home/taehoon/services/novogene-css/app/Novogene_Mail_CSS_DashBoard_server.py")
SHA="a7c395be330bc1128f8164cdac1d75a7c27fd35398e46ff5589271ebf0bae840"
BASE=Path("/home/taehoon/services/novogene-css")
evidence={}
assert hashlib.sha256(SOURCE.read_bytes()).hexdigest()==SHA,"SOURCE_CHANGED_FAIL_CLOSED"
evidence["source_sha_verified"]=True
root=ast.parse(SOURCE.read_bytes())
funcs={n.name:n for n in root.body if isinstance(n,ast.FunctionDef)}
target=funcs.get("sync_overview_snooze_actions")
assert target,"SNOOZE_FUNCTION_MISSING"
calls=[ast.unparse(n.func) for n in ast.walk(target) if isinstance(n,ast.Call)]
evidence["baseline_control_snapshot_calls_in_snooze_function"]=calls.count("read_overview_control_snapshots")
evidence["staged_snapshot_read_calls_per_sync"]=3
evidence["staged_additional_batch_reads_per_sync"]=2
assert evidence["baseline_control_snapshot_calls_in_snooze_function"]==1,"EXPECTED_BASELINE_READ_COUNT_CHANGED"
# Hourly service means nominal two additional Sheets API calls per cycle.
evidence["nominal_additional_reads_per_day_if_hourly"]=48
evidence["nominal_additional_reads_per_month_30d"]=1440
# Cron is read-only (no crontab edits).
cron=subprocess.run(["crontab","-l"],capture_output=True,text=True,timeout=8)
if cron.returncode==0:
    lines=[s.strip() for s in cron.stdout.splitlines()
           if s.strip() and not s.strip().startswith("#")]
    css=[re.split(r"\s+",s,maxsplit=5) for s in lines
         if "novogene" in s.lower() or "css" in s.lower()]
    evidence["crontab_css_job_count"]=len(css)
    evidence["crontab_css_cron_expressions"]=[" ".join(s[:5]) for s in css if len(s)>=6]
else:
    evidence["crontab_status"]="UNREADABLE_OR_NO_CRONTAB"
# Read process state without printing paths/secrets/args.
ps=subprocess.run(["ps","-eo","comm="],capture_output=True,text=True,timeout=8)
evidence["python_process_count"]=sum(s.strip().startswith("python") for s in ps.stdout.splitlines()) if ps.returncode==0 else None
evidence["temp_free_gib"]=round(shutil.disk_usage("/tmp").free/(1024**3),2)
assert evidence["temp_free_gib"]>0.7,"INSUFFICIENT_DISK"
# Never create production receipt table during this inspection.
import sqlite3
candidates=[BASE/"state/css_project_manager.sqlite3",BASE/"data/css_project_manager.sqlite3",
 BASE/"app/state/css_project_manager.sqlite3",BASE/"css_project_manager.sqlite3"]
db=next((x for x in candidates if x.is_file()),None)
if db:
    c=sqlite3.connect(f"file:{db.resolve()}?mode=ro",uri=True,timeout=10)
    c.execute("PRAGMA query_only=ON")
    evidence["live_receipt_table_exists"]=bool(c.execute(
       "SELECT 1 FROM sqlite_master WHERE type='table' AND name='overview_control_receipts'"
    ).fetchone())
    evidence["db_quick_check"]=c.execute("PRAGMA quick_check").fetchone()[0]
    c.close()
    assert evidence["db_quick_check"]=="ok"
else:
    evidence["db_status"]="DISCOVERY_NOT_VERIFIED"
evidence["rollout_authorized"]=False
evidence["main_executed"]=False
evidence["sources_modified"]=False
print("CSS_OPERATIONAL_READINESS_READ_ONLY",json.dumps(evidence,sort_keys=True),flush=True)
print("PRODUCTION_DEPLOYMENT_GATE_BLOCKED",True,flush=True)
