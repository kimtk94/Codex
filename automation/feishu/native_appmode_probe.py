#!/usr/bin/env python3
"""Check native Feishu Base App Mode prerequisites without mutating any resource.

User outcome is a Feishu-hosted App Mode, not Vercel or a grid-only Base.
Probe existing Base metadata and dashboard templates before attempting creation.
"""
import os
import sys
from qq_mail_ingest import auth,api,SafeError

BASE="IpMkbUD0vaFqtYs93a3csXtdn1b"
TABLE="tblTZe5tkRUeOHM8"

def main():
    if os.environ.get("FEISHU_BASE_APP_TOKEN")!=BASE:
        raise SafeError("REFUSE_NON_SALES_BASE")
    token,root=auth()
    meta=api("GET",root,token,action="native_appmode_base_info")
    app=meta.get("app") or meta
    print("FEISHU_APP_MODE_BASE_ACCESS=PASS")
    print("FEISHU_APP_MODE_BASE_FIELDS="+",".join(sorted(app.keys())))
    for key in ("workspace_token","workspace_id"):
        val=app.get(key)
        if isinstance(val,str) and val:
            print("FEISHU_APP_MODE_"+key.upper()+"="+val)
    data=api("GET",root+"/dashboards?page_size=100",token,action="native_appmode_dashboards")
    dashboards=data.get("dashboards") or data.get("items") or []
    print("FEISHU_APP_MODE_DASHBOARD_COUNT="+str(len(dashboards)))
    # Titles and public resource IDs are not customer records, but never log
    # arbitrary dashboard content or private record values.
    for dashboard in dashboards:
        did=dashboard.get("block_id") or dashboard.get("id")
        if did and str(did).startswith("blk"):
            print("FEISHU_APP_MODE_DASHBOARD_TEMPLATE_ID="+str(did))
    fields=api("GET",root+"/tables/"+TABLE+"/fields?page_size=100",token,action="native_appmode_fields")
    colset={r.get("field_name") for r in fields.get("items") or []}
    required={"Quote Full Name","Progress %","SIF State","Prepayment","AMEA","Current Stage"}
    if not required.issubset(colset):
        raise SafeError("APP_MODE_PROJECT_SOURCE_SCHEMA_MISSING")
    print("FEISHU_APP_MODE_PROJECT_SOURCE=READY fields="+str(len(colset)))
    print("FEISHU_APP_MODE_PRECHECK_PASS writes=0")

if __name__=="__main__":
    try:main()
    except Exception as e:
        msg=str(e) if isinstance(e,SafeError) else type(e).__name__
        print("FEISHU_APP_MODE_PRECHECK_FAILED="+msg,file=sys.stderr)
        sys.exit(1)
