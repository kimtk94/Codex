#!/usr/bin/env python3
"""Read-only metadata inspection of Feishu Sales Home shortcut view.

Print field IDs and filter shape, suppress non-key record content.
"""
import json
from sales_home_links import HOME_TABLE, HOME_VIEW, API, pages, extract_token, request, require, require_success

def main():
    token=extract_token(request("POST","/open-apis/auth/v3/tenant_access_token/internal",
         body={"app_id":require("FEISHU_APP_ID"),"app_secret":require("FEISHU_APP_SECRET")}))
    root=API+"/tables/"+HOME_TABLE
    fields=list(pages(root+"/fields",token))
    mapped={f.get("field_name"):(f.get("field_id"),f.get("type")) for f in fields}
    view=require_success(request("GET",root+"/views/"+HOME_VIEW,token=token),"GET_VIEW").get("view") or {}
    f=(view.get("property") or {}).get("filter_info")
    # Only menu and generic filters; suppress any user-entered free-text conditions.
    safe=[]
    for condition in (f or {}).get("conditions") or []:
        field_id=condition.get("field_id")
        name=next((k for k,v in mapped.items() if v[0]==field_id),None)
        raw=condition.get("value")
        safe.append({"field":name,"field_id":field_id,
                     "operator":condition.get("operator"),
                     "value":raw if name in ("Menu Key","메뉴 구분","데이터 상태") else "(redacted)",
                     "condition_id":condition.get("condition_id")})
    print("HOME_VIEW_FILTER",json.dumps({
       "name":view.get("view_name"),"id":view.get("view_id"),
       "conjunction":(f or {}).get("conjunction"),
       "conditions":safe,"field_map":{k:v for k,v in mapped.items()
           if k in ("Menu Key","메뉴 구분","화면","바로가기","데이터 상태")}},ensure_ascii=False))
    for name, view_id in [("shortcut",HOME_VIEW)]:
        rows=list(pages(root+"/records",token,{"view_id":view_id}))
        tally={}
        for r in rows:
            key=str((r.get("fields") or {}).get("Menu Key"))
            tally[key]=tally.get(key,0)+1
        print("VIEW_MENU_KEYS",name,json.dumps(tally,ensure_ascii=False))
    allrows=list(pages(root+"/records",token))
    keys=[str((r.get("fields") or {}).get("Menu Key")) for r in allrows]
    print("HOME_TABLE_ROW_COUNT",len(keys),"TARGET_KEYS_PRESENT",{"PROJECT_ACTIVE_QUOTE":keys.count("PROJECT_ACTIVE_QUOTE"),"PROJECT_BILLING_QUOTE":keys.count("PROJECT_BILLING_QUOTE")})
    print("HOME_VIEW_AUDIT_READ_ONLY_PASS")

if __name__=="__main__":main()
