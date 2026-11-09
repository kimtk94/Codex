#!/usr/bin/env python3
"""Feishu native Quote Review grid presentation: purpose-built views.

Full list: no filter, group by Friday-week descending, newest approval first.
Included: active/manual-included only, grouped by week.
Not included: inactive/unknown/manual-excluded, grouped by reason then week.
"""
import json
import os
import sys

from qq_mail_ingest import SafeError, auth, get_fields, list_all
from setup_sales_web import list_views, get_view
from sort_sales_home import run_cli, get_group_items, visible_items
from sales_metrics_sync import (
    EXPECTED_BASE, QUOTE_REVIEW_TABLE, table_catalog, table_path, VIEW_SPECS,
)

COLUMNS=(
    "Quote Name","합산 제외","합산 상태","제외 이유",
    "Quote Status","SFDC IsActive","Week Start","Approval KST",
    "SFDC Record ID",
)
SORT={"sort_config":[{"field":"Approval KST","desc":True}]}


def group_policy(name):
    first=([{"field":"제외 이유","desc":False}]
           if name=="합산 제외 · 미확인" else [])
    return {"group_config":[*first,{"field":"Week Start","desc":True}]}


def match_group(document,expected,by_id):
    rows=get_group_items(document)
    return isinstance(rows,list) and [
        (by_id.get(x.get("field"),x.get("field")),x.get("desc"))
        for x in rows if isinstance(x,dict)
    ]==[(x["field"],x["desc"]) for x in expected["group_config"]]


def match_sort(document,by_id):
    from sort_sales_home import get_sort_items
    rows=get_sort_items(document)
    return isinstance(rows,list) and len(rows)==1 and isinstance(rows[0],dict) and (
        by_id.get(rows[0].get("field"),rows[0].get("field")),
        rows[0].get("desc"))==("Approval KST",True)


def match_columns(document,by_id):
    fields=visible_items(document)
    if not isinstance(fields,list):
        return False
    values=[]
    for item in fields:
        if isinstance(item,str):
            values.append(by_id.get(item,item))
        elif isinstance(item,dict):
            k=item.get("field_id",item.get("field",item.get("name")))
            values.append(by_id.get(k,k))
        else:
            return False
    return values==list(COLUMNS)


def ensure(action,check,config,table_id,view_id,mode,by_id):
    get_cmd="+view-get-"+action
    set_cmd="+view-set-"+action
    before=run_cli(get_cmd,EXPECTED_BASE,table_id,view_id)
    good=check(before,config,by_id) if action=="group" else check(before,by_id)
    if mode=="apply" and not good:
        run_cli(set_cmd,EXPECTED_BASE,table_id,view_id,config)
        after=run_cli(get_cmd,EXPECTED_BASE,table_id,view_id)
        actual=check(after,config,by_id) if action=="group" else check(after,by_id)
        if not actual:
            raise SafeError("QUOTE_REVIEW_LAYOUT_"+action.upper()+"_READBACK_FAILED")
    return not good


def main():
    if os.environ.get("FEISHU_BASE_APP_TOKEN")!=EXPECTED_BASE:
        raise SafeError("QUOTE_REVIEW_LAYOUT_WRONG_BASE")
    mode=os.environ.get("FEISHU_METRIC_MODE","plan")
    if mode not in ("plan","apply"):
        raise SafeError("QUOTE_REVIEW_LAYOUT_BAD_MODE")
    token,root=auth()
    catalog=table_catalog(token,root)
    ids=catalog.get(QUOTE_REVIEW_TABLE,[])
    if len(ids)!=1:
        raise SafeError("QUOTE_REVIEW_LAYOUT_TABLE_MISSING")
    tid=ids[0]
    path=table_path(root,tid)
    views=list_views(token,path)
    fields=get_fields(token,path)
    names={f.get("field_name"):f.get("type") for f in fields}
    if names.get("Quote Name")!=1 or names.get("합산 제외")!=7:
        raise SafeError("QUOTE_REVIEW_LAYOUT_SCHEMA_NOT_READY")
    if set(COLUMNS)-set(names):
        raise SafeError("QUOTE_REVIEW_LAYOUT_FIELDS_MISSING")
    by_id={f.get("field_id"):f.get("field_name") for f in fields}
    for name,_,_ in VIEW_SPECS[QUOTE_REVIEW_TABLE]:
        vid=views.get(name)
        if not vid:
            raise SafeError("QUOTE_REVIEW_LAYOUT_VIEW_MISSING")
        if get_view(token,path,vid).get("view_type")!="grid":
            raise SafeError("QUOTE_REVIEW_LAYOUT_NOT_GRID")
        group=group_policy(name)
        group_changed=ensure("group",match_group,group,tid,vid,mode,by_id)
        sort_changed=ensure("sort",match_sort,SORT,tid,vid,mode,by_id)
        visible_changed=ensure("visible-fields",match_columns,
                               {"visible_fields":list(COLUMNS)},tid,vid,mode,by_id)
        print("QUOTE_REVIEW_LAYOUT_"+("PASS" if mode=="apply" else "PLAN")+
              " view="+name+" group="+str(len(group["group_config"]))+
              " sort=approval_newest columns="+str(len(COLUMNS))+
              " changed="+str(sum([group_changed,sort_changed,visible_changed])))
        print("QUOTE_REVIEW_URL_"+name+"=https://ocnz4cb25scn.feishu.cn/base/"
              +EXPECTED_BASE+"?table="+tid+"&view="+vid)


if __name__=="__main__":
    try: main()
    except (SafeError,RuntimeError) as e:
        print("QUOTE_REVIEW_LAYOUT_FAILED="+str(e),file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print("QUOTE_REVIEW_LAYOUT_FAILED="+type(e).__name__,file=sys.stderr)
        sys.exit(1)
