#!/usr/bin/env python3
"""Test the real CSS main branch, display-policy split, and output builder wiring.

All data is synthetic; no production import, DB mutation, Sheets write, or
customer information leaves the host. Source is read only for AST extraction.
"""
from __future__ import annotations
import argparse, ast, hashlib, re, sqlite3, subprocess, tempfile
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

EXPECTED_ORIGINAL="a7c395be330bc1128f8164cdac1d75a7c27fd35398e46ff5589271ebf0bae840"
N=1200
results=[]

def check(value,key):
    if not value:
        raise AssertionError(key)
    results.append(key)
    print("POLICY_TEST_PASS",key,flush=True)

def execnode(node,env,label):
    exec(compile(ast.Module(body=[node],type_ignores=[]),label,"exec"),env)

def assignment(main,name):
    matches=[n for n in ast.walk(main)
             if isinstance(n,ast.Assign)
             and any(isinstance(t,ast.Name) and t.id==name for t in n.targets)]
    if len(matches)!=1:
        raise AssertionError("ONE_ASSIGNMENT_REQUIRED_"+name)
    return matches[0]

def exercise_main(source):
    tree=ast.parse(source)
    main=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="main")
    ids={f"AMEA{2099000000+i:010d}" for i in range(N) if i%3==0}
    board=pd.DataFrame([{
        "project_id":f"AMEA{2099000000+i:010d}",
        "current_stage":"Sample QC review" if i%7==0 else
            "SIF revision required" if i%2 else "SIF requested",
        "attention":"Yes","attention_reason":"Latest email requires action",
        "latest_action_required":"Yes",
        "institution":f"Synthetic institute {i%17}",
    } for i in range(N)])
    wanted=set(board.loc[
        board["project_id"].isin(ids)&
        board["current_stage"].isin(["SIF requested","SIF revision required"]),
        "project_id"])
    check(len(wanted)>200,"SIF_FIXTURE_SIZABLE")
    prepay_branch=[n for n in ast.walk(main)
             if isinstance(n,ast.If) and isinstance(n.test,ast.BoolOp)
             and any(isinstance(s,ast.Name) and s.id=="prepayment_project_ids"
                     for s in ast.walk(n.test))
             and any(isinstance(s,ast.Name) and s.id=="prepayment_mask"
                     for s in ast.walk(n))]
    check(len(prepay_branch)==1,"ACTUAL_PREPAYMENT_BRANCH_UNIQUE")
    retain=assignment(main,"df_dashboard_portfolio")
    check(isinstance(retain.value,ast.Call) and
         ast.unparse(retain.value)=="df_dashboard.copy()",
         "PORTFOLIO_SNAPSHOT_BEFORE_FILTER")

    def fake_snooze(conn,frame,pids):
        return {"overview_prepayment_skip_created":0,
                "overview_prepayment_skip_released":0,
                "overview_prepayment_skip_active":len(pids)}
    env={
        "df_dashboard":board.copy(),
        "prepayment_project_ids":ids,
        "counts":{},
        "conn":None,
        "pd":pd,
        "sync_overview_prepayment_snoozes":fake_snooze,
        "_sync_overview_snooze_actions_from_records":
            lambda *a:(pd.DataFrame(columns=["mode"]),{}),
    }
    execnode(retain,env,"portfolio_snapshot")
    execnode(prepay_branch[0],env,"actual_prepaid_branch")
    active=env["df_dashboard"]
    portfolio=env["df_dashboard_portfolio"]
    check(len(active)==N-len(wanted),"FOLLOWUP_ONLY_FILTERED")
    check(set(board["project_id"])-set(active["project_id"])==wanted,
          "EXCLUDED_PROJECT_IDS_EXACT")
    check(len(portfolio)==N,"PORTFOLIO_TOTAL_RETAINED")
    check(set(portfolio["project_id"])==set(board["project_id"]),
          "PORTFOLIO_IDS_IDENTICAL")
    rows=portfolio.set_index("project_id")
    check(rows.loc[sorted(wanted),"attention"].eq("No").all(),
          "SUPPRESSED_SIF_ATTENTION_NO")
    check(rows.loc[sorted(wanted),"attention_reason"].str.contains(
        "SIF 제출 불필요",regex=False).all(),"SUPPRESSED_REASON_EXPLICIT")
    check(rows.loc[sorted(wanted),"latest_action_required"].eq("No").all(),
          "SIF_ACTION_REQUIRED_NO")
    unsuppressed=sorted(set(board["project_id"])-wanted)
    check(rows.loc[unsuppressed,"attention"].eq("Yes").all(),
          "OTHER_ATTENTION_PRESERVED")
    check(rows.loc[unsuppressed,"latest_action_required"].eq("Yes").all(),
          "OTHER_ACTION_REQUIRED_PRESERVED")
    check(rows["current_stage"].equals(board.set_index("project_id")["current_stage"]),
          "STAGE_NOT_MUTATED")
    check(env["counts"]["prepayment_project_followup_excluded"]==len(wanted),
          "EXCLUSION_COUNT_EXACT")

    # Confirm actual main output calls have *portfolio*, not filtered active,
    # wired to both Customer 360 and the Summary.
    customer=assignment(main,"df_customer_360")
    summary=assignment(main,"df_summary")
    check(ast.unparse(customer.value.func)=="build_customer_360_output"
          and ast.unparse(customer.value.args[0])=="df_dashboard_portfolio",
          "CUSTOMER360_USES_FULL_PORTFOLIO")
    check(ast.unparse(summary.value.func)=="build_summary_df"
          and ast.unparse(summary.value.args[1])=="df_dashboard_portfolio",
          "SUMMARY_USES_FULL_PORTFOLIO")

    recorded={}
    env.update({
        "df_invoice_list":pd.DataFrame(),
        "df_ledger":pd.DataFrame(),
        "df_project_exclusions":pd.DataFrame(),
        "new_total":0,
        "spreadsheet":SimpleNamespace(url="synthetic:canary"),
        "build_customer_360_output":lambda df,other:recorded.setdefault("customer",df.copy()),
        "build_summary_df":lambda ledger,df,*args:recorded.setdefault("summary",df.copy())
    })
    execnode(customer,env,"customer_builder_wiring")
    execnode(summary,env,"summary_builder_wiring")
    check(len(recorded["customer"])==N,"CUSTOMER360_FIXTURE_INPUT_1200")
    check(len(recorded["summary"])==N,"SUMMARY_FIXTURE_INPUT_1200")
    check(recorded["summary"]["attention"].eq("Yes").sum()==len(unsuppressed),
          "SUMMARY_ATTENTION_COUNT_CORRECT")

    # Real output assignment happens after action/review/summary building.
    restore=assignment(main,"df_dashboard")
    check(isinstance(restore.value,ast.Name) and restore.value.id=="df_dashboard_portfolio",
          "SHEET_OUTPUT_RESTORES_PORTFOLIO")
    execnode(restore,env,"portfolio_restore")
    check(len(env["df_dashboard"])==N,"DASHBOARD_SHEET_1200_ROWS")
    check(env["df_dashboard"]["attention"].eq("Yes").sum()==len(unsuppressed),
          "DASHBOARD_ATTENTION_COUNT_CORRECT")

    # Stage recovery and zero-match cases.
    changed=board.copy()
    pid=sorted(wanted)[0]
    changed.loc[changed["project_id"]==pid,"current_stage"]="Sample QC review"
    env["df_dashboard"]=changed.copy()
    env["prepayment_project_ids"]=ids
    env["counts"]={}
    execnode(retain,env,"portfolio_qc")
    execnode(prepay_branch[0],env,"action_qc")
    check(pid in set(env["df_dashboard"]["project_id"]),"QC_REENTERS_ACTION_QUEUE")
    check(pid in set(env["df_dashboard_portfolio"]["project_id"]),"QC_STAYS_PORTFOLIO")
    check(env["df_dashboard_portfolio"].set_index("project_id").loc[pid,"attention"]=="Yes",
          "QC_ATTENTION_NOT_SUPPRESSED")
    env["df_dashboard"]=board.copy()
    env["prepayment_project_ids"]=set()
    env["counts"]={}
    execnode(retain,env,"portfolio_empty")
    execnode(prepay_branch[0],env,"action_empty")
    check(len(env["df_dashboard"])==N and len(env["df_dashboard_portfolio"])==N,
          "ZERO_PREPAYMENT_BOTH_VIEWS_FULL")
    check(env["df_dashboard_portfolio"]["attention"].eq("Yes").all(),
          "ZERO_PREPAYMENT_ATTENTION_UNCHANGED")


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--source",required=True)
    parser.add_argument("--history",required=True)
    parser.add_argument("--manual",required=True)
    parser.add_argument("--portfolio",required=True)
    args=parser.parse_args()
    original=Path(args.source).read_bytes()
    check(hashlib.sha256(original).hexdigest()==EXPECTED_ORIGINAL,
          "PRODUCTION_SOURCE_SHA_UNCHANGED")
    patches=[Path(args.history).resolve(),Path(args.manual).resolve(),Path(args.portfolio).resolve()]
    with tempfile.TemporaryDirectory(prefix="css-portfolio-") as td:
        staged=Path(td)/"Novogene_Mail_CSS_DashBoard.py"
        staged.write_bytes(original)
        for n,patch in enumerate(patches,1):
            for flags in (("--check",),()):
                proc=subprocess.run(["git","apply",*flags,str(patch)],cwd=td,
                        capture_output=True,text=True,timeout=70)
                if proc.returncode:
                    raise RuntimeError("PATCH_FAILED_"+str(n)+"_"+str(flags)+" "+proc.stderr[:280])
                check(True,"PATCH_"+str(n)+"_"+("CHECK" if flags else "APPLY"))
        b=staged.read_bytes()
        compile(ast.parse(b),"staged_portfolio.py","exec")
        print("PORTFOLIO_COMBINED_SHA256",hashlib.sha256(b).hexdigest(),flush=True)
        check(True,"TRIPLE_PATCH_COMPILE")
        exercise_main(b)
        for i,patch in reversed(list(enumerate(patches,1))):
            for flags in (("-R","--check"),("-R",)):
                proc=subprocess.run(["git","apply",*flags,str(patch)],cwd=td,
                        capture_output=True,text=True,timeout=70)
                if proc.returncode:
                    raise RuntimeError("REVERSE_FAILED_"+str(i)+"_"+str(flags))
                check(True,"REVERSE_"+str(i)+"_"+("CHECK" if "--check" in flags else "APPLY"))
        check(staged.read_bytes()==original,"TRIPLE_PATCH_ROLLBACK_BYTE_EXACT")
    check(hashlib.sha256(Path(args.source).read_bytes()).hexdigest()==EXPECTED_ORIGINAL,
          "PRODUCTION_SOURCE_NEVER_CHANGED")
    print("PORTFOLIO_ACTION_SPLIT_ALL_PASS",len(results),flush=True)
    print("SYNTHETIC_PROJECT_COUNT",N,flush=True)
    print("LIVE_DB_SHEETS_MAIL_UNTOUCHED",True,flush=True)

if __name__=="__main__":
    main()
