#!/usr/bin/env python3
"""Add two verified Quote-first project list links to Feishu Sales Home.

Never replace the existing Project Dashboard shortcut. Only modify the two
new whitelisted Menu Key rows. Existing project data is untouched.
"""
import os
import urllib.parse
from sales_home_links import API, HOME_TABLE, HOME_VIEW, pages, request, require, require_success, extract_token, link_url, url
from project_quote_operating_sync import TABLES, all_tables

KEYS={
    "PROJECT_ACTIVE_QUOTE":("active","08 · 진행 중 프로젝트 (Quote)"),
    "PROJECT_BILLING_QUOTE":("billing","09 · 완료·결제 관리 (Quote)")
}
FIELDS={"Menu Key","메뉴 구분","화면","바로가기","데이터 상태"}

def desired_rows(ids):
    result={}
    for key,(kind,label) in KEYS.items():
        name=TABLES[kind][0]
        table_id=ids.get(name)
        if not table_id:raise RuntimeError("DERIVED_TABLE_NOT_FOUND")
        result[key]={
           "Menu Key":key, "메뉴 구분":"프로젝트", "화면":label,
           "바로가기":{"text":"열기","link":url(table_id)},
           "데이터 상태":"DATA_PRESENT",
        }
    return result

def matches(existing,desired):
    for field,val in desired.items():
        current=existing.get(field)
        if field=="바로가기":
            if link_url(current)!=val["link"]:return False
        elif current!=val:return False
    return True

def main():
    if os.getenv("FEISHU_PROJECT_OPS_APPLY")!="1":
        raise RuntimeError("HOME_WRITE_NOT_AUTHORIZED")
    token=extract_token(request("POST","/open-apis/auth/v3/tenant_access_token/internal",
        body={"app_id":require("FEISHU_APP_ID"),"app_secret":require("FEISHU_APP_SECRET")}))
    tables=all_tables(token)
    desired=desired_rows(tables)
    for _,(kind,_) in KEYS.items():
        tid=tables[TABLES[kind][0]]
        content=list(pages(API+"/tables/"+tid+"/records",token))
        if not content:raise RuntimeError("DESTINATION_TABLE_EMPTY")
    home=API+"/tables/"+HOME_TABLE
    fields={x.get("field_name") for x in pages(home+"/fields",token)}
    if not FIELDS.issubset(fields):raise RuntimeError("SALES_HOME_SCHEMA_MISSING")
    existing={}
    for row in pages(home+"/records",token):
        key=(row.get("fields") or {}).get("Menu Key")
        if key not in KEYS:continue
        if key in existing:raise RuntimeError("DUPLICATE_HOME_MENU_KEY")
        existing[key]=row
    # Preflight the destinations and all existing keys before mutating Home.
    created=0;updated=0
    for key,want in desired.items():
        old=existing.get(key)
        if not old:
            require_success(request("POST",home+"/records",token=token,
                body={"fields":want}),"CREATE_HOME_MENU")
            created+=1
        elif not matches(old.get("fields") or {},want):
            require_success(request("PUT",home+"/records/"+urllib.parse.quote(old["record_id"],safe=""),
                token=token,body={"fields":want}),"UPDATE_HOME_MENU")
            updated+=1
    readback={}
    for row in pages(home+"/records",token):
        key=(row.get("fields") or {}).get("Menu Key")
        if key in KEYS:
            if key in readback:raise RuntimeError("DUPLICATE_HOME_READBACK")
            readback[key]=row.get("fields") or {}
    if set(readback)!=set(desired) or not all(matches(readback[k],v) for k,v in desired.items()):
        raise RuntimeError("HOME_LINK_READBACK_FAILED")
    visible={(r.get("fields") or {}).get("Menu Key") for r in
             pages(home+"/records",token,{"view_id":HOME_VIEW})}
    count=sum(k in visible for k in KEYS)
    print("PROJECT_HOME_QUICKLINK_SYNC_PASS created="+str(created)+
         " updated="+str(updated)+" visible_in_shortcuts_view="+str(count)+
         " verified_destinations=2",flush=True)

if __name__=="__main__": main()
