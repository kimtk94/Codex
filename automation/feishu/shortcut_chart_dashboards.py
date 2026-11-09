#!/usr/bin/env python3
"""Idempotent, source-backed chart dashboards for Sales Home shortcut navigation.

Only two Feishu-native dashboard containers and their own widgets may be written.
No source Feishu records, existing dashboard widgets, or sharing controls are changed.
The user-facing shortcut link is a Base dashboard block (?table=blk...), not a grid.
"""
import json
import os
import sys

from native_dashboard_cli import BASE, BLOCKS, cli, collect, find_named, ident

CHARTS = (
    ("MONTHLY_TREND","FEISHU_SHORTCUT_MONTHLY_DASHBOARD_ID",
     "Novogene · 월별 Revenue 그래프",
     "월별 Revenue · VAT 제외 · M KRW (K USD)",
     "월별 Revenue 표시 기준","line","Monthly Tax Invoice"),
    ("WEEKLY_TREND","FEISHU_SHORTCUT_WEEKLY_DASHBOARD_ID",
     "Novogene · Weekly Quote 그래프",
     "KOREA · Weekly Quote · 완료 4주 + 이번 주 (Count + 계산 K USD)",
     "Quote 계산 기준","combo","Weekly Quote KPI"),
)


def expected_components(chart_name,note_name,kind,source):
    available={name:(typ,config) for name,typ,config in BLOCKS}
    if chart_name not in available or note_name not in available:
        raise RuntimeError("CHART_SHORTCUT_REFERENCE_WIDGET_MISSING")
    chart_type,chart_config=available[chart_name]
    note_type,note_config=available[note_name]
    if (chart_type!=kind or note_type!="text"
            or chart_config.get("table_name")!=source
            or not chart_config.get("group_by")
            or not chart_config.get("series")):
        raise RuntimeError("CHART_SHORTCUT_REFERENCE_SOURCE_MISMATCH")
    return ((chart_name,kind,chart_config),(note_name,"text",note_config))


def blocks_by_name(rows):
    found={}
    for row in collect(rows):
        name=row.get("name")
        bid=row.get("block_id") or row.get("id")
        if not isinstance(name,str) or not isinstance(bid,str):
            continue
        if not bid.startswith(("cht","blk")):
            continue
        if name in found and found[name].get("block_id")!=row.get("block_id"):
            raise RuntimeError("CHART_SHORTCUT_DUPLICATE_COMPONENT")
        found[name]=row
    return found


def verify_components(dashboard_id,expected,allow_create):
    before=cli("+dashboard-block-list","--base-token",BASE,
               "--dashboard-id",dashboard_id)
    indexed=blocks_by_name(before)
    created=0
    for name,kind,config in expected:
        existing=indexed.get(name)
        if existing:
            if existing.get("type")!=kind:
                raise RuntimeError("CHART_SHORTCUT_WIDGET_TYPE_MISMATCH")
            if allow_create and kind in ("combo","text"):
                cli("+dashboard-block-update","--base-token",BASE,
                    "--dashboard-id",dashboard_id,
                    "--block-id",existing.get("block_id") or existing.get("id"),
                    "--data-config",json.dumps(config,ensure_ascii=False,
                                               separators=(",",":")))
            continue
        if not allow_create:
            raise RuntimeError("CHART_SHORTCUT_REQUIRED_WIDGET_MISSING")
        cli("+dashboard-block-create","--base-token",BASE,
            "--dashboard-id",dashboard_id,"--name",name,
            "--type",kind,"--data-config",
            json.dumps(config,ensure_ascii=False,separators=(",",":")))
        created+=1
    after=cli("+dashboard-block-list","--base-token",BASE,
              "--dashboard-id",dashboard_id)
    final=blocks_by_name(after)
    for name,kind,_ in expected:
        if name not in final or final[name].get("type")!=kind:
            raise RuntimeError("CHART_SHORTCUT_WIDGET_READBACK_MISMATCH")
    return created


def ensure_graph_dashboard(title,expected,mode,dashboards):
    dashboard_id=find_named(dashboards,title)
    if not dashboard_id and mode=="apply":
        result=cli("+dashboard-create","--base-token",BASE,"--name",title)
        dashboard_id=find_named(result,title) or ident(result)
        if not dashboard_id:
            dashboard_id=find_named(cli("+dashboard-list","--base-token",BASE),title)
    if not dashboard_id:
        if mode=="plan":
            print("CHART_SHORTCUT_PLAN_MISSING="+title+" writes=0")
            return None
        raise RuntimeError("CHART_SHORTCUT_DASHBOARD_CREATE_UNVERIFIED")
    if not dashboard_id.startswith("blk"):
        raise RuntimeError("CHART_SHORTCUT_INVALID_DASHBOARD_ID")
    created=verify_components(dashboard_id,expected,mode=="apply")
    print("CHART_SHORTCUT_DASHBOARD_PASS name="+title+" widgets="+str(len(expected))
          +" created="+str(created)+" source_data_writes=0")
    return dashboard_id


def main():
    if os.environ.get("FEISHU_BASE_APP_TOKEN")!=BASE:
        raise RuntimeError("CHART_SHORTCUT_REFUSE_OTHER_BASE")
    mode=os.environ.get("FEISHU_PORTAL_MODE","plan")
    if mode not in ("plan","apply"):
        raise RuntimeError("CHART_SHORTCUT_UNSUPPORTED_MODE")
    dashboards=cli("+dashboard-list","--base-token",BASE)
    ids={}
    for key,env_key,title,chart_name,note_name,kind,source in CHARTS:
        expected=expected_components(chart_name,note_name,kind,source)
        dash_id=ensure_graph_dashboard(title,expected,mode,dashboards)
        if dash_id:
            ids[env_key]=dash_id
            print("CHART_SHORTCUT_URL_"+key+"=https://ocnz4cb25scn.feishu.cn/base/"
                  +BASE+"?table="+dash_id)
    if mode=="apply":
        if len(ids)!=len(CHARTS):
            raise RuntimeError("CHART_SHORTCUT_DASHBOARD_PAIR_INCOMPLETE")
        env_path=os.environ.get("GITHUB_ENV")
        if not env_path:
            raise RuntimeError("CHART_SHORTCUT_GITHUB_ENV_MISSING")
        with open(env_path,"a",encoding="utf-8") as stream:
            for name,dash_id in ids.items():
                stream.write(name+"="+dash_id+"\n")
        print("CHART_SHORTCUT_LINK_EXPORT_PASS count=2")


if __name__=="__main__":
    try:
        main()
    except Exception as exc:
        print("CHART_SHORTCUT_FAILED="+
              (str(exc) if isinstance(exc,RuntimeError) else type(exc).__name__),
              file=sys.stderr)
        sys.exit(1)
