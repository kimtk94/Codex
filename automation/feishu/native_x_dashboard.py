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
      "text":"# Novogene · X 하위 프로젝트 현황\n**X-Z01은 실제 프로젝트**, AMEA는 견적/영업 그룹, H는 계약, SAM은 시료입니다.\n프로젝트별 단계·TAT·시료 연결을 확인하세요. 정확하지 않은 연결은 별도 검토이며 AMEA 진행률 100%를 X에 복사하지 않습니다.\n프로젝트 상세는 Feishu Base의 '내 X 프로젝트', 시료는 'X-SAM 확정 연결'에서 확인할 수 있습니다. 결제 완료는 CMS Invoice와 Receipt 및 실제 프로젝트 완료가 모두 확인된 경우에만 보관 처리합니다."}),
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
]

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
                # Existing stable explanatory text needs no rewrites.
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
