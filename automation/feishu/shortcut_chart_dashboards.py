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
from qq_mail_ingest import auth, list_all, SafeError
from setup_sales_web import list_views
from sales_native_home import HOME, table_map, target_path
from quote_dashboard_preview import BLOCK_NAME,read_preview

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


def editable_quote_url():
    """Resolve existing Feishu editable view IDs, never fabricate a view link."""
    token,root=auth()
    tables=table_map(token,root)
    tid=tables.get("Weekly Quote Review")
    if not tid:
        raise SafeError("WEEKLY_DASHBOARD_REVIEW_TABLE_NOT_FOUND")
    views=list_views(token,target_path(root,tid))
    preferred=("그래프 연동 · 최근 5주 검토","전체 Quote 목록")
    name=next((n for n in preferred if views.get(n)),None)
    if not name:
        raise SafeError("WEEKLY_DASHBOARD_REVIEW_VIEW_NOT_FOUND")
    url="https://ocnz4cb25scn.feishu.cn/base/"+BASE+"?table="+tid+"&view="+views[name]
    print("WEEKLY_DASHBOARD_EDITABLE_LIST_URL="+url+" view="+name,flush=True)
    return url


def expected_components(chart_name,note_name,kind,source,detail_url=None,preview=None):
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
    if kind=="combo" and source=="Weekly Quote KPI" and detail_url:
        note_config=dict(note_config)
        note_config["text"]=(
            "### [실제 Quote 목록 보기 · 최근 5주 / 합산 제외 체크]("+detail_url+")\n"
            "**결정할 때 필요한 기관·서비스·공정별 샘플수·참고금액·Active 증빙을 같은 목록에서 확인하세요.**\n"
            "체크한 Quote는 계속 목록에 남고, 최대 15분 주기 GitHub Actions가 "
            "반영 여부를 확인해 집계와 차트를 갱신합니다. 예약 실행은 지연될 수 있습니다.\n"
            "수동 체크를 해제하면 다시 포함되며, Inactive는 체크를 해제해도 합산되지 않습니다.\n\n"
            +note_config["text"]
        )
    components=((chart_name,kind,chart_config),(note_name,"text",note_config))
    if kind=="combo" and preview is not None:
        components+=(BLOCK_NAME,"text",{"text":preview}),
    return components


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
        detail_url=editable_quote_url() if kind=="combo" else None
        preview=read_preview() if kind=="combo" else None
        expected=expected_components(chart_name,note_name,kind,source,detail_url,preview)
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
