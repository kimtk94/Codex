#!/usr/bin/env python3
"""Stage source-verified X/SAM links and CMS invoices inside Feishu Sales Base.

GitHub Actions: readonly plan on feature, idempotent apply on main/schedule.
Never split AMEA-level %/paid status into an X row. No deletes anywhere.
"""
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.parse
from collections import Counter

from qq_mail_ingest import auth,api,list_all,SafeError
from sales_metrics_sync import (EXPECTED_BASE,CSS_SHEET,UNIFIED_SHEET,
                                sheets_session,req_sheet,table_catalog,
                                raw_value,equivalent,timestamp)
from x_project_lineage import build,LINK_SCHEMAS

def source_rows():
    session=sheets_session()
    sources={}
    for book,name,limit in [
        (CSS_SHEET,"CSS Project Dashboard",800),
        (CSS_SHEET,"CSS Project Timeline",6000),
        (UNIFIED_SHEET,"BI Project Lifecycle Overview",450),
        (UNIFIED_SHEET,"Feishu Latest Online",300),
        (UNIFIED_SHEET,"Feishu Latest Outstanding",550),
        (UNIFIED_SHEET,"Feishu Latest eTax",350),
        (UNIFIED_SHEET,"Feishu Source Manifest",30),
    ]:
        sources[name]=req_sheet(session,book,name,limit)
    expected={
        "CSS Project Dashboard":{"project_id","h_project_numbers","sam_numbers"},
        "CSS Project Timeline":{"project_id","sam_numbers","h_project_numbers"},
        "BI Project Lifecycle Overview":{"AMEA","Project / Sub-project"},
        "Feishu Latest Online":{"Contract Number","Sub-Project Number","Sales",
                                "Project Status"},
        "Feishu Latest Outstanding":{"CMS Invoice Number","Project Number",
                                      "Quotation Number","Invoice Amount","Sales"},
        "Feishu Latest eTax":{"CMS Invoice Num","Project Number",
                              "Quotation Number","Amount","Sales"},
        "Feishu Source Manifest":{"Source","Source Date","Synced At KST","Schema"},
    }
    # req_sheet validated basic required headers globally; this pipeline must
    # inspect the X/SAM-specific columns independently.
    for name,required in expected.items():
        if not sources[name]:
            raise SafeError("X_BRIDGE_EMPTY_SOURCE")
        if not required.issubset(sources[name][0]):
            raise SafeError("X_BRIDGE_SOURCE_SCHEMA_INCOMPLETE")
    manifest={str(r.get("Source") or "").strip():r
              for r in sources["Feishu Source Manifest"]}
    row=manifest.get("Online-Project",{})
    if row.get("Schema")!="BASE_FIELDS":
        raise SafeError("X_BRIDGE_ONLINE_MANIFEST_UNVERIFIED")
    try:
        stamp=dt.datetime.fromisoformat(str(row["Synced At KST"]))
    except (ValueError,KeyError):
        raise SafeError("X_BRIDGE_ONLINE_SYNC_TIME_MISSING") from None
    now=dt.datetime.now(dt.timezone(dt.timedelta(hours=9)))
    if stamp.tzinfo is None or not 0<=(now-stamp).total_seconds()<=48*3600:
        raise SafeError("X_BRIDGE_ONLINE_MIRROR_STALE")
    if not sources["CSS Project Dashboard"] or not sources["Feishu Latest Online"]:
        raise SafeError("X_BRIDGE_CORE_SOURCE_EMPTY")
    return sources

def path_of(root,table_id):
    return root+"/tables/"+urllib.parse.quote(table_id,safe="")

def ensure_tables(token,root):
    catalog=table_catalog(token,root)
    paths={}
    for name,fields in LINK_SCHEMAS.items():
        existing=catalog.get(name,[])
        if len(existing)>1:raise SafeError("X_BRIDGE_DUPLICATE_TABLE")
        spec=[{"field_name":n,"type":t} for n,t in fields]
        if not existing:
            api("POST",root+"/tables",token,data={
                "table":{"name":name,"default_view_name":"All","fields":spec}
            },action="x_bridge_create_table")
            catalog=table_catalog(token,root)
            existing=catalog.get(name,[])
            if len(existing)!=1:
                raise SafeError("X_BRIDGE_TABLE_CREATION_NOT_VERIFIED")
            print("X_BRIDGE_TABLE_CREATED="+name)
        path=path_of(root,existing[0])
        found=list_all(path+"/fields",token,"x_bridge_fields")
        actual={r.get("field_name"):r.get("type") for r in found}
        if any(actual.get(n)!=t for n,t in fields):
            raise SafeError("X_BRIDGE_TABLE_SCHEMA_MISMATCH")
        paths[name]=path
    return paths

def retry_list(token,uri,label):
    for attempt in range(4):
        try:return list_all(uri,token,label)
        except SafeError as e:
            if not re.search(r"HTTP_(?:429|500|502|503|504)(?!\d)",str(e)) or attempt==3:
                raise
            time.sleep((attempt+1)*2)

def batch(token,path,method,rows):
    for offset in range(0,len(rows),25):
        group=rows[offset:offset+25]
        api("POST",path+"/records/"+method,token,data={"records":group},
            action="x_bridge_"+method)
        # All-or-none response must give exactly one record per source row.
        # Readback later independently verifies full data.
        time.sleep(.12)

def apply_rows(token,path,rows,table_name):
    existing=retry_list(token,path+"/records","x_bridge_existing")
    indexed={}
    for record in existing:
        key=raw_value((record.get("fields") or {}).get("Source Key")).strip()
        if not key:continue
        if key in indexed:raise SafeError("X_BRIDGE_DUPLICATE_SOURCE_KEY")
        indexed[key]=record
    creates=[];updates=[];unchanged=0;seen=set()
    now=timestamp()
    for source in rows:
        row={**source,"Record State":"CURRENT"}
        key=row["Source Key"]
        if key in seen:raise SafeError("X_BRIDGE_DUPLICATE_DESIRED_KEY")
        seen.add(key)
        previous=indexed.get(key)
        original=(previous or {}).get("fields") or {}
        if previous and equivalent(original,row):
            unchanged+=1
            continue
        changes={**row,"Last Sync KST":now}
        if previous:
            updates.append({"record_id":previous["record_id"],"fields":changes})
        else:
            creates.append({"fields":changes})
    # Source keys no longer present are retained for audit but explicitly
    # excluded from the current state and all live dashboard views.
    stale=0
    for key,rec in indexed.items():
        if key not in seen and raw_value((rec.get("fields") or {}).get("Record State"))!="SOURCE_NOT_IN_LATEST":
            updates.append({"record_id":rec["record_id"],"fields":{
                "Source Key":key,"Record State":"SOURCE_NOT_IN_LATEST",
                "Last Sync KST":now}})
            stale+=1
    batch(token,path,"batch_create",creates)
    batch(token,path,"batch_update",updates)
    if creates or updates:
        got=retry_list(token,path+"/records","x_bridge_readback")
    else:
        got=existing
    index={}
    for rec in got:
        key=raw_value((rec.get("fields") or {}).get("Source Key")).strip()
        if key in index:raise SafeError("X_BRIDGE_READBACK_DUPLICATE")
        index[key]=rec.get("fields") or {}
    for source in rows:
        key=source["Source Key"]
        fields=index.get(key)
        if fields is None or not equivalent(fields,{**source,"Record State":"CURRENT"}):
            raise SafeError("X_BRIDGE_SOURCE_READBACK_MISMATCH")
    for key in indexed:
        if key not in seen and (key not in index or
                raw_value(index[key].get("Record State"))!="SOURCE_NOT_IN_LATEST"):
            raise SafeError("X_BRIDGE_STALE_READBACK_MISMATCH")
    print("X_BRIDGE_TABLE_SYNC_PASS name="+table_name+
          " desired="+str(len(rows))+" created="+str(len(creates))+
          " updated="+str(len(updates))+" unchanged="+str(unchanged)+
          " stale="+str(stale)+" readback=VERIFIED")
    return path

def view_filter(token,table_path,name,conditions):
    from setup_sales_web import resolve_view,get_view,field_map
    fid=field_map(token,table_path)
    expected=[]
    for field,choice in conditions:
        if field not in fid:raise SafeError("X_BRIDGE_FILTER_FIELD_MISSING")
        expected.append((fid[field],choice))
    vid,_=resolve_view(token,table_path,name,True)
    base=table_path+"/views/"+urllib.parse.quote(vid,safe="")
    def valid():
        row=get_view(token,table_path,vid)
        info=(row.get("property") or {}).get("filter_info") or {}
        found=[]
        for c in info.get("conditions") or []:
            try:v=json.loads(c.get("value") or "null")
            except (ValueError,TypeError):return False
            if c.get("operator")!="is" or not isinstance(v,list) or len(v)!=1:return False
            found.append((c.get("field_id"),str(v[0])))
        return row.get("view_name")==name and info.get("conjunction")=="and" and sorted(found)==sorted(expected)
    if not valid():
        api("PATCH",base,token,data={
            "view_name":name,"property":{"filter_info":{
                "conjunction":"and",
                "conditions":[{"field_id":i,"operator":"is",
                               "value":json.dumps([v],ensure_ascii=False)}
                              for i,v in expected],
            }}
        },action="x_bridge_view_filter")
        if not valid():raise SafeError("X_BRIDGE_VIEW_READBACK_FAILED")
    return vid

VIEWS={
    "X Project Registry":[
        ("전체 X 프로젝트",[("Record State","CURRENT")]),
        ("내 X 프로젝트",[("Record State","CURRENT"),("Owner Scope","MY_VERIFIED")]),
        ("AMEA 정확 연결",[("Record State","CURRENT"),("AMEA Link State","EXACT_LIFECYCLE")]),
        ("H 후보 · 확인 필요",[("Record State","CURRENT"),("AMEA Link State","UNIQUE_H_CANDIDATE")]),
    ],
    "AMEA H X SAM Link":[
        ("전체 연결 관계",[("Record State","CURRENT")]),
        ("X-SAM 확정 연결",[("Record State","CURRENT"),("Link State","EXACT_SINGLE_X_CHAIN")]),
        ("공유 SAM 검토",[("Record State","CURRENT"),("Link State","SHARED_SAM_REVIEW")]),
        ("복수 X 검토",[("Record State","CURRENT"),("Link State","MULTI_X_REVIEW")]),
    ],
    "X Invoice Ledger":[
        ("전체 X Invoice",[("Record State","CURRENT")]),
        ("내 X Invoice",[("Record State","CURRENT"),("Owner Scope","MY_VERIFIED")]),
        ("X-AMEA-CMS 검증",[("Record State","CURRENT"),("Invoice Link State","EXACT_X_AMEA_CMS")]),
        ("X 복수 Z 검토",[("Record State","CURRENT"),("Invoice Link State","MULTI_Z_REVIEW")]),
    ],
}

def main():
    if os.environ.get("FEISHU_BASE_APP_TOKEN")!=EXPECTED_BASE:
        raise SafeError("REFUSE_OTHER_FEISHU_BASE")
    mode=os.environ.get("FEISHU_X_BRIDGE_MODE","plan")
    if mode not in ("plan","apply"):raise SafeError("X_BRIDGE_BAD_MODE")
    sources=source_rows()
    data,audit=build(sources)
    print("X_BRIDGE_SOURCE_AUDIT "+ " ".join(
        key+"="+str(value) for key,value in sorted(audit.items())))
    if mode=="plan":
        print("X_BRIDGE_PLAN_PASS source_tables=7 records="+
              str(sum(map(len,data.values())))+" writes=0")
        return
    token,root=auth()
    paths=ensure_tables(token,root)
    for name,rows in data.items():
        apply_rows(token,paths[name],rows,name)
    for name,definitions in VIEWS.items():
        for title,conditions in definitions:
            view_id=view_filter(token,paths[name],title,conditions)
            print("X_BRIDGE_VIEW_READY name="+title+
                  " URL=https://ocnz4cb25scn.feishu.cn/base/"+EXPECTED_BASE+
                  "?table="+paths[name].rsplit("/",1)[-1]+"&view="+view_id)
    print("X_BRIDGE_APPLY_PASS tables=3 sample_or_invoice_inferred=0"
          " original_project_board_writes=0")

if __name__=="__main__":
    try:main()
    except Exception as exc:
        reason=str(exc) if isinstance(exc,(SafeError,ValueError)) else type(exc).__name__
        print("X_BRIDGE_FAILED="+reason,file=sys.stderr)
        sys.exit(1)
