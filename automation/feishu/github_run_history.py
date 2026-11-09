#!/usr/bin/env python3
"""GitHub Actions source/sink run evidence -> Feishu native operations history.

This monitor is independent of the two writers. Never changes SFDC records,
QQ mail, Invoice, Payment, Monthly, source manifests, or other Feishu tables.
Main-branch scheduled/manual/push executions are kept separate from PR tests.
GitHub run SUCCESS alone is never treated as proof of source freshness.
"""
import datetime as dt
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

from qq_mail_ingest import SafeError,api,auth,list_all,get_fields,plain_field
from setup_sales_web import get_view,list_views,resolve_view
from sort_sales_home import get_group_items,get_sort_items,visible_items,run_cli

BASE="IpMkbUD0vaFqtYs93a3csXtdn1b"
BASE_URL="https://ocnz4cb25scn.feishu.cn/base/"+BASE
REPO="kimtk94/Codex"
TABLE="Automation Run History"
VIEW_OPERATION="최근 운영 실행"
VIEW_PROBLEMS="확인 필요"
VIEW_ALL="전체 실행 기록"
WORKFLOWS=(
    ("SFDC Report","sfdc-three-report-email-digestion.yml"),
    ("Feishu Payment·Online·Monthly","feishu-sources-unified.yml"),
)
KST=ZoneInfo("Asia/Seoul")
FIELDS=(
    ("실행명",1),("Run Key",1),("워크플로",1),("운영 여부",1),
    ("실행 구분",1),("실행 상태",1),("원본 검증",1),("결과 검증",1),
    ("검증 상태",1),("단계별 결과",1),
    ("시작 KST",1),("종료 KST",1),("실제 소요 분",2),
    ("예약 시간 KST",1),("다음 예약 KST",1),
    ("실행 링크",15),("최종 확인 KST",1),
)
VISIBLE=("실행명","실행 상태","원본 검증","결과 검증","단계별 결과",
         "실행 구분","시작 KST","종료 KST","다음 예약 KST","실행 링크")
VIEW_FILTERS=((VIEW_OPERATION,"운영 여부","OPERATION"),
              (VIEW_PROBLEMS,"검증 상태","CHECK"),(VIEW_ALL,None,None))


def gh(path):
    token=os.environ.get("GITHUB_TOKEN","").strip()
    if not token:
        raise SafeError("HISTORY_MISSING_GITHUB_TOKEN")
    url="https://api.github.com"+path
    req=urllib.request.Request(url,headers={
        "Accept":"application/vnd.github+json",
        "Authorization":"Bearer "+token,
        "X-GitHub-Api-Version":"2022-11-28",
        "User-Agent":"css-feishu-run-history/1.0",
    })
    try:
        with urllib.request.urlopen(req,timeout=25) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        raise SafeError("HISTORY_GITHUB_HTTP_"+str(exc.code)) from None
    except (urllib.error.URLError,TimeoutError,ValueError):
        raise SafeError("HISTORY_GITHUB_UNAVAILABLE") from None


def parse_when(value):
    if not value:
        return None
    try:
        result=dt.datetime.fromisoformat(str(value).replace("Z","+00:00"))
    except ValueError:
        raise SafeError("HISTORY_INVALID_RUN_DATETIME") from None
    if result.tzinfo is None:
        raise SafeError("HISTORY_NAIVE_RUN_DATETIME")
    return result.astimezone(dt.timezone.utc)


def show_time(t):
    return t.astimezone(KST).strftime("%Y-%m-%d %H:%M:%S") if t else ""


def schedule_from_yaml(text,now):
    """Use actual workflow cron declarations; never copy a separate schedule."""
    found=re.search(r"(?m)^  schedule:\s*\n((?:    .*\n)*)",text)
    if not found:
        raise SafeError("HISTORY_SCHEDULE_NOT_FOUND")
    tokens=re.findall(r"(?m)^\s+- cron: ['\"]([^'\"]+)['\"]",found.group(1))
    if not tokens:
        raise SafeError("HISTORY_CRON_EMPTY")
    slots=set()
    for cron in tokens:
        parts=cron.split()
        if len(parts)!=5 or parts[2:]!=["*","*","*"]:
            raise SafeError("HISTORY_UNSUPPORTED_CRON")
        try:
            minutes=[int(x) for x in parts[0].split(",")]
            hours=[int(x) for x in parts[1].split(",")]
        except ValueError:
            raise SafeError("HISTORY_UNSUPPORTED_CRON") from None
        if any(x not in range(60) for x in minutes) or any(h not in range(24) for h in hours):
            raise SafeError("HISTORY_INVALID_CRON_CLOCK")
        for h in hours:
            for m in minutes:
                slots.add(((h+9)%24,m))
    next_time=None
    local=now.astimezone(KST)
    for day in range(3):
        date=local.date()+dt.timedelta(days=day)
        for hour,minute in sorted(slots):
            candidate=dt.datetime.combine(date,dt.time(hour,minute,tzinfo=KST))
            if candidate>local and (next_time is None or candidate<next_time):
                next_time=candidate
    if next_time is None:
        raise SafeError("HISTORY_NEXT_SCHEDULE_UNAVAILABLE")
    return ", ".join(f"{h:02d}:{m:02d}" for h,m in sorted(slots)),show_time(next_time)


def schedule_map(now):
    root=Path(__file__).resolve().parents[2]
    result={}
    for label,filename in WORKFLOWS:
        file=root/".github/workflows"/filename
        if not file.is_file():
            raise SafeError("HISTORY_WORKFLOW_FILE_MISSING")
        result[label]=schedule_from_yaml(file.read_text(encoding="utf-8"),now)
    return result


def get_jobs(run_id):
    data=gh("/repos/"+REPO+"/actions/runs/"+str(run_id)+"/jobs?per_page=100")
    jobs=data.get("jobs")
    if not isinstance(jobs,list):
        raise SafeError("HISTORY_GITHUB_JOBS_UNVERIFIED")
    return jobs


def step_state(jobs,needle):
    matches=[]
    for job in jobs:
        for step in job.get("steps") or []:
            if needle in (step.get("name") or ""):
                matches.append(step)
    if len(matches)>1:
        raise SafeError("HISTORY_AMBIGUOUS_VALIDATION_STEP")
    if not matches:
        return "NOT_EVALUATED"
    step=matches[0]
    state=step.get("conclusion") or step.get("status") or "PENDING"
    return {
        "success":"PASS","failure":"FAIL","cancelled":"CANCELLED",
        "skipped":"NOT_EVALUATED","completed":"PENDING",
        "in_progress":"PENDING","queued":"PENDING",
    }.get(state,"PENDING")


def job_state(jobs,name):
    matches=[j for j in jobs if j.get("name")==name]
    if len(matches)>1:
        raise SafeError("HISTORY_DUPLICATE_JOB")
    if not matches:
        return "NOT_EVALUATED"
    j=matches[0]
    status=j.get("conclusion") or j.get("status")
    return {"success":"PASS","failure":"FAIL","skipped":"NOT_EVALUATED",
            "cancelled":"CANCELLED","in_progress":"PENDING","queued":"PENDING",
            "completed":"PENDING"}.get(status,"PENDING")


def result_states(label,run,jobs):
    """Step and job readback, NOT Github checkmark, determines evidence."""
    if label=="SFDC Report":
        parts={
            "mail":step_state(jobs,"Read authorized subscription mail and conditionally stage"),
            "freshness":step_state(jobs,"Check current 09/12/17 report slot after staging"),
            "quote":step_state(jobs,"Publish only SFDC Quote Review and Weekly KPI"),
            "chart":step_state(jobs,"Refresh and verify native Quote trend dashboards"),
        }
        source="PASS" if parts["mail"]=="PASS" and parts["freshness"]=="PASS" else (
            "FAIL" if "FAIL" in (parts["mail"],parts["freshness"]) else
            "NOT_EVALUATED" if all(parts[k]=="NOT_EVALUATED" for k in ("mail","freshness"))
            else "PENDING")
        sink="PASS" if parts["quote"]=="PASS" and parts["chart"]=="PASS" else (
            "PARTIAL" if "PASS" in (parts["quote"],parts["chart"]) else
            "FAIL" if "FAIL" in (parts["quote"],parts["chart"]) else
            "NOT_EVALUATED" if parts["quote"]==parts["chart"]=="NOT_EVALUATED" else "PENDING")
    else:
        parts={name:job_state(jobs,name) for name in ("ingest","lifecycle","payment","monthly")}
        source=parts["ingest"]
        outcomes=(parts["lifecycle"],parts["payment"],parts["monthly"])
        sink="PASS" if all(x=="PASS" for x in outcomes) else (
            "PARTIAL" if "PASS" in outcomes and ("FAIL" in outcomes or "CANCELLED" in outcomes) else
            "FAIL" if "FAIL" in outcomes else
            "NOT_EVALUATED" if all(x=="NOT_EVALUATED" for x in outcomes) else "PENDING")
    completed=run.get("status")=="completed"
    if completed and run.get("conclusion")=="success" and source=="NOT_EVALUATED":
        verdict="TEST_ONLY"
    elif run.get("conclusion") in ("failure","cancelled","timed_out") or source=="FAIL" or sink in ("FAIL","PARTIAL"):
        verdict="CHECK"
    elif not completed or source=="PENDING" or sink=="PENDING":
        verdict="RUNNING"
    elif source==sink=="PASS":
        verdict="PASS"
    else:
        verdict="CHECK" # A green job without source/sink proof is not PASS.
    return source,sink,verdict,parts


def build_row(label,run,jobs,schedule,now):
    run_id=run.get("id")
    if not isinstance(run_id,int) or run_id<1:
        raise SafeError("HISTORY_RUN_ID_UNVERIFIED")
    event=run.get("event")
    if event not in ("schedule","workflow_dispatch","push","pull_request","workflow_run"):
        raise SafeError("HISTORY_UNKNOWN_EVENT")
    if run.get("head_repository",{}):
        repo=(run.get("head_repository") or {}).get("full_name")
        if repo and repo!=REPO and event!="pull_request":
            raise SafeError("HISTORY_RUN_WRONG_REPOSITORY")
    start=parse_when(run.get("run_started_at") or run.get("created_at"))
    end=parse_when(run.get("updated_at")) if run.get("status")=="completed" else None
    if not start:
        raise SafeError("HISTORY_RUN_START_MISSING")
    link=run.get("html_url")
    if link!="https://github.com/"+REPO+"/actions/runs/"+str(run_id):
        raise SafeError("HISTORY_RUN_URL_MISMATCH")
    source,sink,verdict,parts=result_states(label,run,jobs)
    kind={"schedule":"예약","workflow_dispatch":"수동","push":"코드 변경",
          "pull_request":"PR 테스트","workflow_run":"연계 실행"}[event]
    operation="TEST" if event=="pull_request" or verdict=="TEST_ONLY" else "OPERATION"
    minutes=round((end-start).total_seconds()/60,2) if end else None
    if minutes is not None and minutes<0:
        raise SafeError("HISTORY_DURATION_NEGATIVE")
    state={"completed":str(run.get("conclusion") or "UNKNOWN").upper(),
           "in_progress":"RUNNING","queued":"QUEUED","requested":"QUEUED",
           "waiting":"QUEUED","pending":"QUEUED"}.get(run.get("status"),"UNKNOWN")
    return {
        "실행명":label+" · "+show_time(start),
        "Run Key":label.split(" ")[0].upper()+":"+str(run_id),
        "워크플로":label,"운영 여부":operation,
        "실행 구분":kind,"실행 상태":state,
        "원본 검증":source,"결과 검증":sink,"검증 상태":verdict,
        "단계별 결과":" / ".join(k+"="+v for k,v in parts.items()),
        "시작 KST":show_time(start),"종료 KST":show_time(end),
        "실제 소요 분":minutes,
        "예약 시간 KST":schedule[0],"다음 예약 KST":schedule[1],
        "실행 링크":{"text":"GitHub 실행 로그","link":link},
        "최종 확인 KST":show_time(now),
    }


def collect_rows(now):
    schedules=schedule_map(now)
    result=[]
    for label,filename in WORKFLOWS:
        query=urllib.parse.urlencode({"per_page":100})
        data=gh("/repos/"+REPO+"/actions/workflows/"+filename+"/runs?"+query)
        runs=data.get("workflow_runs")
        if not isinstance(runs,list):
            raise SafeError("HISTORY_GITHUB_RUNS_UNVERIFIED")
        operating=[r for r in runs if r.get("head_branch")=="main"
                   and r.get("event") in ("schedule","workflow_dispatch","push","workflow_run")]
        testing=[r for r in runs if r.get("event")=="pull_request"]
        if not operating:
            raise SafeError("HISTORY_NO_MAIN_BRANCH_OPERATING_RUNS")
        for run in operating[:12]+testing[:5]:
            result.append(build_row(label,run,get_jobs(run["id"]),schedules[label],now))
    keys=[r["Run Key"] for r in result]
    if len(set(keys))!=len(keys):
        raise SafeError("HISTORY_DUPLICATE_RUN_KEY")
    print("HISTORY_GITHUB_SOURCE_PASS runs="+str(len(result))+
          " operating="+str(sum(r["운영 여부"]=="OPERATION" for r in result))+
          " checks="+str(sum(r["검증 상태"]=="CHECK" for r in result)))
    return result


def table_path(root,tid):
    return root+"/tables/"+urllib.parse.quote(tid,safe="")


def ensure_table(token,root):
    names={}
    for item in list_all(root+"/tables",token,"history_tables"):
        name=item.get("name")
        if name in names:
            raise SafeError("HISTORY_DUPLICATE_FEISHU_TABLE")
        names[name]=item.get("table_id")
    tid=names.get(TABLE)
    if not tid:
        created=api("POST",root+"/tables",token,data={"table":{
            "name":TABLE,"default_view_name":VIEW_OPERATION,
            "fields":[{"field_name":n,"type":t} for n,t in FIELDS],
        }},action="history_create_table")
        tid=(created.get("table") or {}).get("table_id") or created.get("table_id")
        if not tid:
            refreshed=list_all(root+"/tables",token,"history_table_readback")
            tid=next((x.get("table_id") for x in refreshed if x.get("name")==TABLE),None)
        if not tid:
            raise SafeError("HISTORY_TABLE_NOT_CREATED")
    path=table_path(root,tid)
    types={f.get("field_name"):f.get("type") for f in get_fields(token,path)}
    for name,typ in FIELDS:
        if name not in types:
            api("POST",path+"/fields",token,data={"field_name":name,"type":typ},
                action="history_add_field")
        elif types[name]!=typ:
            raise SafeError("HISTORY_FIELD_TYPE_MISMATCH")
    types={f.get("field_name"):f.get("type") for f in get_fields(token,path)}
    if any(types.get(name)!=typ for name,typ in FIELDS):
        raise SafeError("HISTORY_SCHEMA_READBACK_FAILED")
    return tid,path


def filter_config(field_id,value):
    return {"conjunction":"and","conditions":[{
        "field_id":field_id,"operator":"is",
        "value":json.dumps([value],ensure_ascii=False),
    }]}


def matches_filter(view,field_id,value):
    filt=((view.get("property") or {}).get("filter_info") or {})
    cond=filt.get("conditions") or []
    if value is None:
        return not cond
    return filt.get("conjunction")=="and" and len(cond)==1 and (
        cond[0].get("field_id")==field_id and
        cond[0].get("operator")=="is" and
        json.loads(cond[0].get("value") or "null")==[value])


def ensure_views(token,path):
    fields={f.get("field_name"):f.get("field_id") for f in get_fields(token,path)}
    views={}
    for name,field,value in VIEW_FILTERS:
        vid,_=resolve_view(token,path,name,field is not None)
        current=get_view(token,path,vid)
        field_id=fields.get(field) if field else None
        if field and not field_id:
            raise SafeError("HISTORY_FILTER_FIELD_NOT_FOUND")
        if current.get("view_name")!=name or not matches_filter(current,field_id,value):
            info=filter_config(field_id,value) if field else {"conjunction":"and","conditions":[]}
            api("PATCH",path+"/views/"+urllib.parse.quote(vid,safe=""),token,
                data={"view_name":name,"property":{"filter_info":info}},
                action="history_configure_view")
        after=get_view(token,path,vid)
        if after.get("view_name")!=name or after.get("view_type")!="grid" or not matches_filter(after,field_id,value):
            raise SafeError("HISTORY_VIEW_READBACK_FAILED")
        views[name]=vid
    return views


def match_sort(doc,field_id):
    entries=get_sort_items(doc)
    return isinstance(entries,list) and len(entries)==1 and isinstance(entries[0],dict) and (
        entries[0].get("field",entries[0].get("field_id")) in ("시작 KST",field_id) and
        entries[0].get("desc") is True)


def match_group(doc,field_id):
    entries=get_group_items(doc)
    return isinstance(entries,list) and len(entries)==1 and isinstance(entries[0],dict) and (
        entries[0].get("field",entries[0].get("field_id")) in ("워크플로",field_id) and
        entries[0].get("desc") is False)


def match_visible(doc,field_ids):
    entries=visible_items(doc)
    if not isinstance(entries,list):
        return False
    names=[field_ids.get(x,x) if isinstance(x,str) else
           field_ids.get(x.get("field_id",x.get("field")),x.get("field_id",x.get("field")))
           for x in entries]
    return names==list(VISIBLE)


def ensure_layout(tid,views,token,path):
    fields=get_fields(token,path)
    by_name={f.get("field_name"):f.get("field_id") for f in fields}
    by_id={v:k for k,v in by_name.items()}
    if not by_name.get("워크플로") or not by_name.get("시작 KST"):
        raise SafeError("HISTORY_LAYOUT_FIELDS_MISSING")
    for name,view_id in views.items():
        for action,expected,desired in (
            ("group",lambda x:match_group(x,by_name["워크플로"]),
             {"group_config":[{"field":"워크플로","desc":False}]}),
            ("sort",lambda x:match_sort(x,by_name["시작 KST"]),
             {"sort_config":[{"field":"시작 KST","desc":True}]}),
            ("visible-fields",lambda x:match_visible(x,by_id),
             {"visible_fields":list(VISIBLE)}),
        ):
            before=run_cli("+view-get-"+action,BASE,tid,view_id)
            if not expected(before):
                run_cli("+view-set-"+action,BASE,tid,view_id,desired)
            if not expected(run_cli("+view-get-"+action,BASE,tid,view_id)):
                raise SafeError("HISTORY_LAYOUT_READBACK_FAILED_"+action)
        print("HISTORY_VIEW_LAYOUT_PASS view="+name+
              " group=workflow sort=started_desc columns="+str(len(VISIBLE)))


def visible_equal(old,desired):
    for name,value in desired.items():
        if name=="최종 확인 KST":
            continue
        existing=old.get(name)
        if isinstance(value,dict):
            if (plain_field(existing)!=value["text"] or
                    value["link"] not in json.dumps(existing,ensure_ascii=False)):
                return False
        elif value is None:
            if existing not in (None,"",[]):
                return False
        elif isinstance(value,(float,int)):
            try:
                if abs(float(plain_field(existing))-float(value))>0.01:
                    return False
            except (ValueError,TypeError):
                return False
        elif plain_field(existing).strip()!=str(value).strip():
            return False
    return True


def write_rows(token,path,rows):
    existing=list_all(path+"/records",token,"history_list_records")
    indexed={}
    for record in existing:
        key=plain_field((record.get("fields") or {}).get("Run Key")).strip()
        if not key or key in indexed or not record.get("record_id"):
            raise SafeError("HISTORY_EXISTING_DUPLICATE_OR_BAD_KEY")
        indexed[key]=record
    create=[]; update=[]; same=0
    for item in rows:
        key=item["Run Key"]
        old=indexed.get(key)
        if old and visible_equal(old.get("fields") or {},item):
            same+=1
            continue
        if old:
            update.append({"record_id":old["record_id"],"fields":item})
        else:
            create.append({"fields":item})
    for action,items in (("batch_create",create),("batch_update",update)):
        for k in range(0,len(items),25):
            chunk=items[k:k+25]
            response=api("POST",path+"/records/"+action,token,
                         data={"records":chunk},action="history_"+action)
            if len(response.get("records") or [])!=len(chunk):
                raise SafeError("HISTORY_BATCH_COMMIT_MISMATCH")
    after=list_all(path+"/records",token,"history_records_readback")
    observed={}
    for item in after:
        key=plain_field((item.get("fields") or {}).get("Run Key")).strip()
        if not key or key in observed:
            raise SafeError("HISTORY_READBACK_DUPLICATE_KEY")
        observed[key]=item.get("fields") or {}
    if any(r["Run Key"] not in observed or not visible_equal(observed[r["Run Key"]],r)
           for r in rows):
        raise SafeError("HISTORY_SOURCE_TO_SINK_READBACK_MISMATCH")
    print("HISTORY_SINK_READBACK_PASS desired="+str(len(rows))+
          " created="+str(len(create))+" updated="+str(len(update))+
          " unchanged="+str(same)+" records_deleted=0")


def main():
    if os.environ.get("FEISHU_BASE_APP_TOKEN")!=BASE:
        raise SafeError("HISTORY_WRONG_BASE")
    now=dt.datetime.now(dt.timezone.utc)
    rows=collect_rows(now) # All GitHub reads before ANY Feishu writes.
    token,root=auth()
    tid,path=ensure_table(token,root)
    views=ensure_views(token,path)
    write_rows(token,path,rows)
    ensure_layout(tid,views,token,path)
    for name,vid in views.items():
        print("HISTORY_FEISHU_VIEW_URL "+name+"="+BASE_URL+"?table="+tid+"&view="+vid)
    print("HISTORY_APPLY_PASS schedule_read_from_workflows=2 "+
          "source_and_sink_verified_separately=TRUE")


if __name__=="__main__":
    try:
        main()
    except Exception as exc:
        reason=str(exc) if isinstance(exc,SafeError) else type(exc).__name__
        print("HISTORY_FAILED="+reason,file=sys.stderr)
        sys.exit(1)
