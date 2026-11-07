#!/usr/bin/env python3
"""Feishu-hosted X Project Dashboard; all values sourced from X Registry Base.

No AMEA-level progress percentages are projected onto X, and no ranking.
"""
import json
import os
import sys
from native_dashboard_cli import BASE,cli,find_named,ident,collect

NAME="Novogene X 프로젝트 운영 대시보드"
CURRENT={"field_name":"Record State","operator":"is","value":"CURRENT"}
MINE={"field_name":"Owner Scope","operator":"is","value":"MY_VERIFIED"}
def scope(*conditions):
    return {"conjunction":"and","conditions":list(conditions)}
WIDGETS=[
  ("X 프로젝트 안내","text",{
      "text":"# X 프로젝트 운영\n**X-Z01=프로젝트 · SAM=시료 · AMEA=견적 · H=계약**\n**P0 즉시 확인 / P1 후속 확인 / P2 모니터링**\n메모 날짜는 실제 수정일이 아닙니다. 상세는 '내 X 프로젝트', 시료는 'X-SAM 확정 연결'에서 확인하세요. X별 진행률·입금 완료는 증빙 없이는 추정하지 않습니다."}),
  ("내 X 프로젝트 건수","statistics",{
      "table_name":"X Project Registry","count_all":True,
      "filter":scope(CURRENT,MINE)}),
  ("정확 연결된 내 X","statistics",{
      "table_name":"X Project Registry","count_all":True,
      "filter":scope(CURRENT,MINE,
                     {"field_name":"AMEA Link State","operator":"is",
                      "value":"EXACT_LIFECYCLE"})}),
  ("내 X 프로젝트 상태별 현황","bar",{
      "table_name":"X Project Registry","count_all":True,
      "group_by":[{"field_name":"Project Status","mode":"integrated"}],
      "filter":scope(CURRENT,MINE)}),
  ("확인된 SAM 연결 건수","statistics",{
      "table_name":"X Project Registry",
      "series":[{"field_name":"SAM Linked","rollup":"SUM"}],
      "filter":scope(CURRENT,MINE)}),
  ("내 X Invoice 건수","statistics",{
      "table_name":"X Invoice Ledger","count_all":True,
      "filter":scope(CURRENT,MINE)}),
  ("내 X 연결 상태","pie",{
      "table_name":"X Project Registry","count_all":True,
      "group_by":[{"field_name":"AMEA Link State","mode":"integrated"}],
      "filter":scope(CURRENT,MINE)}),
  ("내 즉시 확인 X","statistics",{
      "table_name":"X Project Registry","count_all":True,
      "filter":scope(CURRENT,MINE,
          {"field_name":"Exception Priority","operator":"is",
           "value":"P0_URGENT"})}),
  ("내 후속 확인 X","statistics",{
      "table_name":"X Project Registry","count_all":True,
      "filter":scope(CURRENT,MINE,
          {"field_name":"Attention State","operator":"is",
           "value":"REVIEW_REQUIRED"})}),
  ("내 30일 이상 날짜 메모 X","statistics",{
      "table_name":"X Project Registry","count_all":True,
      "filter":scope(CURRENT,MINE,
          {"field_name":"Dated Note Age Flag","operator":"is",
           "value":"DATED_NOTE_30D_PLUS"})}),
  ("내 X 예외 원인별 현황","bar",{
      "table_name":"X Project Registry","count_all":True,
      "group_by":[{"field_name":"Primary Reason","mode":"integrated"}],
      "filter":scope(CURRENT,MINE,
          {"field_name":"Attention State","operator":"is",
           "value":"REVIEW_REQUIRED"})}),

]

# All source counts (X projects, SAM, invoices) are integer quantities.
# Only statistics type accepts the official CLI number_format property.
for _name,_kind,_config in WIDGETS:
    if _kind=="statistics":
        _config["number_format"]={"formatName":"digital","precision":0}

def bid(block):
    for field in ("block_id","id"):
        v=block.get(field)
        if isinstance(v,str) and v.startswith(("cht","blk")):return v
    return ""

def find_block(root,name):
    found={bid(b):b for b in collect(root) if b.get("name")==name and bid(b)}
    if len(found)>1:raise RuntimeError("X_DASHBOARD_DUPLICATE_BLOCK")
    return next(iter(found.values())) if found else None

def main():
    if os.environ.get("FEISHU_BASE_APP_TOKEN")!=BASE:
        raise RuntimeError("REFUSE_OTHER_BASE")
    mode=os.environ.get("FEISHU_X_DASHBOARD_MODE","plan")
    if mode not in {"plan","apply"}:raise RuntimeError("X_DASHBOARD_BAD_MODE")
    listing=cli("+dashboard-list","--base-token",BASE)
    dashboard=find_named(listing,NAME)
    if mode=="plan":
        print("X_DASHBOARD_PLAN_PASS existing="+str(bool(dashboard))+
              " widgets="+str(len(WIDGETS))+" writes=0")
        return
    if not dashboard:
        created=cli("+dashboard-create","--base-token",BASE,"--name",NAME)
        dashboard=find_named(created,NAME) or ident(created)
        if not dashboard:dashboard=find_named(
            cli("+dashboard-list","--base-token",BASE),NAME)
        if not dashboard:raise RuntimeError("X_DASHBOARD_CREATE_READBACK_FAILED")
    existing=cli("+dashboard-block-list","--base-token",BASE,"--dashboard-id",dashboard)
    created_count=updated_count=0
    for title,typ,config in WIDGETS:
        prior=find_block(existing,title)
        if prior:
            if typ=="text":
                # Keep warning copy current after rule/schema revisions.
                cli("+dashboard-block-update","--base-token",BASE,
                    "--dashboard-id",dashboard,"--block-id",bid(prior),
                    "--data-config",json.dumps(config,ensure_ascii=False,
                                               separators=(",",":")))
                updated_count+=1
                continue
            cli("+dashboard-block-update","--base-token",BASE,
                "--dashboard-id",dashboard,"--block-id",bid(prior),
                "--data-config",json.dumps(config,ensure_ascii=False,
                                           separators=(",",":")))
            updated_count+=1
            continue
        cli("+dashboard-block-create","--base-token",BASE,
            "--dashboard-id",dashboard,"--name",title,"--type",typ,
            "--data-config",json.dumps(config,ensure_ascii=False,
                                       separators=(",",":")))
        created_count+=1
    final=cli("+dashboard-block-list","--base-token",BASE,"--dashboard-id",dashboard)
    if any(not find_block(final,title) for title,_,_ in WIDGETS):
        raise RuntimeError("X_DASHBOARD_WIDGET_READBACK_MISSING")
    print("X_DASHBOARD_APPLY_PASS id="+dashboard+
          " widgets="+str(len(WIDGETS))+
          " created="+str(created_count)+" updated="+str(updated_count)+
          " original_project_rows_written=0 VERCEL_REQUIRED=FALSE")
    print("X_DASHBOARD_URL=https://ocnz4cb25scn.feishu.cn/base/"+BASE)

if __name__=="__main__":
    try:main()
    except Exception as exc:
        print("X_DASHBOARD_FAILED="+(
            str(exc) if isinstance(exc,RuntimeError) else type(exc).__name__),
            file=sys.stderr)
        sys.exit(1)
