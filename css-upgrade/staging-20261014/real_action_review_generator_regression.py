#!/usr/bin/env python3
"""Large real Action Center/Review Queue generator regression with synthetic input.

AST extracts function bodies from SHA-verified SERVER code without module import.
All dependencies with potential external effects are synthetic stubs; no Sheet/DB,
mail/CRM/Drive call or persistent write is made.
"""
import argparse, ast, hashlib
from pathlib import Path
import pandas as pd

SHA="a7c395be330bc1128f8164cdac1d75a7c27fd35398e46ff5589271ebf0bae840"
PASS=[]
def check(value,name):
    if not value: raise AssertionError(name)
    PASS.append(name)
    print("GENERATOR_PASS",name,flush=True)

def prepare(src):
    tree=ast.parse(src)
    funcs={n.name:n for n in tree.body if isinstance(n,ast.FunctionDef)}
    needed=("build_action_center_output","build_review_queue_output")
    check(all(n in funcs for n in needed),"ACTUAL_FUNCTION_BODIES_PRESENT")
    ns={"pd":pd,"KST":"Asia/Seoul","STALE_DAYS":7,
        "ACTION_UNANSWERED_MIN_AGE_DAYS":0,"ACTION_UNANSWERED_MAX_AGE_DAYS":365,
        "ACTION_PRIORITY_VALUES":{"긴급","높음","보통"},
        "ACTIVE_SAMPLE_COUNT_STAGES":{"Sample QC issue","Sample QC review"},
        "CLOSED_PROJECT_STAGES":{"Invoice issued","Project finished"},
        "REVIEW_LOOKBACK_DAYS":30}
    for name in ("ACTION_CENTER_COLUMNS","REVIEW_QUEUE_COLUMNS","MANUAL_ISSUE_COLUMNS"):
        matching=[n for n in tree.body if isinstance(n,ast.Assign)
                  and any(isinstance(t,ast.Name) and t.id==name for t in n.targets)]
        check(len(matching)==1,"STATIC_COLUMNS_"+name)
        ns[name]=ast.literal_eval(matching[0].value)
    ns["SAMPLE_INTAKE_COLUMNS"]=["record_id"]
    ns["clean_text"]=lambda x: "" if x is None else str(x).strip()
    ns["normalize_text"]=lambda x:ns["clean_text"](x).lower()
    ns["dataframe_row_text"]=lambda row,key:ns["clean_text"](row.get(key,""))
    ns["iter_dataframe_records"]=lambda df:df.to_dict("records")
    ns["normalize_institution_name"]=lambda x:ns["clean_text"](x)
    ns["project_customer_name"]=lambda evidence,project:""
    ns["stable_record_id"]=lambda *items:"TEST-"+hashlib.md5(
        "|".join(map(str,items)).encode()).hexdigest()[:20]
    ns["build_action_drafts"]=lambda *a:("","","")
    ns["build_recommended_action"]=lambda *a:""
    ns["action_due_date"]=lambda _: "2026-10-16"
    ns["sheet_source_link"]=lambda *a:""
    ns["dataframe_uid_source_row_index"]=lambda df:{}
    ns["safe_float"]=lambda x:float(x) if str(x).strip() not in ("","None") else None
    ns["safe_int"]=lambda x:int(x) if str(x).strip() not in ("","None") else None
    ns["rule_int"]=lambda key,default,**kw:default
    ns["is_external_customer_email"]=lambda x:bool(x and "@" in x)
    ns["is_automated_unanswered_candidate"]=lambda _:False
    ns["salesforce_action_is_current"]=lambda age:age<=30
    ns["merge_operational_state"]=lambda frame,prior,*a:frame
    for name in needed:
        exec(compile(ast.Module(body=[funcs[name]],type_ignores=[]),
                     "extracted-real-generator","exec"),ns)
    return ns

def run_case(ns,board,unanswered,manual,crm,quote):
    empty=pd.DataFrame()
    actions=ns["build_action_center_output"](
        board,unanswered,empty,crm,empty,empty,12345,
        df_sample_intake=empty,df_manual_issues=manual)
    reviews=ns["build_review_queue_output"](board,empty,empty,quote,12345)
    return actions,reviews

def main():
    args=argparse.ArgumentParser()
    args.add_argument("--source",required=True)
    p=args.parse_args().source
    raw=Path(p).read_bytes()
    check(hashlib.sha256(raw).hexdigest()==SHA,"EXACT_PRODUCTION_SOURCE_SHA")
    ns=prepare(raw)
    n=1200
    rows=[]
    for i in range(n):
        pid=f"AMEA{2099000000+i:010d}"
        prepaid=i%3==0 and i%7!=0
        attention="No" if prepaid else "Yes"
        stage="SIF requested" if prepaid or i%7 else "Sample QC issue"
        rows.append(dict(
            project_id=pid,institution="Canary Uni",
            customer_name=f"SYNTHETIC_PI_{i}",service="mRNA-Seq",
            attention=attention,
            attention_reason=("Prepayment - SIF 제출 불필요 (조치 제외)" if prepaid
                              else "Latest email requires action"),
            latest_action_required=attention,current_stage=stage,
            latest_subject="Synthetic message",latest_uid=f"SYNTH-U-{i}",
            planned_samples=10,latest_confirmed_samples=8,
            days_since_update=10,sla_enabled="Yes",
        ))
    board=pd.DataFrame(rows)
    suppressed=board.loc[board["attention"]=="No","project_id"].tolist()
    check(len(suppressed)==342,"PREPAYMENT_SIF_COUNT_342")
    p0,p1,p2=suppressed[:3]
    unanswered=pd.DataFrame([dict(waiting_days=5.0,from_email="synthetic@example.test",
                                  project_ids=p0,subject="Synthetic unanswered inquiry",
                                  uid="SYNTH-UNANSWERED-1")])
    manual=pd.DataFrame([dict(status="활성",priority="긴급",issue_id="SYNTH-MANUAL-1",
                              issue_type="Synthetic Manual Task",project_id=p1,
                              institution="Canary Uni",service="mRNA-Seq",
                              reason="Synthetic manual issue",evidence="Synthetic evidence")])
    crm=pd.DataFrame([dict(waiting_days=5.0,record_id="SYNTH-SF-1",
                           request_text="Synthetic CRM",customer_name="Synthetic CRM",
                           institution="Canary Uni",customer_email="crm@example.test",
                           mail_sent_after_enquiry="No",email_followup_status="Needs response",
                           record_status="Open")])
    quote=pd.DataFrame([dict(quotation_id="",invoice_number="SYNTH-INV-1",
                             matched_project_id=p2,match_type="Ambiguous")])
    action,review=run_case(ns,board,unanswered,manual,crm,quote)
    check(len(action)==861,"REAL_ACTION_RECORD_COUNT_861")
    check(len(review)==1,"REAL_REVIEW_RECORD_COUNT_1")
    check(action["task_id"].is_unique,"ACTION_TASK_ID_UNIQUE")
    check(review["review_id"].is_unique,"REVIEW_ID_UNIQUE")
    generic={"SIF 제출 요청","SIF 수정","프로젝트 조치","장기 정체"}
    check(not any((action["project_id"].isin(suppressed)) &
                  (action["task_type"].isin(generic))),
          "PREPAYMENT_GENERIC_SIF_ALERT_ZERO")
    check(set(action.loc[action["project_id"]==p0,"task_type"])==
          {"미회신 고객 문의"},"SAME_PROJECT_UNANSWERED_PRESERVED")
    check(set(action.loc[action["project_id"]==p1,"task_type"])==
          {"Synthetic Manual Task"},"SAME_PROJECT_MANUAL_ISSUE_PRESERVED")
    check(len(action.loc[action["task_type"]=="Salesforce 문의"])==1,
          "INDEPENDENT_CRM_TASK_PRESERVED")
    check("Quotation-Invoice 모호" in set(review.loc[
          review["project_id"]==p2,"review_type"]),
          "SAME_PROJECT_REVIEW_PRESERVED")
    check(action.loc[action["project_id"]==p0,"customer_name"].iat[0].
          startswith("SYNTHETIC_PI_"),"SAME_PROJECT_CUSTOMER_NAME_PRESERVED")
    check(review.loc[review["project_id"]==p2,"institution"].iat[0]=="Canary Uni",
          "SAME_PROJECT_REVIEW_METADATA_PRESERVED")
    old_action,old_review=run_case(
        ns,board.loc[board["attention"]=="Yes"],unanswered,manual,crm,quote)
    check(old_action.loc[old_action["project_id"]==p0,"customer_name"].iat[0]=="확인 필요",
          "OLD_FILTER_CAUSES_CUSTOMER_NAME_LOSS_REPRODUCED")
    check(old_review.loc[old_review["project_id"]==p2,"institution"].iat[0]=="",
          "OLD_FILTER_CAUSES_REVIEW_METADATA_LOSS_REPRODUCED")
    check(len(old_action)==len(action) and len(old_review)==len(review),
          "TASK_COUNTS_PRESERVED_WITH_BETTER_CONTEXT")
    again,re_again=run_case(ns,board,unanswered,manual,crm,quote)
    check(set(again["task_id"])==set(action["task_id"]),
          "RERUN_STABLE_ACTION_IDS")
    check(set(re_again["review_id"])==set(review["review_id"]),
          "RERUN_STABLE_REVIEW_IDS")
    check(hashlib.sha256(Path(p).read_bytes()).hexdigest()==SHA,
          "PRODUCTION_SOURCE_UNTOUCHED")
    print("REAL_GENERATOR_REGRESSION_PASS",len(PASS),flush=True)
    print("SYNTHETIC_PROJECTS",n,"ACTIONS",len(action),
          "REVIEWS",len(review),"PREPAYMENT_SIF",len(suppressed),flush=True)
    print("NO_PRODUCTION_DB_SHEET_MAIL_CRM_WRITES",True,flush=True)

if __name__=="__main__":
    main()
