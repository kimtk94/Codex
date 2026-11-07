#!/usr/bin/env python3
"""Create an idempotent Feishu-hosted Dashboard from existing Sales Base.

No Vercel, no user-hosted server, no customer table edits.
All Feishu data stays in the original Base. The app identity must have
dashboard creation scopes and actual Base management permissions.
"""
import json
import os
import subprocess
import sys

BASE="IpMkbUD0vaFqtYs93a3csXtdn1b"
TITLE="Novogene 프로젝트 운영 대시보드"
TABLE="Project Progress Board"

# Each data config is grounded in the verified Sales Base field schema.
BLOCKS=[
    ("운영 안내","text",{"text":"# Novogene · 프로젝트 진행 현황\n**Feishu Base 실시간 데이터** · Quote Full Name 원문과 개별 진행률을 추적합니다.\nPrepayment는 SIF 제출이 필수가 아니며, Final Report/Statement의 PO 제출 여부는 추정과 직접 접수를 구분합니다."}),
    ("전체 프로젝트","statistics",{"table_name":TABLE,"count_all":True}),
    ("진행률 확인 건수","statistics",{"table_name":TABLE,"count_all":True,
        "filter":{"conjunction":"and","conditions":[{"field_name":"Progress %","operator":"isNotEmpty"}]}}),
    ("Prepayment 프로젝트","statistics",{"table_name":TABLE,"count_all":True,
        "filter":{"conjunction":"and","conditions":[{"field_name":"Prepayment","operator":"is","value":"YES"}]}}),
    ("진행률 · Quote Full Name","ranking",{"table_name":TABLE,
        "series":[{"field_name":"Progress %","rollup":"AVERAGE"}],
        "group_by":[{"field_name":"Quote Full Name","mode":"integrated",
                     "sort":{"type":"value","order":"asc"}}],
        "limit_size":500}),
    ("프로젝트 단계별 분포","bar",{"table_name":TABLE,"count_all":True,
        "group_by":[{"field_name":"Current Stage","mode":"integrated"}]}),
    ("SIF 상태","pie",{"table_name":TABLE,"count_all":True,
        "group_by":[{"field_name":"SIF State","mode":"integrated"}]}),
    ("월별 Revenue · VAT 제외","line",{
        "table_name":"Monthly Tax Invoice",
        "series":[{"field_name":"Net Revenue KRW Ex VAT","rollup":"SUM"}],
        "group_by":[{"field_name":"Month","mode":"integrated",
                     "sort":{"type":"group","order":"asc"}}]}),
    ("Weekly 승인 Quote","column",{
        "table_name":"Weekly Quote KPI",
        "series":[{"field_name":"Approved Quote Count","rollup":"SUM"}],
        "group_by":[{"field_name":"Week Start","mode":"integrated",
                     "sort":{"type":"group","order":"asc"}}]}),
    ("KOREA · Quote Count / Value (K USD)","combo",{
        "table_name":"Weekly Quote KPI",
        "series":[{"field_name":"Approved Quote Count","rollup":"SUM"},
                  {"field_name":"Verified Quote Value K USD","rollup":"SUM"}],
        "group_by":[{"field_name":"Chart Week Label","mode":"integrated",
                     "sort":{"type":"view","order":"desc"}}],
        "filter":{"conjunction":"and","conditions":[
            {"field_name":"Chart Window","operator":"is",
             "value":"RECENT_4_COMPLETED"}]}}),
    ("KOREA · Quote Count / Value (KRW)","combo",{
        "table_name":"Weekly Quote KPI",
        "series":[{"field_name":"Approved Quote Count","rollup":"SUM"},
                  {"field_name":"Verified Quote Value KRW FX","rollup":"SUM"}],
        "group_by":[{"field_name":"Chart Week Label","mode":"integrated",
                     "sort":{"type":"view","order":"desc"}}],
        "filter":{"conjunction":"and","conditions":[
            {"field_name":"Chart Window","operator":"is",
             "value":"RECENT_4_COMPLETED"}]}}),
    ("Quote 금액 검증 기준","text",{
        "text":"# KOREA · Quote Count / Value\n**차트 대상:** 최근 종료된 4개 주간, 금요일~목요일 기준입니다. X축은 Oct W2 · Oct W3 · Oct W4 · Nov W1처럼 해당 기간의 월요일을 기준으로 표시합니다.\n**파란 막대:** Approved Quote Count(건), **왼쪽 Y축: Count**.\n**주황색 선:** Verified Quote Value K USD(천 USD) 또는 Verified Quote Value KRW FX(원), **오른쪽 Y축: Value (K USD/KRW)**.\n데이터 라벨·가로 그리드·좌우 축을 표시합니다. 두 계열의 색상, 막대/선 유형, 2차 축 지정은 Feishu 차트의 [설정 → 시리즈]에서 선택해야 합니다. 현재 공식 CLI는 개별 시리즈 스타일/2차 축 인수를 제공하지 않습니다.\n**금액 검증:** SFDC Quote ID가 연결된 승인 견적 금액만 합산합니다. 금액 미확인 건도 Count에는 포함하지만 금액을 0으로 간주하지 않습니다."})

]

def cli(*args):
    process=subprocess.run(["lark-cli","base",*args,"--as","bot","--format","json"],
                           text=True,capture_output=True,timeout=70)
    if process.returncode:
        # Never print OAuth tokens or full command response to public Actions.
        raise RuntimeError("FEISHU_CLI_COMMAND_FAILED_"+str(args[0]))
    output=process.stdout.strip()
    if not output:raise RuntimeError("FEISHU_CLI_EMPTY_"+str(args[0]))
    try:return json.loads(output)
    except json.JSONDecodeError:
        # Some CLI versions add a status line. Read a trailing JSON object.
        start=output.find("{")
        if start>=0:
            try:return json.loads(output[start:])
            except json.JSONDecodeError:pass
        raise RuntimeError("FEISHU_CLI_UNEXPECTED_FORMAT_"+str(args[0]))

def collect(node):
    if isinstance(node,list):
        for item in node:yield from collect(item)
    elif isinstance(node,dict):
        yield node
        for value in node.values():
            if isinstance(value,(dict,list)):yield from collect(value)

def ident(node):
    for k in ("dashboard_id","block_id","id"):
        v=node.get(k)
        if isinstance(v,str) and v.startswith("blk"):return v
    return None

def find_named(resp,name):
    matches={}
    for row in collect(resp):
        if row.get("name")==name and ident(row):
            matches[ident(row)]=row
    if len(matches)>1:raise RuntimeError("FEISHU_DUPLICATE_DASHBOARD_OR_BLOCK")
    return next(iter(matches)) if matches else None

LEGACY_COMBO_NAMES={
    "KOREA · Quote Count / Value (K USD)":"Weekly Quote · 건수 + 검증금액 K USD",
    "KOREA · Quote Count / Value (KRW)":"Weekly Quote · 건수 + 검증금액 KRW",
}
def locate_chart(rows,target):
    for row in collect(rows):
        if row.get("name")==target:
            ident_value=row.get("block_id") or row.get("id")
            if isinstance(ident_value,str) and ident_value.startswith(("cht","blk")):
                return ident_value
    return None


def main():
    if os.environ.get("FEISHU_BASE_APP_TOKEN")!=BASE:
        raise RuntimeError("REFUSE_OTHER_BASE")
    if os.environ.get("FEISHU_DASHBOARD_MODE","plan") not in {"plan","apply"}:
        raise RuntimeError("BAD_MODE")
    mode=os.environ.get("FEISHU_DASHBOARD_MODE","plan")
    dashboards=cli("+dashboard-list","--base-token",BASE)
    dashboard_id=find_named(dashboards,TITLE)
    print("FEISHU_NATIVE_DASHBOARD_LIST_PASS exists="+str(bool(dashboard_id)))
    if mode=="plan":
        print("FEISHU_NATIVE_DASHBOARD_PLAN_PASS source="+BASE+" writes=0 planned_blocks="+str(len(BLOCKS)))
        return
    if not dashboard_id:
        created=cli("+dashboard-create","--base-token",BASE,"--name",TITLE)
        dashboard_id=find_named(created,TITLE) or ident(created)
        if not dashboard_id:
            dashboard_id=find_named(cli("+dashboard-list","--base-token",BASE),TITLE)
        if not dashboard_id:raise RuntimeError("FEISHU_DASHBOARD_CREATE_READBACK_MISSING")
        print("FEISHU_NATIVE_DASHBOARD_CREATED="+dashboard_id)
    existing=cli("+dashboard-block-list","--base-token",BASE,"--dashboard-id",dashboard_id)
    names={row.get("name") for row in collect(existing) if isinstance(row.get("name"),str)}
    count=0
    updated=0
    existing=cli("+dashboard-block-list","--base-token",BASE,"--dashboard-id",dashboard_id)
    for name,kind,config in BLOCKS:
        if kind=="combo":
            chart=locate_chart(existing,name) or locate_chart(
                existing,LEGACY_COMBO_NAMES.get(name,""))
            if chart:
                # Update the real existing combo instead of creating a duplicate
                # and restrict the data to the latest 4 completed sales weeks.
                cli("+dashboard-block-update","--base-token",BASE,
                    "--dashboard-id",dashboard_id,"--block-id",chart,
                    "--name",name,
                    "--data-config",json.dumps(config,ensure_ascii=False,separators=(",",":")))
                updated+=1
                print("FEISHU_QUOTE_COMBO_UPDATED type=combo window=RECENT_4_COMPLETED")
                continue
        if name in names:
            if name=="Quote 금액 검증 기준":
                info=locate_chart(existing,name)
                if info:
                    cli("+dashboard-block-update","--base-token",BASE,
                        "--dashboard-id",dashboard_id,"--block-id",info,
                        "--data-config",json.dumps(config,ensure_ascii=False,separators=(",",":")))
                    updated+=1
            continue
        cli("+dashboard-block-create","--base-token",BASE,"--dashboard-id",dashboard_id,
            "--name",name,"--type",kind,
            "--data-config",json.dumps(config,ensure_ascii=False,separators=(",",":")))
        count+=1
        print("FEISHU_NATIVE_COMPONENT_CREATED="+kind+" index="+str(count))
    final=cli("+dashboard-block-list","--base-token",BASE,"--dashboard-id",dashboard_id)
    found={row.get("name") for row in collect(final) if isinstance(row.get("name"),str)}
    missing={n for n,_,_ in BLOCKS}-found
    if missing:raise RuntimeError("FEISHU_NATIVE_COMPONENTS_MISSING_"+str(len(missing)))
    print("FEISHU_NATIVE_DASHBOARD_PASS id="+dashboard_id+
          " blocks="+str(len(BLOCKS))+" created="+str(count)+" updated="+str(updated)+
          " customer_rows_written=0 VERCEL_REQUIRED=FALSE")
    print("FEISHU_NATIVE_DASHBOARD_BASE_URL=https://ocnz4cb25scn.feishu.cn/base/"+BASE)
if __name__=="__main__":
    try:main()
    except Exception as ex:
        reason=str(ex) if isinstance(ex,RuntimeError) else type(ex).__name__
        print("FEISHU_NATIVE_DASHBOARD_FAILED="+reason,file=sys.stderr)
        sys.exit(1)
