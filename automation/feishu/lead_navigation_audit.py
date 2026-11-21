#!/usr/bin/env python3
"""Read-only audit of Lead view navigation and display metadata.

Never PATCHes or deletes views/records. Prints no customer data.
Reports API-supported properties and identifies views managed by automation.
"""
import json
import sys
import lead_mail_description_sync as lead
import lead_mail_views_sync as mail
import lead_action_queue_views as queue
import lead_manual_checkboxes as manual
import lead_workbench_view as workbench
import lead_workbench_columns as columns
from sales_home_links import API, pages, request, require_success

def audit_views(views, target_id):
    names = [v.get("view_name") for v in views]
    if len(views) < 8 or len(set(names)) != len(names):
        raise RuntimeError("LEAD_NAV_VIEW_COUNT_OR_DUPLICATE")
    managed = {name for name, _, _ in mail.VIEWS}
    managed.update(name for name, _ in queue.QUEUES)
    managed.add(workbench.VIEW_NAME)
    existing = {v.get("view_name") for v in views}
    if not managed.issubset(existing):
        raise RuntimeError("LEAD_NAV_MANAGED_VIEW_MISSING")
    return [
        {"id": v.get("view_id"), "name": v.get("view_name"),
         "managed_by_automation": v.get("view_name") in managed,
         "overview": v.get("view_id") == target_id}
        for v in views
    ]

def main():
    token=lead.auth()
    tables=[t for t in pages(API+"/tables",token) if t.get("name")==lead.TABLE]
    if len(tables)!=1 or tables[0].get("table_id")!=manual.EXPECTED_TABLE_ID:
        raise RuntimeError("LEAD_NAV_WRONG_TABLE")
    root=API+"/tables/"+manual.EXPECTED_TABLE_ID
    fields=list(pages(root+"/fields",token))
    hidden=columns.make_plan(fields)
    views=list(pages(root+"/views",token))
    matched=[v for v in views if v.get("view_name")==workbench.VIEW_NAME]
    if len(matched)!=1:
        raise RuntimeError("LEAD_NAV_OVERVIEW_NOT_UNIQUE")
    view_id=matched[0].get("view_id")
    target=mail.get_one_view(root,token,view_id)
    columns.verify_hidden(target,hidden)
    wanted=workbench.filter_definition(workbench.validate_schema(fields))
    if not mail.filter_matches((target.get("property") or {}).get("filter_info"),wanted):
        raise RuntimeError("LEAD_NAV_AGE_FILTER_CHANGED")
    summary={
        "table_id":manual.EXPECTED_TABLE_ID,
        "overview_id":view_id,
        "overview_columns_visible":len(columns.VISIBLE),
        "overview_columns_hidden":len(hidden),
        "other_views":len(views)-1,
        "views":audit_views(views,view_id),
        "api_column_visibility_supported":True,
        "api_column_order_update_supported":False,
        "api_sidebar_hide_supported":False,
        "writes":0,
    }
    print("LEAD_NAVIGATION_AUDIT_PASS="+json.dumps(summary,ensure_ascii=False),flush=True)

if __name__=="__main__":
    try: main()
    except Exception as exc:
        print("LEAD_NAVIGATION_AUDIT_FAILED="+str(exc),file=sys.stderr)
        sys.exit(1)
