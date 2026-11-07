#!/usr/bin/env python3
"""Feishu-native project/payment dashboards. No Vercel and no record mutation.

The existing production dashboard is scoped to PRODUCTION_ACTIVE.
The new Payment Dashboard includes only PAYMENT_FOLLOWUP in detail widgets
and a separate count of PAID_ARCHIVED without exposing archived project rows.
"""
import json
import os
import sys
from native_dashboard_cli import BASE,TABLE,TITLE,BLOCKS,cli,collect,ident,find_named

PAYMENT_TITLE="Novogene 결제 관리 대시보드"

OWNER_FIELD="Payment Owner Scope"
MINE="MY_VERIFIED"
def filter_lane(lane):
    # Fail closed: never show teammates' invoices or unverified sales tags.
    return {"conjunction":"and","conditions":[
        {"field_name":"Workflow Lane","operator":"is","value":lane},
        {"field_name":OWNER_FIELD,"operator":"is","value":MINE}]}
def filter_and(*conditions):
    return {"conjunction":"and","conditions":list(conditions)}
def condition(field,operator,value=None):
    c={"field_name":field,"operator":operator}
    if operator not in {"isEmpty","isNotEmpty"}:c["value"]=value
    return c

PROJECT_BLOCKS={}
for name,typ,config in BLOCKS:
    if typ=="text" or config.get("table_name")!=TABLE:continue
    previous=(config.get("filter") or {}).get("conditions") or []
    active=condition("Workflow Lane","is","PRODUCTION_ACTIVE")
    PROJECT_BLOCKS[name]=filter_and(*(previous if active in previous
                                    else [*previous,active]))

PAYMENT_BLOCKS=[
    ("결제 업무 안내","text",{"text":"# Novogene · 결제 대시보드\n**내 담당자(Kim Taehoon) 원본 일치 건만 표시합니다.** KRW 금액은 백만원(M KRW) 단위로 표시합니다. 완료된 프로젝트는 이 화면에서 Invoice·미수금·Receipt를 추적합니다. 결제 완료 건은 운영 목록에서 숨기되 Feishu Base에 보관합니다.\n**결제 완료 판정:** 최신 날짜의 Payment Receipt + CMS Invoice + AMEA/X + VAT 포함 금액/입금일 정확 일치. Outstanding 잔액이 충돌하면 자동 완료하지 않습니다."}),
    ("결제 확인 대기 프로젝트","statistics",{
        "table_name":TABLE,"count_all":True,
        "filter":filter_lane("PAYMENT_FOLLOWUP")}),
    ("결제 대기 Invoice 총액 (연결 확인분)","statistics",{
        "table_name":TABLE,
        "series":[{"field_name":"Invoice Gross M KRW","rollup":"SUM"}],
        "filter":filter_lane("PAYMENT_FOLLOWUP")}),
    ("결제 대기 미수 잔액 (원본 확인분)","statistics",{
        "table_name":TABLE,
        "series":[{"field_name":"Outstanding Balance M KRW","rollup":"SUM"}],
        "filter":filter_lane("PAYMENT_FOLLOWUP")}),
    ("입금 확인 · 보관 건수","statistics",{
        "table_name":TABLE,"count_all":True,
        "filter":filter_lane("PAID_ARCHIVED")}),
    ("결제 대기 · Quote Full Name","ranking",{
        "table_name":TABLE,"count_all":True,
        "group_by":[{"field_name":"Project Display Name","mode":"integrated",
                     "sort":{"type":"value","order":"desc"}}],
        "limit_size":500,"filter":filter_lane("PAYMENT_FOLLOWUP")}),
    ("결제 대기 상태 분포","pie",{
        "table_name":TABLE,"count_all":True,
        "group_by":[{"field_name":"Payment State","mode":"integrated"}],
        "filter":filter_lane("PAYMENT_FOLLOWUP")}),
    ("결제 대기 프로젝트 미수금","bar",{
        "table_name":TABLE,
        "series":[{"field_name":"Outstanding Balance M KRW","rollup":"SUM"}],
        "group_by":[{"field_name":"Project Display Name","mode":"integrated",
                     "sort":{"type":"value","order":"desc"}}],
        "filter":filter_lane("PAYMENT_FOLLOWUP")}),
]
def block_id(row):
    for key in ("block_id","id"):
        value=row.get(key)
        if isinstance(value,str) and value.startswith(("cht","blk")):
            return value
    return None

def find_block(rows,name):
    matching={}
    for row in collect(rows):
        if row.get("name")==name and block_id(row):
            matching[block_id(row)]=row
    if len(matching)>1:raise RuntimeError("DUPLICATE_PAYMENT_DASHBOARD_BLOCK")
    return next(iter(matching.values())) if matching else None

def ensure_dashboard(name):
    listing=cli("+dashboard-list","--base-token",BASE)
    current=find_named(listing,name)
    if current:return current,False
    created=cli("+dashboard-create","--base-token",BASE,"--name",name)
    current=find_named(created,name) or ident(created)
    if not current:
        current=find_named(cli("+dashboard-list","--base-token",BASE),name)
    if not current:raise RuntimeError("PAYMENT_DASHBOARD_CREATION_NOT_VERIFIED")
    return current,True

def main():
    if os.environ.get("FEISHU_BASE_APP_TOKEN")!=BASE:
        raise RuntimeError("REFUSE_OTHER_BASE")
    mode=os.environ.get("FEISHU_PAYMENT_DASHBOARD_MODE","plan")
    if mode not in {"plan","apply"}:raise RuntimeError("BAD_MODE")
    listing=cli("+dashboard-list","--base-token",BASE)
    production=find_named(listing,TITLE)
    if not production:raise RuntimeError("PRODUCTION_DASHBOARD_MISSING")
    payment=find_named(listing,PAYMENT_TITLE)
    print("FEISHU_PAYMENT_DASHBOARD_SOURCE_PASS production_existing="+str(bool(production))+
          " payment_existing="+str(bool(payment)))
    if mode=="plan":
        print("FEISHU_PAYMENT_DASHBOARD_PLAN_PASS widgets="+str(len(PAYMENT_BLOCKS))+
              " updated_production_filters="+str(len(PROJECT_BLOCKS))+" writes=0")
        return
    payment,created=ensure_dashboard(PAYMENT_TITLE)
    existing=cli("+dashboard-block-list","--base-token",BASE,"--dashboard-id",payment)
    created_count=0
    updated_count=0
    for name,kind,config in PAYMENT_BLOCKS:
        prior=find_block(existing,name)
        if prior:
            # Preserve existing block layouts; update only the source metric,
            # owner filter or text note. Never recreate customer-facing cards.
            updated_config=({"text":config["text"]} if kind=="text" else
                            {"filter":config["filter"],
                             **({"series":config["series"]} if "series" in config else {})})
            cli("+dashboard-block-update","--base-token",BASE,
                "--dashboard-id",payment,"--block-id",block_id(prior),
                "--data-config",json.dumps(updated_config,ensure_ascii=False,
                                           separators=(",",":")))
            updated_count+=1
            continue
        cli("+dashboard-block-create","--base-token",BASE,
            "--dashboard-id",payment,"--name",name,"--type",kind,
            "--data-config",json.dumps(config,ensure_ascii=False,separators=(",",":")))
        created_count+=1
        print("FEISHU_PAYMENT_WIDGET_CREATED type="+kind)
    final=cli("+dashboard-block-list","--base-token",BASE,"--dashboard-id",payment)
    missing=[name for name,_,_ in PAYMENT_BLOCKS if not find_block(final,name)]
    if missing:raise RuntimeError("PAYMENT_WIDGETS_MISSING_"+str(len(missing)))

    original=cli("+dashboard-block-list","--base-token",BASE,"--dashboard-id",production)
    updated=0
    for name,flt in PROJECT_BLOCKS.items():
        block=find_block(original,name)
        if not block:raise RuntimeError("PRODUCTION_PROJECT_BLOCK_NOT_FOUND")
        bid=block_id(block)
        cli("+dashboard-block-update","--base-token",BASE,
            "--dashboard-id",production,"--block-id",bid,
            "--data-config",json.dumps({"filter":flt},ensure_ascii=False,separators=(",",":")))
        updated+=1
    print("FEISHU_PROJECT_PAYMENT_DASHBOARDS_PASS production="+production+
          " payment="+payment+" payment_widgets="+str(len(PAYMENT_BLOCKS))+
          " created="+str(created_count)+" owner_filters_updated="+str(updated_count)+
          " production_filters="+str(updated)+
          " source=Feishu_Base source_record_writes=0 VERCEL_REQUIRED=FALSE")
    print("FEISHU_PAYMENT_DASHBOARD_BASE_URL=https://ocnz4cb25scn.feishu.cn/base/"+BASE)

if __name__=="__main__":
    try:main()
    except Exception as e:
        print("FEISHU_PAYMENT_DASHBOARD_FAILED="+
              (str(e) if isinstance(e,RuntimeError) else type(e).__name__),file=sys.stderr)
        sys.exit(1)
