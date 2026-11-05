#!/usr/bin/env python3
"""Feishu Base native KPI table + gallery cards; no external Vercel web."""
import datetime as dt
import os
import sys
import urllib.parse
from qq_mail_ingest import SafeError,api,auth,get_fields,list_all,plain_field
from setup_sales_web import BASE_URL,EXPECTED_BASE,list_views
from native_kpi_compute import KST,SRC,VIEWS,compute,val
from native_kpi_financial import financial

NAME="01 핵심 KPI 대시보드"
FIELDS={"KPI Key":1,"섹션":1,"지표":1,"값":2,"단위":1,
        "기간":1,"검증 상태":1,"상세 설명":1,"원본 화면":1,"갱신 시각":1}

def table_ids(token,root):
    tables={}
    for r in list_all(root+"/tables",token,"dashboard_tables"):
        n,tid=r.get("name"),r.get("table_id")
        if not n or not tid or n in tables:
            raise SafeError("DASHBOARD_BAD_TABLE_METADATA")
        tables[n]=tid
    return tables

def load(token,root,tables):
    source={};links={}
    for name,view in zip(SRC,VIEWS):
        if name not in tables:raise SafeError("DASHBOARD_SOURCE_NOT_FOUND_"+name.replace(" ","_"))
        tid=tables[name];path=root+"/tables/"+urllib.parse.quote(tid,safe="")
        records=list_all(path+"/records",token,"dashboard_source_read")
        source[name]=[r.get("fields") or {} for r in records]
        vid=list_views(token,path).get(view)
        links[name]=BASE_URL+"?table="+tid+("&view="+vid if vid else "")
        print("DASHBOARD_SOURCE_"+name.replace(" ","_")+"="+str(len(records)))
    return source,links

def ensure_table(token,root,tables):
    tid=tables.get(NAME)
    if not tid:
        api("POST",root+"/tables",token,data={"table":{"name":NAME,
            "default_view_name":"02 KPI 상세",
            "fields":[{"field_name":k,"type":t} for k,t in FIELDS.items()]}},
            action="dashboard_create_table")
        tid=table_ids(token,root).get(NAME)
    if not tid:raise SafeError("DASHBOARD_TABLE_NOT_VERIFIED")
    path=root+"/tables/"+urllib.parse.quote(tid,safe="")
    fields={f.get("field_name"):f.get("type") for f in get_fields(token,path)}
    if any(k in fields and fields[k]!=t for k,t in FIELDS.items()):
        raise SafeError("DASHBOARD_FIELD_TYPE_CONFLICT")
    for k,t in FIELDS.items():
        if k not in fields:
            api("POST",path+"/fields",token,data={"field_name":k,"type":t},
                action="dashboard_add_field")
    check={f.get("field_name"):f.get("type") for f in get_fields(token,path)}
    if any(check.get(k)!=t for k,t in FIELDS.items()):
        raise SafeError("DASHBOARD_SCHEMA_READBACK_FAIL")
    return tid,path

def views(token,tid,path):
    current=list_views(token,path)
    grid=current.get("02 KPI 상세") or next(iter(current.values()),None)
    if not grid:raise SafeError("DASHBOARD_NO_GRID")
    gallery=current.get("01 KPI 카드")
    if not gallery:
        try:
            api("POST",path+"/views",token,
                data={"view_name":"01 KPI 카드","view_type":"gallery"},
                action="dashboard_gallery")
            gallery=list_views(token,path).get("01 KPI 카드")
        except SafeError:
            print("DASHBOARD_GALLERY_NOT_SUPPORTED_FALLBACK_GRID=1")
    card=gallery or grid
    print("DASHBOARD_GRID_URL="+BASE_URL+"?table="+tid+"&view="+grid)
    print("DASHBOARD_CARD_URL="+BASE_URL+"?table="+tid+"&view="+card)
    return card

def equal(fields,row):
    from native_kpi_financial import amount
    return all(amount(fields.get(k))==amount(v) if k=="값"
               else val(fields.get(k))==str(v) for k,v in row.items())

def upsert(token,path,desired):
    old=list_all(path+"/records",token,"dashboard_stored_records")
    index={}
    for r in old:
        k=val((r.get("fields") or {}).get("KPI Key"))
        if k in index:raise SafeError("DASHBOARD_DUPLICATE_KEY")
        index[k]=r
    create=[];update=[];unchanged=0
    for row in desired:
        previous=index.get(row["KPI Key"])
        if previous and equal(previous.get("fields") or {},row):
            unchanged+=1
        elif previous:
            update.append({"record_id":previous["record_id"],"fields":row})
        else:
            create.append({"fields":row})
    for action,items in (("batch_create",create),("batch_update",update)):
        for i in range(0,len(items),25):
            chunk=items[i:i+25]
            result=api("POST",path+"/records/"+action,token,
                       data={"records":chunk},action="dashboard_"+action)
            if len(result.get("records") or [])!=len(chunk):
                raise SafeError("DASHBOARD_WRITE_UNVERIFIED")
    verified=list_all(path+"/records",token,"dashboard_readback")
    recorded={val((r.get("fields") or {}).get("KPI Key")):r.get("fields") or {}
              for r in verified}
    for row in desired:
        if row["KPI Key"] not in recorded or not equal(recorded[row["KPI Key"]],row):
            raise SafeError("DASHBOARD_READBACK_FAILED")
    print("DASHBOARD_APPLY_PASS created="+str(len(create))+
          " updated="+str(len(update))+" unchanged="+str(unchanged)+
          " other_table_writes=0")

def main():
    if os.environ.get("FEISHU_BASE_APP_TOKEN")!=EXPECTED_BASE:
        raise SafeError("DASHBOARD_WRONG_BASE")
    mode=os.environ.get("FEISHU_DASHBOARD_MODE","plan")
    if mode not in ("plan","apply"):raise SafeError("DASHBOARD_BAD_MODE")
    token,root=auth();tables=table_ids(token,root)
    source,links=load(token,root,tables)
    now=dt.datetime.now(KST)
    metrics=compute(source,links,now)+financial(source,links,now)
    if len({x["KPI Key"] for x in metrics})!=len(metrics):
        raise SafeError("DASHBOARD_DUPLICATE_METRIC_KEY")
    print("DASHBOARD_METRIC_COUNT="+str(len(metrics)))
    if mode=="plan":
        print("DASHBOARD_PLAN_PASS writes=0")
        return
    tid,path=ensure_table(token,root,tables)
    view=views(token,tid,path)
    upsert(token,path,metrics)
    print("DASHBOARD_HOME_URL="+BASE_URL+"?table="+tid+"&view="+view)

if __name__=="__main__":
    try:main()
    except Exception as exc:
        reason=str(exc) if isinstance(exc,SafeError) else type(exc).__name__
        print("DASHBOARD_FAILED:"+reason,file=sys.stderr)
        sys.exit(1)
