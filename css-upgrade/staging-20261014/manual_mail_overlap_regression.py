#!/usr/bin/env python3
"""Synthetic mail/manual/Prepayment race and replay analysis against real CSS functions.
No real CSS main import, Google Sheets, mail, production SQLite, or service writes.
"""
import argparse, ast, hashlib, json, multiprocessing, sqlite3, subprocess, tempfile, time
from pathlib import Path
from zoneinfo import ZoneInfo
import pandas as pd

ORIGINAL_SHA="a7c395be330bc1128f8164cdac1d75a7c27fd35398e46ff5589271ebf0bae840"
PREVIOUS_SHA="851469d0aa53757fd55d5d31357d06068952d3983e79d8ee8b2d15ccb2cbf4fb"
TZ=ZoneInfo("Asia/Seoul")
CHECKS=[]

def check(ok,name):
    if not ok:
        raise AssertionError(name)
    CHECKS.append(name)
    print("COLLISION_PASS",name,flush=True)

def stage(src,patches,directory):
    original=Path(src).read_bytes()
    check(hashlib.sha256(original).hexdigest()==ORIGINAL_SHA,"ORIGINAL_SOURCE_SHA")
    out=Path(directory)/"Novogene_Mail_CSS_DashBoard.py"
    out.write_bytes(original)
    check(len(patches)==6,"SIX_PATCH_CANDIDATE")
    for n,patch in enumerate(patches,1):
        for args in (("--check",),()):
            p=subprocess.run(["git","apply",*args,str(Path(patch).resolve())],cwd=directory,
                  capture_output=True,text=True,timeout=90)
            check(p.returncode==0,"PATCH_"+str(n)+"_"+("CHECK" if args else "APPLY"))
        if n==4:
            check(hashlib.sha256(out.read_bytes()).hexdigest()==PREVIOUS_SHA,
                  "STAGED_4_PATCH_SHA")
    data=out.read_bytes()
    print("STAGED_6_PATCH_SHA256",hashlib.sha256(data).hexdigest(),flush=True)
    ast.parse(data)
    return data,original,out

def extract(data):
    root=ast.parse(data)
    names=("overview_mail_marker","_overview_control_rows_from_values",
       "read_overview_control_snapshots","_upsert_overview_snooze",
       "_sync_overview_snooze_actions_from_records",
       "sync_overview_snooze_actions","sync_overview_prepayment_snoozes")
    funs={n.name:n for n in root.body if isinstance(n,ast.FunctionDef)}
    check(all(n in funs for n in names),"REAL_SYNCHRONIZATION_FUNCTIONS_FOUND")
    ns={
       "pd":pd,"KST":TZ,
       "OVERVIEW_PRIORITY_HEADER_ROW":10,"OVERVIEW_PRIORITY_DATA_START_ROW":11,
       "OVERVIEW_PRIORITY_ROWS":20,"OVERVIEW_SNOOZE_HEADER_ROW":41,
       "OVERVIEW_SNOOZE_DATA_START_ROW":42,
       "OVERVIEW_SNOOZE_MANAGEMENT_ROWS":40,
       "OVERVIEW_PREPAYMENT_COLUMN":"Prepayment",
       "OVERVIEW_SNOOZE_COLUMNS": [
           "project_id","institution","customer_name","service","mode",
           "hold_until","baseline_mail_marker","current_mail_marker",
           "latest_email_at","status","created_at","updated_at"],
       "CLOSED_PROJECT_STAGES":{"Completed","Invoice issued","Project finished","Terminated"},
    }
    ns.update({
       "clean_text":lambda v:"" if v is None else str(v).strip(),
       "dataframe_row_text":lambda row,key:str(row.get(key,"") or "").strip(),
       "iter_dataframe_records":lambda df:df.to_dict(orient="records"),
       "safe_int":lambda v:int(v) if str(v).strip().isdigit() else None,
       "checkbox_is_checked":lambda v:str(v).strip().lower() in {"true","1","yes","y"},
       "project_customer_name":lambda *a:"",
    })
    for n in names:
        exec(compile(ast.Module(body=[funs[n]],type_ignores=[]),
             "actual-css-"+n,"exec"),ns)
    return ns

class FakeSheet:
    def __init__(self):
        self.priority=[]
        self.management=[]
        self.fail=False
        self.incorrect_response=False
        self.calls=0
    def batch_get(self,ranges,**kwargs):
        self.calls+=1
        if self.fail:
            raise RuntimeError("Synthetic sheet read failure")
        h1=["AMEA Project","Normal Action","Hold Days","Mail Marker","Prepayment"]
        h2=["AMEA Project","Action"]
        result=[
            [h1]+[[str(record.get(k,"")) for k in h1] for record in self.priority],
            [h2]+[[str(record.get(k,"")) for k in h2] for record in self.management]
        ]
        return result[:1] if self.incorrect_response else result

def connect():
    conn=sqlite3.connect(":memory:")
    conn.execute("""CREATE TABLE overview_project_snoozes(
        project_id TEXT PRIMARY KEY, mode TEXT NOT NULL, hold_until TEXT,
        baseline_mail_marker TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""")
    conn.execute("""CREATE TABLE overview_prepayment_requests(
        project_id TEXT PRIMARY KEY, created_at TEXT, updated_at TEXT)""")
    return conn

def board(pid,mail="A",stage="SIF requested"):
    return pd.DataFrame([{
       "project_id":pid,"latest_uid":mail,"email_count":1,
       "latest_email_at":"2026-10-15T08:00:00+09:00",
       "current_stage":stage,"institution":"Synthetic Univ",
       "customer_name":"SYNTHETIC_PI","service":"mRNA-Seq",
       "project_description":"TEST ONLY"}])

def row(con,pid):
    return con.execute("""SELECT mode,hold_until,baseline_mail_marker,
                                  created_at,updated_at FROM overview_project_snoozes
                           WHERE project_id=?""",(pid,)).fetchone()

def two_process_manual_worker(dbpath,pid,mode,start_signal,lock_ready,actual_upsert,now_text):
    """Second process uses a DIFFERENT SQLite connection and real snooze writer."""
    if not start_signal.wait(timeout=8):
        raise RuntimeError("worker not started")
    second=sqlite3.connect(dbpath,timeout=5)
    try:
        second.execute("PRAGMA busy_timeout=5000")
        second.execute("BEGIN IMMEDIATE")
        actual_upsert(second,pid,mode,
                      "2030-01-01T00:00:00+09:00" if mode=="hold" else "",
                      "CHILD_MANUAL_MAIL",now_text)
        lock_ready.set()
        time.sleep(0.12)
        second.commit()
    finally:
        second.close()

def test_two_process_sqlite_interleavings(ns,now):
    """Cross-process SQLite: child manual writer LOCKS a real temp SQLite file.

    Parent's auto writer first reads then tries a conditional UPSERT/DELETE,
    blocks on the second process' transaction, and must observe newer mode.
    """
    mp=multiprocessing.get_context("fork")
    base_upsert=ns["_upsert_overview_snooze"]
    pid="AMEA2099555000"
    round_count=0
    for scenario in ("insert_then_hold","update_then_skip","delete_then_hold"):
        for iteration in range(8):
            with tempfile.TemporaryDirectory(prefix="css-two-process-sqlite-") as td:
                dbpath=str(Path(td)/"css_synthetic.sqlite3")
                setup=sqlite3.connect(dbpath,timeout=5)
                setup.execute("PRAGMA journal_mode=WAL")
                setup.execute("""CREATE TABLE overview_project_snoozes(
                    project_id TEXT PRIMARY KEY, mode TEXT NOT NULL, hold_until TEXT,
                    baseline_mail_marker TEXT, created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL)""")
                setup.commit()
                if scenario in ("update_then_skip","delete_then_hold"):
                    base_upsert(setup,pid,"skip_prepayment","",
                                "AUTO_OLD_MAIL",now.isoformat())
                    setup.commit()
                setup.close()
                parent=sqlite3.connect(dbpath,timeout=5)
                parent.execute("PRAGMA busy_timeout=5000")
                start=mp.Event()
                acquired=mp.Event()
                mode="skip_until_new_mail" if scenario=="update_then_skip" else "hold"
                p=mp.Process(
                    target=two_process_manual_worker,
                    args=(dbpath,pid,mode,start,acquired,base_upsert,now.isoformat()))
                p.start()
                class ConcurrentSQLiteProxy:
                    def __init__(self,real):
                        self.real=real
                        self.intercepted=False
                        self.wait_seconds=0.
                    def execute(self,sql,params=()):
                        target="DELETE FROM overview_project_snoozes" if scenario=="delete_then_hold" else "INSERT INTO overview_project_snoozes"
                        if target in sql and not self.intercepted:
                            self.intercepted=True
                            start.set()
                            if not acquired.wait(timeout=5):
                                raise AssertionError("CHILD_WRITER_DID_NOT_ACQUIRE_LOCK")
                            t=time.monotonic()
                            result=self.real.execute(sql,params)
                            self.wait_seconds=time.monotonic()-t
                            return result
                        return self.real.execute(sql,params)
                    def commit(self):
                        return self.real.commit()
                proxy=ConcurrentSQLiteProxy(parent)
                stage="Sample QC review" if scenario=="delete_then_hold" else "SIF requested"
                outcome=None
                try:
                    outcome=ns["sync_overview_prepayment_snoozes"](
                        proxy,board(pid,"LIVE_"+str(iteration),stage),
                        {pid},now=now+pd.Timedelta(minutes=iteration))
                    p.join(timeout=5)
                    check(not p.is_alive() and p.exitcode==0,
                          "SECOND_PROCESS_TRANSACTION_COMPLETED_"+scenario+"_"+str(iteration))
                    actual=row(parent,pid)
                    check(actual is not None and actual[0]==mode,
                          "NEWER_MANUAL_MODE_SURVIVES_"+scenario+"_"+str(iteration))
                    check(proxy.intercepted and proxy.wait_seconds>=0.05,
                          "REAL_SQLITE_WRITE_LOCK_SERIALIZATION_"+scenario+"_"+str(iteration))
                    check(outcome["overview_prepayment_skip_active"]==0,
                          "AUTO_ACTIVE_COUNT_CORRECT_"+scenario+"_"+str(iteration))
                    if scenario=="insert_then_hold":
                        check(outcome["overview_prepayment_skip_created"]==0,
                              "NO_GHOST_AUTO_CREATE_"+str(iteration))
                    if scenario=="delete_then_hold":
                        check(outcome["overview_prepayment_skip_released"]==0,
                              "NO_GHOST_AUTO_RELEASE_"+str(iteration))
                    round_count+=1
                finally:
                    if p.is_alive():
                        p.terminate()
                    p.join(timeout=2)
                    parent.close()
    check(round_count==24,"TWO_PROCESS_24_SERIALIZATION_ROUNDS")
    print("TWO_PROCESS_SEPARATE_CONNECTION_LOCK_TEST_PASS",round_count,flush=True)


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--source",required=True)
    ap.add_argument("--patch",action="append",required=True)
    args=ap.parse_args()
    with tempfile.TemporaryDirectory(prefix="css-overlap-case-") as folder:
        src,original,path=stage(args.source,args.patch,folder)
        ns=extract(src)
        now=pd.Timestamp("2026-10-15T09:00:00",tz=TZ)
        p1="AMEA2099000001"; p2="AMEA2099000002"; p3="AMEA2099000003"
        con=connect()
        sheet=FakeSheet()
        # Same project: explicit manual Hold wins over new mail + Prepayment.
        sheet.priority=[{"AMEA Project":p1,"Normal Action":"Hold","Hold Days":"3"}]
        ns["sync_overview_snooze_actions"](con,sheet,board(p1,"M1"),now=now)
        hold=row(con,p1)
        check(hold is not None and hold[0]=="hold","MANUAL_HOLD_CREATED")
        ns["sync_overview_prepayment_snoozes"](con,board(p1,"M1"),{p1},now=now)
        check(row(con,p1)==hold,"PREPAYMENT_DOES_NOT_REPLACE_MANUAL_HOLD")
        sheet.priority=[]
        ns["sync_overview_snooze_actions"](con,sheet,board(p1,"M2"),
            now=now+pd.Timedelta(hours=1))
        check(row(con,p1)==hold,"NEW_MAIL_DOES_NOT_CANCEL_HOLD")
        ns["sync_overview_prepayment_snoozes"](con,board(p1,"M2"),{p1},
            now=now+pd.Timedelta(hours=1))
        check(row(con,p1)==hold,"PREPAYMENT_AFTER_NEW_MAIL_PRESERVES_HOLD")
        # Hold expiry permits automatic Prepayment Skip.
        ns["sync_overview_snooze_actions"](con,sheet,board(p1,"M2"),
            now=now+pd.Timedelta(days=4))
        check(row(con,p1) is None,"MANUAL_HOLD_EXPIRED")
        ns["sync_overview_prepayment_snoozes"](con,board(p1,"M2"),{p1},
            now=now+pd.Timedelta(days=4))
        check(row(con,p1)[0]=="skip_prepayment",
              "AUTO_PREPAYMENT_CREATED_AFTER_HOLD_EXPIRES")
        # Prepayment skip persists even when new mail changes the marker.
        sheet.priority=[]
        ns["sync_overview_snooze_actions"](con,sheet,board(p1,"M3"),
            now=now+pd.Timedelta(days=4,hours=1))
        ns["sync_overview_prepayment_snoozes"](con,board(p1,"M3"),{p1},
            now=now+pd.Timedelta(days=4,hours=1))
        check(row(con,p1)[0]=="skip_prepayment","NEW_MAIL_DOES_NOT_CLEAR_PREPAYMENT")
        ns["sync_overview_prepayment_snoozes"](con,board(p1,"M3","Sample QC review"),
            {p1},now=now+pd.Timedelta(days=4,hours=2))
        check(row(con,p1) is None,"QC_STAGE_RELEASES_PREPAYMENT")
        # Normal manual Skip must release on NEW mail and not be re-created.
        sheet.priority=[{"AMEA Project":p2,"Normal Action":"Skip",
                         "Mail Marker":"B0||1||2026-10-15T08:00:00+09:00"}]
        ns["sync_overview_snooze_actions"](con,sheet,board(p2,"B0"),now=now)
        check(row(con,p2)[0]=="skip_until_new_mail","NORMAL_MANUAL_SKIP_CREATED")
        sheet.priority=[]
        ns["sync_overview_snooze_actions"](con,sheet,board(p2,"B1"),
             now=now+pd.Timedelta(minutes=5))
        check(row(con,p2) is None,"NORMAL_SKIP_RELEASED_ON_NEW_MAIL")
        # If Prepayment still applies, manual Skip release becomes auto Skip.
        sheet.priority=[{"AMEA Project":p2,"Normal Action":"Skip",
                         "Mail Marker":"B1||1||2026-10-15T08:00:00+09:00"}]
        ns["sync_overview_snooze_actions"](con,sheet,board(p2,"B1"),
             now=now+pd.Timedelta(minutes=6))
        sheet.priority=[]
        ns["sync_overview_snooze_actions"](con,sheet,board(p2,"B2"),
             now=now+pd.Timedelta(minutes=7))
        ns["sync_overview_prepayment_snoozes"](con,board(p2,"B2"),{p2},
             now=now+pd.Timedelta(minutes=7))
        check(row(con,p2)[0]=="skip_prepayment",
              "MANUAL_SKIP_RELEASE_WITH_PREPAYMENT_STILL_SUPPRESSED")
        # A newer mail between render and user click cannot create a sticky Skip.
        sheet.priority=[{"AMEA Project":p3,"Normal Action":"Skip",
                         "Mail Marker":"OLD||1||2026-10-15T08:00:00+09:00"}]
        ns["sync_overview_snooze_actions"](con,sheet,board(p3,"NEW"),now=now)
        check(row(con,p3) is None,"STALE_SHEET_MARKER_SKIP_NOT_STICKY")
        # A single malformed control read must never partially update DB.
        before=list(con.execute("SELECT * FROM overview_project_snoozes ORDER BY 1"))
        sheet.fail=True
        try:ns["sync_overview_snooze_actions"](con,sheet,board(p1,"M3"),now)
        except RuntimeError:pass
        else:raise AssertionError("SHEET_READ_FAILURE_NOT_PROPAGATED")
        check(before==list(con.execute("SELECT * FROM overview_project_snoozes ORDER BY 1")),
             "FAILED_SNAPSHOT_READ_NO_DB_MUTATION")
        sheet.fail=False
        sheet.incorrect_response=True
        try:ns["sync_overview_snooze_actions"](con,sheet,board(p1,"M3"),now)
        except RuntimeError:pass
        else:raise AssertionError("PARTIAL_SNAPSHOT_NOT_REJECTED")
        check(before==list(con.execute("SELECT * FROM overview_project_snoozes ORDER BY 1")),
             "PARTIAL_SHEET_RESPONSE_NO_DB_MUTATION")
        sheet.incorrect_response=False
        # Exception after first manual row forces complete SAVEPOINT rollback.
        old_func=ns["overview_mail_marker"]
        call_count=[0]
        def injected(row):
            call_count[0]+=1
            if call_count[0]==2:
                raise RuntimeError("synthetic marker parsing fault")
            return old_func(row)
        ns["overview_mail_marker"]=injected
        sheet.priority=[
          {"AMEA Project":p1,"Normal Action":"Hold","Hold Days":"4"},
          {"AMEA Project":p3,"Normal Action":"Hold","Hold Days":"4"}]
        frame=pd.concat([board(p1,"A"),board(p3,"B")],ignore_index=True)
        try:ns["sync_overview_snooze_actions"](con,sheet,frame,now)
        except RuntimeError:pass
        else:raise AssertionError("INJECTED_FAILURE_NOT_PROPAGATED")
        ns["overview_mail_marker"]=old_func
        check(before==list(con.execute("SELECT * FROM overview_project_snoozes ORDER BY 1")),
             "SAVEPOINT_PARTIAL_MANUAL_ACTION_ROLLBACK")
        # Explicit release of Hold allows Prepayment to be reinstated.
        sheet.priority=[{"AMEA Project":p1,"Normal Action":"Hold","Hold Days":"2"}]
        ns["sync_overview_snooze_actions"](con,sheet,board(p1,"X"),now)
        sheet.priority=[]
        sheet.management=[{"AMEA Project":p1,"Action":"Release"}]
        ns["sync_overview_snooze_actions"](con,sheet,board(p1,"X"),now+pd.Timedelta(minutes=1))
        check(row(con,p1) is None,"MANUAL_RELEASE_REMOVES_HOLD")
        sheet.management=[]
        ns["sync_overview_prepayment_snoozes"](con,board(p1,"X"),{p1},now)
        check(row(con,p1)[0]=="skip_prepayment",
              "EXPLICIT_HOLD_RELEASE_REENABLES_PREPAYMENT")
        # Two repeat-cycle states to DIAGNOSE (not treat known behavior as PASS).
        initial=row(con,p1)
        ns["sync_overview_prepayment_snoozes"](con,board(p1,"X"),{p1},
              now+pd.Timedelta(minutes=10))
        repeated=row(con,p1)
        check(initial[4]==repeated[4],"AUTO_SKIP_NOOP_PRESERVES_UPDATED_AT")
        sheet.priority=[{"AMEA Project":p3,"Normal Action":"Hold","Hold Days":"3"}]
        ns["sync_overview_snooze_actions"](con,sheet,board(p3,"Y"),now)
        original_hold=row(con,p3)
        ns["sync_overview_snooze_actions"](con,sheet,board(p3,"Y"),
             now+pd.Timedelta(hours=1))
        repeated_hold=row(con,p3)
        check(repeated_hold[1]==original_hold[1],
              "REPLAYED_HOLD_DOES_NOT_EXTEND_DEADLINE")
        # REPRODUCE manual-update race deterministically between read and upsert.
        ns["sync_overview_prepayment_snoozes"](con,board(p2,"B2","Sample QC review"),
             {p2},now)
        check(row(con,p2) is None,"RACE_TEST_PREPARED")
        base_upsert=ns["_upsert_overview_snooze"]
        class RaceConnection:
            def __init__(self,inner):
                self.inner=inner
                self.intercepted=False
            def execute(self,sql,params=()):
                if ("INSERT INTO overview_project_snoozes" in sql
                        and not self.intercepted):
                    self.intercepted=True
                    base_upsert(self.inner,p2,"hold","2030-01-01",
                                "MANUAL_NEWER_MARKER",now.isoformat())
                return self.inner.execute(sql,params)
            def commit(self):
                return self.inner.commit()
        racing=RaceConnection(con)
        race_outcome=ns["sync_overview_prepayment_snoozes"](
            racing,board(p2,"B3"),{p2},now)
        check(racing.intercepted,"RACE_INJECTED_BETWEEN_READ_AND_UPSERT")
        check(row(con,p2)[0]=="hold","LATEST_MANUAL_HOLD_SURVIVES_AUTO_UPSERT")
        check(race_outcome["overview_prepayment_skip_created"]==0,
              "RACE_NO_FALSE_AUTOSKIP_CREATED_COUNT")
        check(race_outcome["overview_prepayment_skip_active"]==0,
              "RACE_NO_FALSE_AUTOSKIP_ACTIVE_COUNT")
        test_two_process_sqlite_interleavings(ns,now)
        check(hashlib.sha256(Path(args.source).read_bytes()).hexdigest()==ORIGINAL_SHA,
              "LIVE_SOURCE_UNCHANGED")
        con.close()
        for n,patch in reversed(list(enumerate(args.patch,1))):
            for flags in (("-R","--check"),("-R",)):
                v=subprocess.run(["git","apply",*flags,str(Path(patch).resolve())],
                       cwd=folder,capture_output=True,text=True,timeout=90)
                check(v.returncode==0,"REVERSE_PATCH_"+str(n)+"_"+str(flags[-1]))
        check(path.read_bytes()==original,"SIX_PATCH_ROLLBACK_BYTE_EXACT")
        print("COLLISION_HARDENED_CHECKS_PASS",len(CHECKS),flush=True)
        print("REAL_CSS_FUNCTIONS_EXECUTED_SYNTHETIC_ONLY",True,flush=True)

if __name__=="__main__":
    main()
