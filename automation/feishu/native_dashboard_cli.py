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
    ("운영 안내","text",{"text":"# Novogene · 프로젝트 진행 현황\n**순위 없음:** 진행률 %는 프로젝트 간 우열을 비교하는 지표가 아니라 개별 공정 진행 상태입니다.\n**공정 분포:** 계약/SIF → 샘플/QC → 라이브러리 → 시퀀싱 → 데이터/리포트. 불명확한 단계는 별도로 표시합니다.\n**개별 프로젝트:** Feishu Base의 '진행 중 프로젝트' 보기에서 Quote Full Name, Progress Bar, Current Stage, Next Action을 검색·확인하세요. 낮은 %가 우선순위를 의미하지 않습니다.\n**운영:** Prepayment는 SIF 의무가 아닙니다. Final Report/Statement 완료는 Payment 대시보드로 이동하며, 결제 완료는 목록에서 숨깁니다. 지연 판정은 확정된 예정일·근거가 있는 경우에만 합니다.\n**Weekly Quote 차트:** 완료된 최근 4개 금–목 주간을 월요일 MM/DD 기준으로 표시합니다. 파란 막대=승인 Quote 건수, 주황 선=검증된 금액(K USD). 금액 미확인 Quote는 건수에만 포함하며 금액을 0으로 간주하지 않습니다."}),
    ("전체 프로젝트","statistics",{"table_name":TABLE,"count_all":True}),
    ("진행률 확인 건수","statistics",{"table_name":TABLE,"count_all":True,
        "filter":{"conjunction":"and","conditions":[{"field_name":"Progress %","operator":"isNotEmpty"}]}}),
    ("Prepayment 프로젝트","statistics",{"table_name":TABLE,"count_all":True,
        "filter":{"conjunction":"and","conditions":[{"field_name":"Prepayment","operator":"is","value":"YES"}]}}),
    ("진행률 미확인 건수","statistics",{"table_name":TABLE,
        "count_all":True,
        "filter":{"conjunction":"and","conditions":[
            {"field_name":"Progress %","operator":"isEmpty"}]}}),
    ("프로젝트 공정별 현황","bar",{"table_name":TABLE,"count_all":True,
        "group_by":[{"field_name":"Progress Phase","mode":"integrated",
                     "sort":{"type":"group","order":"asc"}}]}),
    ("SIF 상태","pie",{"table_name":TABLE,"count_all":True,
        "group_by":[{"field_name":"SIF State","mode":"integrated"}]}),
    ("월별 Revenue · VAT 제외 (M KRW)","line",{
        "table_name":"Monthly Tax Invoice",
        "series":[{"field_name":"Net Revenue M KRW","rollup":"SUM"}],
        "group_by":[{"field_name":"Month","mode":"integrated",
                     "sort":{"type":"group","order":"asc"}}]}),
    ("Weekly Quote · 건수 + 금액 (K USD)","combo",{
        "table_name":"Weekly Quote KPI",
        "series":[{"field_name":"Approved Quote Count","rollup":"SUM"},
                  {"field_name":"Verified Quote Value K USD","rollup":"SUM"}],
        "group_by":[{"field_name":"Chart Week Label","mode":"integrated",
                     "sort":{"type":"view","order":"asc"}}],
        "filter":{"conjunction":"and","conditions":[
            {"field_name":"Chart Window","operator":"is",
             "value":"RECENT_4_COMPLETED"}]}}),

]

# Feishu official CLI permits number_format only on statistics cards.
# Count metrics are integers; never display a trailing .0 on a count card.
for _title,_kind,_config in BLOCKS:
    if _kind=="statistics" and _config.get("count_all"):
        _config["number_format"]={"formatName":"digital","precision":0}

# Active pipeline only: paid/completed projects belong to Payment Dashboard.
ACTIVE_STAGE={"field_name":"Workflow Lane","operator":"is","value":"PRODUCTION_ACTIVE"}
for _,kind,_config in BLOCKS:
    if kind=="text" or _config.get("table_name")!=TABLE:
        continue
    current=(_config.get("filter") or {}).get("conditions") or []
    if ACTIVE_STAGE not in current:
        _config["filter"]={"conjunction":"and","conditions":[*current,ACTIVE_STAGE]}


def delete_dashboard_block(dashboard_id,block_id):
    """Delete only a verified dashboard block; empty successful replies are OK."""
    p=subprocess.run([
        "lark-cli","base","+dashboard-block-delete",
        "--base-token",BASE,"--dashboard-id",dashboard_id,
        "--block-id",block_id,"--yes","--as","bot","--format","json",
    ],text=True,capture_output=True,timeout=70)
    if p.returncode:
        raise RuntimeError("FEISHU_DASHBOARD_BLOCK_DELETE_FAILED")


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

LEGACY_PROGRESS_RANK="진행률 · Quote Full Name"
LEGACY_RAW_STAGE_CHART="프로젝트 단계별 분포"

def legacy_dashboard_block(rows,name,expected_type=None):
    """Find exactly one named dashboard-only block, never a Base source table."""
    candidates=[row for row in collect(rows)
                if row.get("name")==name
                and isinstance(row.get("block_id") or row.get("id"),str)
                and str(row.get("block_id") or row.get("id")).startswith(("cht","blk"))]
    if len(candidates)>1:raise RuntimeError("LEGACY_DASHBOARD_BLOCK_AMBIGUOUS")
    if not candidates:return None
    current=candidates[0]
    if expected_type is not None and current.get("type")!=expected_type:
        raise RuntimeError("LEGACY_DASHBOARD_TYPE_MISMATCH")
    return current.get("block_id") or current.get("id")


LEGACY_QUOTE_CHART_NAMES=(
    "KOREA · Quote Count / Value (K USD)",
    "Weekly Quote · 건수 + 검증금액 K USD",
)
# Explicit names and types only. Never delete source Base fields/records.
LEGACY_REDUNDANT_QUOTE_WIDGETS={
    "Weekly 승인 Quote":"column",
    "KOREA · Quote Count / Value (M KRW)":"combo",
    "KOREA · Quote Count / Value (KRW)":"combo",
    "Weekly Quote · 건수 + 검증금액 KRW":"combo",
    "Quote 금액 검증 기준":"text",
    **{name:"combo" for name in LEGACY_QUOTE_CHART_NAMES},
}
LEGACY_REVENUE_NAME="월별 Revenue · VAT 제외"
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
        if dashboard_id:
            existing=cli("+dashboard-block-list","--base-token",BASE,
                         "--dashboard-id",dashboard_id)
            for legacy in (LEGACY_PROGRESS_RANK,LEGACY_RAW_STAGE_CHART):
                candidates=[x for x in collect(existing) if x.get("name")==legacy
                            and x.get("block_id")]
                if len(candidates)>1:
                    raise RuntimeError("LEGACY_PROGRESS_MULTIPLE_BLOCKS")
                print("FEISHU_PROGRESS_PRECHECK name="+legacy+
                      " exists="+str(bool(candidates))+
                      " type="+str(candidates[0].get("type") if candidates else "none"))
            for obsolete,kind in LEGACY_REDUNDANT_QUOTE_WIDGETS.items():
                found=legacy_dashboard_block(existing,obsolete,kind)
                if found:
                    print("FEISHU_WEEKLY_QUOTE_CLEANUP_PLAN name="+obsolete+" type="+kind)
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
    # User requested removal of the comparative ranking. Delete the precise
    # old dashboard widget only; never touch project rows or Base views.
    legacy_rank=legacy_dashboard_block(existing,LEGACY_PROGRESS_RANK,"ranking")
    deleted=0
    if legacy_rank:
        delete_dashboard_block(dashboard_id,legacy_rank)
        deleted=1
        print("FEISHU_PROGRESS_RANK_REMOVED title="+LEGACY_PROGRESS_RANK)
    count=0
    updated=0
    existing=cli("+dashboard-block-list","--base-token",BASE,"--dashboard-id",dashboard_id)
    legacy_stage=legacy_dashboard_block(existing,LEGACY_RAW_STAGE_CHART,"bar")
    if legacy_stage:
        delete_dashboard_block(dashboard_id,legacy_stage)
        deleted+=1
        print("FEISHU_RAW_STAGE_GRAPH_REMOVED")
        existing=cli("+dashboard-block-list","--base-token",BASE,"--dashboard-id",dashboard_id)
    names={row.get("name") for row in collect(existing) if isinstance(row.get("name"),str)}
    for name,kind,config in BLOCKS:
        if kind=="combo":
            # Reuse the actual K USD chart; do not create a duplicate.
            chart=legacy_dashboard_block(existing,name,"combo")
            if chart is None:
                for old_name in LEGACY_QUOTE_CHART_NAMES:
                    chart=legacy_dashboard_block(existing,old_name,"combo")
                    if chart:break
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
        if name=="월별 Revenue · VAT 제외 (M KRW)":
            old=locate_chart(existing,name) or locate_chart(existing,LEGACY_REVENUE_NAME)
            if old:
                cli("+dashboard-block-update","--base-token",BASE,
                    "--dashboard-id",dashboard_id,"--block-id",old,
                    "--name",name,
                    "--data-config",json.dumps(config,ensure_ascii=False,
                                               separators=(",",":")))
                updated+=1
                print("FEISHU_REVENUE_UNIT_UPDATED=M_KRW")
                continue
        if name in names:
            info=locate_chart(existing,name)
            if (name in {"Quote 금액 검증 기준","운영 안내"} or
                kind=="statistics") and info:
                cli("+dashboard-block-update","--base-token",BASE,
                    "--dashboard-id",dashboard_id,"--block-id",info,
                    "--data-config",json.dumps(config,ensure_ascii=False,separators=(",",":")))
                updated+=1
            elif config.get("table_name")==TABLE and info:
                # Rewrite only the scope, never reposition the user's widgets.
                cli("+dashboard-block-update","--base-token",BASE,
                    "--dashboard-id",dashboard_id,"--block-id",info,
                    "--data-config",json.dumps({"filter":config["filter"]},
                        ensure_ascii=False,separators=(",",":")))
                updated+=1
            continue
        cli("+dashboard-block-create","--base-token",BASE,"--dashboard-id",dashboard_id,
            "--name",name,"--type",kind,
            "--data-config",json.dumps(config,ensure_ascii=False,separators=(",",":")))
        count+=1
        print("FEISHU_NATIVE_COMPONENT_CREATED="+kind+" index="+str(count))
    # Remove redundant weekly-count, M KRW combo and verbose chart note.
    # Confirm the surviving combined K USD widget exists before any deletion.
    final=cli("+dashboard-block-list","--base-token",BASE,"--dashboard-id",dashboard_id)
    if not legacy_dashboard_block(final,"Weekly Quote · 건수 + 금액 (K USD)","combo"):
        raise RuntimeError("WEEKLY_QUOTE_COMBINED_CHART_MISSING_BEFORE_CLEANUP")
    for obsolete,widget_type in LEGACY_REDUNDANT_QUOTE_WIDGETS.items():
        block_id=legacy_dashboard_block(final,obsolete,widget_type)
        if block_id:
            delete_dashboard_block(dashboard_id,block_id)
            deleted+=1
            print("FEISHU_REDUNDANT_QUOTE_WIDGET_REMOVED="+obsolete)
    final=cli("+dashboard-block-list","--base-token",BASE,"--dashboard-id",dashboard_id)
    for obsolete in LEGACY_REDUNDANT_QUOTE_WIDGETS:
        if legacy_dashboard_block(final,obsolete):
            raise RuntimeError("REDUNDANT_WEEKLY_QUOTE_WIDGET_STILL_EXISTS")
    if legacy_dashboard_block(final,LEGACY_PROGRESS_RANK):
        raise RuntimeError("PROGRESS_RANK_STILL_EXISTS")
    if legacy_dashboard_block(final,LEGACY_RAW_STAGE_CHART):
        raise RuntimeError("LEGACY_STAGE_GRAPH_STILL_EXISTS")
    found={row.get("name") for row in collect(final) if isinstance(row.get("name"),str)}
    missing={n for n,_,_ in BLOCKS}-found
    if missing:raise RuntimeError("FEISHU_NATIVE_COMPONENTS_MISSING_"+str(len(missing)))
    print("FEISHU_NATIVE_DASHBOARD_PASS id="+dashboard_id+
          " blocks="+str(len(BLOCKS))+" created="+str(count)+" updated="+str(updated)+" legacy_removed="+str(deleted)+
          " customer_rows_written=0 VERCEL_REQUIRED=FALSE")
    print("FEISHU_NATIVE_DASHBOARD_BASE_URL=https://ocnz4cb25scn.feishu.cn/base/"+BASE)
if __name__=="__main__":
    try:main()
    except Exception as ex:
        reason=str(ex) if isinstance(ex,RuntimeError) else type(ex).__name__
        print("FEISHU_NATIVE_DASHBOARD_FAILED="+reason,file=sys.stderr)
        sys.exit(1)
