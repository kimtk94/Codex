#!/usr/bin/env python3
"""Strict Feishu Sales Home '바로가기' seven-link audit.

Verify every persisted URL, clickable hyperlink, target table/view or native
dashboard and widget type. No invoice, Quote, Payment or customer source writes.
Called AFTER the native Sales Home upsert to detect any missing persisted link.
"""
import os
import sys
import urllib.parse

from qq_mail_ingest import SafeError, auth, list_all, plain_field
from sales_native_home import (
    EXPECTED_BASE, BASE_URL, HOME, SHORTCUT_KEYS, MENUS,
    CHART_SHORTCUT_ENV, GRAPH_LINK_LABELS, PROJECT_OPS_DASHBOARD_ID,
    EXTERNAL_SHORTCUT_KEYS, table_map, list_views, target_path, valid_menu_url,
    hyperlink,
)
from shortcut_chart_dashboards import (
    CHARTS, expected_components, verify_components,
)
from native_dashboard_cli import cli, find_named
from project_quote_operating_sync import TABLES as PROJECT_OPS_TABLES


def exact_url(url, expected_table, expected_view=None):
    if not isinstance(url,str):
        return False
    parsed=urllib.parse.urlsplit(url)
    ref=urllib.parse.urlsplit(BASE_URL)
    if (parsed.scheme,parsed.netloc,parsed.path)!=(ref.scheme,ref.netloc,ref.path):
        return False
    if parsed.fragment:
        return False
    query=urllib.parse.parse_qs(parsed.query,keep_blank_values=True)
    expected={"table":[expected_table]}
    if expected_view:
        expected["view"]=[expected_view]
    return query==expected


def target_routes(token,root,tables):
    """Read the exact targets; never guess/construct missing Feishu identifiers."""
    result={}
    definition={r[0]:r for r in MENUS}
    charts={r[0]:r for r in CHARTS}
    dashboard_list=cli("+dashboard-list","--base-token",EXPECTED_BASE)
    for key in SHORTCUT_KEYS:
        if key in charts:
            _,_,title,chart,note,kind,source=charts[key]
            dashboard_id=find_named(dashboard_list,title)
            if not dashboard_id or not dashboard_id.startswith("blk"):
                raise SafeError("SHORTCUT_DASHBOARD_NOT_FOUND_"+key)
            components=expected_components(chart,note,kind,source)
            verify_components(dashboard_id,components,False)
            result[key]=(BASE_URL+"?table="+dashboard_id,"DASHBOARD_VERIFIED")
        elif key=="X_MY_PROJECTS":
            match=find_named(dashboard_list,"Novogene 프로젝트 운영 대시보드")
            if match!=PROJECT_OPS_DASHBOARD_ID:
                raise SafeError("SHORTCUT_PROJECT_DASHBOARD_ID_MISMATCH")
            result[key]=(BASE_URL+"?table="+match,"DASHBOARD_VERIFIED")
        elif key in EXTERNAL_SHORTCUT_KEYS:
            kind="active" if key=="PROJECT_ACTIVE_QUOTE" else "billing"
            table_name=PROJECT_OPS_TABLES[kind][0]
            tid=tables.get(table_name)
            if not tid or not tid.startswith("tbl"):
                raise SafeError("SHORTCUT_PROJECT_TABLE_MISSING_"+key)
            rows=list_all(target_path(root,tid)+"/records",token,"shortcut_project_records")
            if not rows:raise SafeError("SHORTCUT_PROJECT_TABLE_EMPTY_"+key)
            result[key]=(BASE_URL+"?table="+tid,"PROJECT_TABLE_VERIFIED")
        else:
            entry=definition.get(key)
            if not entry:
                raise SafeError("SHORTCUT_MENU_DEFINITION_MISSING_"+key)
            table_name,view_name=entry[3],entry[4]
            tid=tables.get(table_name)
            if not tid or not tid.startswith("tbl"):
                raise SafeError("SHORTCUT_TARGET_TABLE_MISSING_"+key)
            views=list_views(token,target_path(root,tid))
            vid=views.get(view_name)
            if not vid or not vid.startswith("vew"):
                raise SafeError("SHORTCUT_TARGET_VIEW_MISSING_"+key)
            result[key]=(BASE_URL+"?table="+tid+"&view="+vid,"VIEW_VERIFIED")
    if set(result)!=set(SHORTCUT_KEYS):
        raise SafeError("SHORTCUT_TARGET_CARDINALITY")
    return result


def verify_persisted_shortcuts(records,targets):
    indexed={}
    for rec in records:
        fields=rec.get("fields") or {}
        key=plain_field(fields.get("Menu Key")).strip()
        if key not in SHORTCUT_KEYS:
            continue
        if key in indexed:
            raise SafeError("SHORTCUT_DUPLICATE_RECORD_"+key)
        indexed[key]=fields
    if set(indexed)!=set(SHORTCUT_KEYS):
        raise SafeError("SHORTCUT_RECORDS_MISSING_"+",".join(sorted(set(SHORTCUT_KEYS)-set(indexed))))
    outcomes={}
    for key in SHORTCUT_KEYS:
        fields=indexed[key]
        expected,kind=targets[key]
        raw=plain_field(fields.get("바로가기 URL")).strip()
        click=hyperlink(fields.get("바로가기"))
        parsed=urllib.parse.parse_qs(urllib.parse.urlsplit(expected).query)
        if key in EXTERNAL_SHORTCUT_KEYS:
            raw=raw or (click[1] if click else "")
        label=GRAPH_LINK_LABELS.get(key,"열기")
        if not (raw==expected and click==(label,expected) and
                valid_menu_url(key,raw) and
                exact_url(raw,parsed["table"][0],
                          (parsed.get("view") or [None])[0])):
            raise SafeError("SHORTCUT_LINK_READBACK_MISMATCH_"+key)
        outcomes[key]=(expected,kind)
    return outcomes


def main():
    if os.environ.get("FEISHU_BASE_APP_TOKEN")!=EXPECTED_BASE:
        raise SafeError("SHORTCUT_WRONG_FEISHU_BASE")
    token,root=auth()
    tables=table_map(token,root)
    tid=tables.get(HOME)
    if not tid:
        raise SafeError("SHORTCUT_HOME_TABLE_MISSING")
    targets=target_routes(token,root,tables)
    records=list_all(target_path(root,tid)+"/records",token,"shortcut_real_readback")
    verified=verify_persisted_shortcuts(records,targets)
    for key,(url,kind) in verified.items():
        print("SHORTCUT_LINK_VERIFIED "+key+" "+kind+" "+url,flush=True)
    print("SHORTCUT_LINK_AUDIT_PASS checked="+str(len(verified))+
          " missing=0 mismatched=0 source_record_writes=0",flush=True)


if __name__=="__main__":
    try:
        main()
    except Exception as exc:
        reason=str(exc) if isinstance(exc,SafeError) else type(exc).__name__
        print("SHORTCUT_LINK_AUDIT_FAILED="+reason,file=sys.stderr)
        sys.exit(1)
