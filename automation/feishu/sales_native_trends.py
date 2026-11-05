#!/usr/bin/env python3
"""Native Feishu monthly revenue / weekly quote trend source tables and views."""
import os
import sys
import time
import urllib.parse
from datetime import datetime
from qq_mail_ingest import SafeError,api,auth,get_fields,list_all
from setup_sales_web import BASE_URL,EXPECTED_BASE,resolve_view,get_view,filter_matches,field_map,list_views
from native_trend_rows import FIELDS,MONTH,WEEK,KST,make,number,val
TABLE="02 매출 견적 추이"
VIEWS=(("월별 Revenue 추이","MONTHLY_REVENUE"),("Weekly Quote 추이","WEEKLY_QUOTE"))

def tables(token,root):
    entries=list_all(root+"/tables",token,"trend_tables")
    if len({r.get("name") for r in entries})!=len(entries):
        raise SafeError("TREND_DUPLICATE_TABLE")
    return {r["name"]:r["table_id"] for r in entries if r.get("name") and r.get("table_id")}

def fetch(token,root,ids):
    data={};links={}
    for name,view in ((MONTH,"월별 Tax Invoice"),(WEEK,"매주 Quote 건수 · 금액")):
        tid=ids.get(name)
        if not tid:raise SafeError("TREND_SOURCE_TABLE_MISSING")
        path=root+"/tables/"+urllib.parse.quote(tid,safe="")
        data[name]=[r.get("fields") or {} for r in list_all(path+"/records",token,"trend_source_read")]
        vid=list_views(token,path).get(view)
        links[name]=BASE_URL+"?table="+tid+("&view="+vid if vid else "")
    return data,links

def ensure_table(token,root,ids):
    tid=ids.get(TABLE)
    if not tid:
        api("POST",root+"/tables",token,data={"table":{"name":TABLE,"default_view_name":"전체 추이 데이터",
            "fields":[{"field_name":k,"type":t} for k,t in FIELDS.items()]}},action="trend_create_table")
        tid=tables(token,root).get(TABLE)
    if not tid:raise SafeError("TREND_CREATE_NOT_VERIFIED")
    path=root+"/tables/"+urllib.parse.quote(tid,safe="")
    current={f.get("field_name"):f.get("type") for f in get_fields(token,path)}
    if any(k in current and current[k]!=t for k,t in FIELDS.items()):
        raise SafeError("TREND_FIELD_TYPE_CONFLICT")
    for k,t in FIELDS.items():
        if k not in current:
            api("POST",path+"/fields",token,data={"field_name":k,"type":t},
                action="trend_add_field")
    verify={f.get("field_name"):f.get("type") for f in get_fields(token,path)}
    if any(verify.get(k)!=t for k,t in FIELDS.items()):
        raise SafeError("TREND_FIELD_READBACK_ERROR")
    return tid,path

def ensure_views(token,tid,path):
    fields=field_map(token,path)
    field=fields.get("유형")
    if not field:raise SafeError("TREND_VIEW_FIELD_MISSING")
    for title,typ in VIEWS:
        vid,_=resolve_view(token,path,title,True)
        view=get_view(token,path,vid)
        if not(view.get("view_name")==title and filter_matches(view,field,typ)):
            import json
            api("PATCH",path+"/views/"+urllib.parse.quote(vid,safe=""),
                token,data={"view_name":title,"property":{"filter_info":{
                "conjunction":"and","conditions":[{"field_id":field,"operator":"is",
                "value":json.dumps([typ])}]} }},action="trend_create_filtered_view")
            for i in range(5):
                view=get_view(token,path,vid)
                if view.get("view_name")==title and filter_matches(view,field,typ):break
                time.sleep(1)
            else:raise SafeError("TREND_FILTER_READBACK_FAILED")
        print("TREND_VIEW_URL="+title+" "+BASE_URL+"?table="+tid+"&view="+vid)

def same(existing,desired):
    for name,value in desired.items():
        if name=="갱신 시각":continue
        if FIELDS[name]==2:
            if number(existing.get(name)) != number(value):return False
        elif val(existing.get(name))!=str(value):return False
    return True

def sync(token,path,desired):
    old=list_all(path+"/records",token,"trend_existing")
    idx={}
    for record in old:
        k=val((record.get("fields") or {}).get("원본 키"))
        if not k:continue
        if k in idx:raise SafeError("TREND_DUPLICATE_ROW_KEY")
        idx[k]=record
    created=[];updated=[];unchanged=0
    for row in desired:
        prev=idx.get(row["원본 키"])
        if prev and same(prev.get("fields") or {},row):
            unchanged+=1
        elif prev:updated.append({"record_id":prev["record_id"],"fields":row})
        else:created.append({"fields":row})
    for op,rows in (("batch_create",created),("batch_update",updated)):
        for i in range(0,len(rows),25):
            b=rows[i:i+25]
            response=api("POST",path+"/records/"+op,token,data={"records":b},
                         action="trend_"+op)
            if len(response.get("records") or [])!=len(b):
                raise SafeError("TREND_SAVE_UNCONFIRMED")
    after=list_all(path+"/records",token,"trend_readback")
    keys={val((x.get("fields") or {}).get("원본 키")):x.get("fields") or {} for x in after}
    for row in desired:
        if row["원본 키"] not in keys or not same(keys[row["원본 키"]],row):
            raise SafeError("TREND_READBACK_FAIL")
    print("TREND_APPLY_PASS created="+str(len(created))+" updated="+str(len(updated))+
          " unchanged="+str(unchanged)+" source_writes=0")

def main():
    if os.environ.get("FEISHU_BASE_APP_TOKEN")!=EXPECTED_BASE:
        raise SafeError("TREND_UNEXPECTED_BASE")
    mode=os.environ.get("FEISHU_TREND_MODE","plan")
    if mode not in ("plan","apply"):raise SafeError("TREND_BAD_MODE")
    token,root=auth();ids=tables(token,root)
    source,links=fetch(token,root,ids)
    records=make(source,links,datetime.now(KST))
    if mode=="plan":
        print("TREND_PLAN_PASS writes=0")
        return
    tid,path=ensure_table(token,root,ids)
    ensure_views(token,tid,path)
    sync(token,path,records)
    view=list_views(token,path).get("전체 추이 데이터")
    print("TREND_HOME_URL="+BASE_URL+"?table="+tid+("&view="+view if view else ""))

if __name__=="__main__":
    try:main()
    except Exception as exc:
        reason=str(exc) if isinstance(exc,SafeError) else type(exc).__name__
        print("TREND_FAILED:"+reason,file=sys.stderr);sys.exit(1)
