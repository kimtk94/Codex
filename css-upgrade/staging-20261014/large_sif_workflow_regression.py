#!/usr/bin/env python3
"""Large synthetic SIF integration regression, extracting REAL production functions by AST.
No production module imports, no external API requests, no persistent DB writes.
"""
import argparse, ast, hashlib, json, re, sqlite3, subprocess, sys, tempfile, time
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import pandas as pd

SOURCE_SHA="a7c395be330bc1128f8164cdac1d75a7c27fd35398e46ff5589271ebf0bae840"
N=1200
COLS=["record_id","is_active","Contract No.","AMEA No.","Institution","Customer Name",
      "skip_reason","Prepayment","skipped_at","restored_at","reference_date","age_days",
      "workflow_status","tracker_visibility","history_note"]
checks=[]

def require(condition,name):
    if not condition:
        raise AssertionError(name)
    checks.append(name)
    print("PASS",name)

def staging(source,patch1,patch2,folder):
    raw=Path(source).read_bytes()
    require(hashlib.sha256(raw).hexdigest()==SOURCE_SHA,"original_server_sha")
    path=Path(folder)/"Novogene_Mail_CSS_DashBoard.py"
    path.write_bytes(raw)
    for p in (patch1,patch2):
        for args in (("--check","--whitespace=error"),("--whitespace=error",)):
            z=subprocess.run(["git","apply",*args,str(Path(p).resolve())],
                         cwd=folder,capture_output=True,text=True,timeout=60)
            require(z.returncode==0,"patch_"+str(Path(p).name)+"_"+str(args[0]))
    txt=path.read_text()
    ast.parse(txt)
    require("v8.92.1-server-local-adc" in txt,"runtime_version_preserved")
    print("COMBINED_PATCH_SHA256",hashlib.sha256(path.read_bytes()).hexdigest())
    # Validate exact rollback of BOTH patches in inverse order, on temp copy only.
    for p in (patch2,patch1):
        for flags in (("-R","--check"),("-R",)):
            out=subprocess.run(["git","apply",*flags,str(Path(p).resolve())],
                 cwd=folder,capture_output=True,text=True,timeout=60)
            require(out.returncode==0,"reverse_"+str(Path(p).name)+"_"+str(flags[-1]))
    require(path.read_bytes()==raw,"two_patch_rollback_byte_exact")
    return txt

def load_functions(txt):
    wanted={"load_active_contract_sif_skips","collect_active_prepayment_project_ids",
      "build_contract_sif_skip_history","sync_overview_prepayment_snoozes",
      "_upsert_overview_snooze","restore_contract_sif_skip",
      "split_contract_sif_active_and_skipped",
      "overwrite_dataframe_if_changed"}
    tree=ast.parse(txt)
    nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in wanted]
    require({n.name for n in nodes}==wanted,"real_function_set_found")
    ns={"pd":pd,"json":json,"datetime":datetime,"timezone":timezone,
        "time":time,"KST":ZoneInfo("Asia/Seoul"),
        "SAMPLE_INTAKE_PREPAYMENT_COLUMN":"Prepayment","SAMPLE_INTAKE_SKIP_COLUMN":"skip",
        "SAMPLE_INTAKE_SKIP_REASON_COLUMN":"skip_reason","SAMPLE_INTAKE_RESTORE_COLUMN":"restore",
        "SAMPLE_INTAKE_RETENTION_DAYS":30,
        "SAMPLE_INTAKE_TERMINAL_STATUSES":{"SIF approved"},
        "SAMPLE_INTAKE_SKIP_HISTORY_COLUMNS":COLS,
        "SAMPLE_INTAKE_COLUMNS":["record_id","skip","Prepayment","skip_reason","project_id","Contract No.","Date"],
        "SAMPLE_INTAKE_SKIPPED_COLUMNS":["restore","skipped_at","record_id",
                                         "project_id","Contract No.","Prepayment","skip_reason"],
        "SMART_SHEET_WRITES":True,"_SHEET_WRITE_PROFILE":[]}
    ns["clean_text"]=lambda x: str(x).strip() if x is not None else ""
    ns["normalize_text"]=lambda x:ns["clean_text"](x).lower()
    ns["checkbox_is_checked"]=lambda x:ns["normalize_text"](x) in {"true","yes","1","y","checked"}
    ns["iter_dataframe_records"]=lambda df:df.to_dict("records")
    ns["dataframe_row_text"]=lambda row,key:ns["clean_text"](row.get(key,""))
    ns["canonical_sif_project_id"]=lambda val:(re.search(r"AMEA\d{10}",str(val).upper()).group()
             if re.search(r"AMEA\d{10}",str(val).upper()) else "")
    ns["overview_mail_marker"]=lambda row:"synthetic-marker-"+str(row.get("project_id",""))
    ns["dataframe_sheet_write_hash"]=lambda df,value_input_option="RAW":hashlib.sha256(
        (df.to_json(orient="split")+"\t"+value_input_option).encode()).hexdigest()
    ns["get_meta"]=lambda conn,key,default="":(conn.execute(
        "SELECT value FROM sheet_meta WHERE key=?",(key,)).fetchone() or [default])[0]
    ns["set_meta"]=lambda conn,key,value:conn.execute(
        "INSERT INTO sheet_meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key,str(value)))
    ns["sheet_integrity_audit_is_fresh"]=lambda conn,ws:True
    ns["output_sheet_structure_is_current"]=lambda conn,ws,df:ws.header==list(df.columns) and ws.rows==len(df)
    ns["ensure_basic_filter_range"]=lambda *a,**kw:None
    ns["verify_repaired_output_sheet_structure"]=lambda *a,**kw:None
    exec(compile(ast.Module(body=nodes,type_ignores=[]),"select-real-css-functions","exec"),ns)
    return ns

def synthetic_db():
    con=sqlite3.connect(":memory:")
    con.execute("""CREATE TABLE contract_sif_skips(
      record_id TEXT PRIMARY KEY, is_active INTEGER, skip_reason TEXT,
      skipped_at TEXT,restored_at TEXT,updated_at TEXT,snapshot_json TEXT)""")
    con.execute("""CREATE TABLE overview_project_snoozes(
      project_id TEXT PRIMARY KEY,mode TEXT NOT NULL,hold_until TEXT,
      baseline_mail_marker TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL)""")
    con.execute("CREATE TABLE sheet_meta(key TEXT PRIMARY KEY,value TEXT)")
    rows=[]
    for i in range(N):
        project=f"AMEA{2099000000+i:010d}"
        active=i%13!=0
        prepay=i%3==0
        invalid=i%47==0
        stage=("Sample QC review" if i%7==0 else
               "SIF revision required" if i%2 else "SIF requested")
        snapshot={"project_id":project,"AMEA No.":project,"Contract No.":f"TEST-{i:05}",
          "Institution":"SYNTHETIC ONLY","Customer Name":"CANARY PERSON",
          "Date":"2026-08-01","workflow_status":stage,"Prepayment":prepay}
        reason=("Prepayment - SIF no submission" if prepay and i%2==0 else "Other")
        raw=("{bad" if invalid else json.dumps(snapshot))
        con.execute("INSERT INTO contract_sif_skips VALUES(?,?,?,?,?,?,?)",
            (f"REC-{i:05}",int(active),reason,"2026-08-20",None,
             "2026-08-20",raw))
        rows.append({"project_id":project,"current_stage":stage,"record_id":f"REC-{i:05}",
            "Contract No.":f"TEST-{i:05}","Date":"2026-08-01",
            "skip":False,"Prepayment":False,"skip_reason":""})
    con.commit()
    return con,pd.DataFrame(rows)

def test_big_batch(ns,conn,board):
    ids=ns["collect_active_prepayment_project_ids"](conn)
    expected=set()
    for i in range(N):
        if i%13!=0 and i%47!=0 and i%3==0:
            expected.add(board.iloc[i]["project_id"])
    require(ids==expected,"1200_row_exact_prepayment_matching")
    hist=ns["build_contract_sif_skip_history"](conn)
    require(len(hist)==N,"1200_history_rows_no_loss")
    require(int(hist["is_active"].sum())==N-len(range(0,N,13)),"history_active_count")
    require(hist["record_id"].nunique()==N,"history_record_ids_unique")
    require((hist.loc[hist["reference_date"]=="2026-08-01","age_days"]>30).all(),
            "retention_history_still_visible")
    first=board.iloc[:500].copy()
    active,skipped=ns["split_contract_sif_active_and_skipped"](conn,first)
    exp_active=sum(1 for i in range(500) if i%13==0)
    require(len(active)==exp_active,"tracker_removes_durable_skip")
    require(len(skipped)==500-exp_active,"skipped_view_current_only")
    empty_a,empty_s=ns["split_contract_sif_active_and_skipped"](conn,first.iloc[:0])
    require(len(empty_a)==0 and len(empty_s)==0,"empty_retention_view_safe")
    return ids

def test_snooze_collision_and_transitions(ns,conn,board,prepay):
    eligible=[p for p in prepay if board.loc[board["project_id"]==p,"current_stage"].iat[0] in
                ("SIF requested","SIF revision required")]
    eligible.sort()
    require(len(eligible)>100,"large_eligible_prepayment_fixture")
    hold_id,skip_id,transition_id=eligible[:3]
    conn.executemany("INSERT INTO overview_project_snoozes VALUES(?,?,?,?,?,?)",[
        (hold_id,"hold","2030-01-01","mail-1","2026-01-01","2026-01-01"),
        (skip_id,"skip_until_new_mail","","mail-2","2026-01-01","2026-01-01")])
    conn.commit()
    before=dict(conn.execute("SELECT project_id,mode FROM overview_project_snoozes"))
    first=ns["sync_overview_prepayment_snoozes"](conn,board,prepay)
    after=dict(conn.execute("SELECT project_id,mode FROM overview_project_snoozes"))
    require(after[hold_id]=="hold" and after[skip_id]=="skip_until_new_mail",
            "same_project_manual_hold_skip_preserved")
    require(first["overview_prepayment_skip_created"]>100,"large_scale_prepayment_created")
    require(first["overview_prepayment_skip_active"]==len(eligible)-2,
            "manual_overrides_excluded_from_auto_skips")
    second=ns["sync_overview_prepayment_snoozes"](conn,board,prepay)
    require(second["overview_prepayment_skip_created"]==0 and
            second["overview_prepayment_skip_released"]==0,"repeat_is_idempotent")
    stage_board=board.copy()
    stage_board.loc[stage_board["project_id"]==transition_id,"current_stage"]="Sample QC review"
    third=ns["sync_overview_prepayment_snoozes"](conn,stage_board,prepay)
    require(third["overview_prepayment_skip_released"]==1 and
            transition_id not in dict(conn.execute("SELECT project_id,mode FROM overview_project_snoozes")),
            "QC_transition_releases_only_auto_skip")
    require(dict(conn.execute("SELECT project_id,mode FROM overview_project_snoozes"))[hold_id]=="hold",
            "QC_does_not_remove_manual_hold")
    conn.execute("DELETE FROM overview_project_snoozes WHERE project_id=?",(hold_id,))
    fourth=ns["sync_overview_prepayment_snoozes"](conn,stage_board,prepay)
    require(dict(conn.execute("SELECT project_id,mode FROM overview_project_snoozes"))[hold_id]=="skip_prepayment" and
            fourth["overview_prepayment_skip_created"]==1,"released_manual_hold_allows_auto_skip")
    # Prepayment removed while QC and old manual Skip must remain.
    fifth=ns["sync_overview_prepayment_snoozes"](conn,stage_board,set())
    modes=dict(conn.execute("SELECT project_id,mode FROM overview_project_snoozes"))
    require(modes=={skip_id:"skip_until_new_mail"},"all_auto_skips_cleaned_only_manual_remains")
    require(fifth["overview_prepayment_skip_active"]==0,"empty_prepayment_set_empty_auto_state")

def test_actual_main_prepayment_branch(ns,conn,board,source):
    """Execute only the real main() Prepayment branch; never import/call main()."""
    tree=ast.parse(source)
    main=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="main")
    branches=[n for n in ast.walk(main)
              if isinstance(n,ast.If)
              and isinstance(n.test,ast.BoolOp)
              and any(isinstance(t,ast.Name) and t.id=="prepayment_project_ids"
                      for t in ast.walk(n.test))
              and any(isinstance(z,ast.Name) and z.id=="prepayment_mask"
                      for z in ast.walk(n))]
    require(len(branches)==1,"main_branch_exactly_one")
    node=branches[0]
    ids=ns["collect_active_prepayment_project_ids"](conn)
    fresh=board.copy()
    expected={
        r["project_id"] for r in ns["iter_dataframe_records"](fresh)
        if r["project_id"] in ids and r["current_stage"] in
        {"SIF requested","SIF revision required"}
    }
    assert len(expected)>100
    outer=dict(ns)
    outer.update({
      "conn":conn,
      "df_dashboard":fresh,
      "prepayment_project_ids":ids,
      "counts":{},
      "df_overview_snoozes":pd.DataFrame(columns=["mode"]),
      "_sync_overview_snooze_actions_from_records":
          lambda con, dashboard, requests, snapshots: (pd.DataFrame(columns=["mode"]),{}),
    })
    exec(compile(ast.Module(body=[node],type_ignores=[]),"actual-main-prepayment-if","exec"),outer)
    actual=outer["df_dashboard"]
    remain=set(actual["project_id"])
    before=set(fresh["project_id"])
    require(before-remain==expected,"main_only_active_SIF_prepayment_removed")
    require(len(actual)+len(expected)==len(fresh),"main_no_unintended_row_loss")
    require(outer["counts"]["prepayment_project_followup_excluded"]==len(expected),
            "main_prepayment_exclusion_count_exact")
    require(set(outer["counts"]["prepayment_project_followup_project_ids"])==expected,
            "main_prepayment_exclusion_ids_exact")
    qc_ids=set(board.loc[board["current_stage"]=="Sample QC review","project_id"])
    require(qc_ids.issubset(remain),"main_QC_projects_remain_visible")
    normal_ids=set(board["project_id"])-ids
    require(normal_ids.issubset(remain),"main_nonprepayment_projects_remain_visible")
    # Rerunning the same section on a fresh source board must not change output.
    outer["df_dashboard"]=fresh.copy()
    outer["counts"]={}
    exec(compile(ast.Module(body=[node],type_ignores=[]),"main-prepayment-repeat","exec"),outer)
    require(set(outer["df_dashboard"]["project_id"])==remain,"main_repeat_same_output")
    # Simulate advancing a suppressed project from SIF to QC in original input.
    transitioned=sorted(expected)[0]
    promoted=fresh.copy()
    promoted.loc[promoted["project_id"]==transitioned,"current_stage"]="Sample QC review"
    outer["df_dashboard"]=promoted
    outer["counts"]={}
    exec(compile(ast.Module(body=[node],type_ignores=[]),"main-prepayment-QC","exec"),outer)
    require(transitioned in set(outer["df_dashboard"]["project_id"]),
            "main_SIF_to_QC_reappears")
    require(outer["counts"]["prepayment_project_followup_excluded"]==len(expected)-1,
            "main_QC_reappearance_count")
    # Negative case: no Prepayment qualifies. Branch may only clean auto snoozes,
    # never erase unrelated manual modes or drop Dashboard rows.
    outer["df_dashboard"]=promoted.copy()
    outer["prepayment_project_ids"]=set()
    outer["counts"]={}
    exec(compile(ast.Module(body=[node],type_ignores=[]),"main-prepayment-empty","exec"),outer)
    require(len(outer["df_dashboard"])==len(promoted),"main_zero_prepayment_rows_retained")
    require(outer["counts"]["prepayment_project_followup_excluded"]==0,
            "main_zero_prepayment_count")
    print("ACTUAL_MAIN_BRANCH_EXTRACTED_NOT_EXECUTED_ENTIRE_MAIN",True)


def test_restore_and_writer(ns,conn,board):
    rec="REC-00003"
    require(ns["restore_contract_sif_skip"](conn,rec),"manual_restore_applied")
    require(not ns["restore_contract_sif_skip"](conn,rec),"double_restore_noop")
    require(rec not in ns["load_active_contract_sif_skips"](conn),"restore_durable_exclusion_removed")
    require(rec in set(ns["build_contract_sif_skip_history"](conn)["record_id"]),
            "restore_audit_history_remains")
    class FakeSheet:
        id=91234
        title="SYNTHETIC SIF"
        header=[]
        rows=0
        fail=False
        writes=0
    ws=FakeSheet()
    def write(_ws,df,**kwargs):
        if _ws.fail:
            raise RuntimeError("synthetic transient Sheets failure")
        _ws.writes+=1
        _ws.header=list(df.columns)
        _ws.rows=len(df)
    ns["overwrite_typed_worksheet"]=write
    frame=pd.DataFrame([{"project_id":"AMEA2099000123","Prepayment":True}])
    require(ns["overwrite_dataframe_if_changed"](conn,ws,frame) is True,"sheet_initial_write")
    require(ns["overwrite_dataframe_if_changed"](conn,ws,frame) is False,"sheet_second_run_skipped")
    ws.header=["damaged"]
    require(ns["overwrite_dataframe_if_changed"](conn,ws,frame) is True,
            "sheet_structure_self_heal")
    ws.fail=True
    changed=pd.DataFrame([{"project_id":"AMEA2099000123","Prepayment":False}])
    try:
        ns["overwrite_dataframe_if_changed"](conn,ws,changed)
    except RuntimeError:
        pass
    else:
        raise AssertionError("sheet_failure_injection_missing")
    ws.fail=False
    require(ns["overwrite_dataframe_if_changed"](conn,ws,changed) is True,
            "failed_sheet_write_retries")
    require(ns["overwrite_dataframe_if_changed"](conn,ws,changed) is False,
            "post_failure_idempotent")

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--source",required=True)
    parser.add_argument("--history",required=True)
    parser.add_argument("--manual",required=True)
    args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="css-sif-1200-") as tmp:
        source=staging(args.source,args.history,args.manual,tmp)
        ns=load_functions(source)
        conn,df=synthetic_db()
        try:
            ids=test_big_batch(ns,conn,df)
            test_snooze_collision_and_transitions(ns,conn,df,ids)
            test_actual_main_prepayment_branch(ns,conn,df,source)
            test_restore_and_writer(ns,conn,df)
        finally:
            conn.close()
    print("ALL_BIG_BATCH_CHECKS_PASS",len(checks))
    print("RECORDS_TESTED",N)
    print("NO_PRODUCTION_SOURCE_DB_SHEETS_OR_NETWORK_WRITES",True)

if __name__=="__main__":
    main()
