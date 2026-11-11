#!/usr/bin/env python3
"""Create an idempotent Feishu-hosted Dashboard from existing Sales Base.

No Vercel, no user-hosted server, no customer table edits.
All Feishu data stays in the original Base. The app identity must have
dashboard creation scopes and actual Base management permissions.
"""
import datetime as dt
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
from zoneinfo import ZoneInfo
from weekly_quote_live_chart import config as live_quote_config, preflight as live_quote_preflight

BASE="IpMkbUD0vaFqtYs93a3csXtdn1b"
TITLE="Novogene 프로젝트 운영 대시보드"
TABLE="Project Progress Board"
KST=ZoneInfo("Asia/Seoul")
AUDIT_BOOK="1Fo0Tc6PQ3Ek0-33lmegScM_z8ST-ShUYQ0K3kD4PqnI"

# Each data config is grounded in the verified Sales Base field schema.
BLOCKS=[
    ("운영 안내","text",{"text":"# Novogene · 프로젝트 진행 현황\n**순위 없음:** 진행률 %는 프로젝트 간 우열을 비교하는 지표가 아니라 개별 공정 진행 상태입니다.\n**공정 분포:** 계약/SIF → 샘플/QC → 라이브러리 → 시퀀싱 → 데이터/리포트. 불명확한 단계는 별도로 표시합니다.\n**개별 프로젝트:** Feishu Base의 '진행 중 프로젝트' 보기에서 Quote Full Name, Progress Bar, Current Stage, Next Action을 검색·확인하세요. 낮은 %가 우선순위를 의미하지 않습니다.\n**운영:** Prepayment는 SIF 의무가 아닙니다. Final Report/Statement 완료는 Payment 대시보드로 이동하며, 결제 완료는 목록에서 숨깁니다. 지연 판정은 확정된 예정일·근거가 있는 경우에만 합니다."}),
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
    ("월별 Revenue · VAT 제외 · M KRW (K USD)","line",{
        "table_name":"Monthly Tax Invoice",
        "series":[{"field_name":"Net Revenue M KRW","rollup":"SUM"},
                  {"field_name":"Net Revenue K USD","rollup":"SUM"}],
        "group_by":[{"field_name":"Month","mode":"integrated",
                     "sort":{"type":"group","order":"asc"}}]}),
    ("월별 Revenue 표시 기준","text",{
        "text":"**월별 Revenue: Tax Invoice 수신 메일만 집계 · M KRW (K USD).** QQ 메일함의 공식 CSS \"Invoice Issued & Statement Confirmed\" 원본 메일에서 확인된 CMS Invoice(209126...)만 Invoice 번호로 중복 제거하고 VAT를 제외해 표시합니다. **수기 ERP Invoice·Feishu eTax·Payment·Pending·Forecast·Quote는 발행 검증 여부와 관계없이 합산하지 않습니다.** 백필 원본 메일 누락 후보는 제목·발신자·첨부파일명·금액 검증 전까지 합산하지 않습니다. 메일 수신월 기준 발행 안내 합계로서 회계상 매출 인식이나 입금 완료를 의미하지 않으며, 아직 전체 메일 수집 범위 검증 중입니다. KRW는 M, USD는 K 단위, 1 USD=1,500 KRW 보고용 환율로 동일 금액을 표시합니다."}),
    ("KOREA · Weekly Quote · 완료 4주 + 이번 주 (Count + 계산 K USD)","combo",live_quote_config()),
    ("Quote 계산 기준","text",{
        "text":"**Quote 금액은 추정치입니다.** 최근 완료된 4주(금~목)와 이번 주 진행 중 데이터를 함께 표시합니다. "
               "견적 금액은 QQ SFDC 3종 Report의 원본 해시·최신성을 확인한 뒤, "
               "각 Quotation의 공정별 Unit Price USD × Sample Quantity를 중복 없이 합산한 값입니다. "
               "**승인 목록은 모두 유지하고, 그래프 합계는 Active 견적만 반영합니다.** "
               "Quote Status=ACTIVE, Approved AND Active=YES, SFDC IsActive=1이고 "
               "Weekly Quote Review의 합산 제외 체크가 없는 건만 집계합니다. "
               "이 그래프는 Weekly Quote Review를 직접 조회하므로 수동 체크 변경은 GitHub Actions를 기다리지 않고 Feishu 차트에 반영됩니다. "
               "단, Feishu 자체 화면 캐시의 짧은 지연은 발생할 수 있으며 필요하면 새로고침하세요. "
               "Inactive·미확인·수동 제외는 승인 목록에 남지만 건수와 금액 합계에서 제외합니다. "
               "담당 Opportunity Owner가 본인이고, 기존 금액과 충돌하지 않는 견적만 계산합니다. "
               "이번 주 승인 0건은 원본 수집 누락을 의미하지 않습니다. 승인 여부와 최신 SFDC Report 수집 여부는 별개입니다. "
               "예외 건은 금액 합계에서 제외되며 0원이라고 해석하면 안 됩니다. "
               "M KRW는 표시용 환율 적용, K USD는 원본 USD를 천 단위로 표시합니다. "
               "Quote 예상금액은 Tax Invoice 매출(Revenue)이 아니며 VAT 제외 Revenue와 합산하면 안 됩니다."}),

]


# Stable reading order on Feishu's 12-column dashboard grid:
# provenance -> project KPIs -> production stages -> weekly quotes -> Revenue.
# Positions are dashboard presentation only; they never modify Base rows.
BLOCK_POSITIONS={
    "운영 안내":                           {"x":0,"y":0,"w":12,"h":7},
    "전체 프로젝트":                       {"x":0,"y":8,"w":3,"h":4},
    "진행률 확인 건수":                     {"x":3,"y":8,"w":3,"h":4},
    "진행률 미확인 건수":                   {"x":6,"y":8,"w":3,"h":4},
    "Prepayment 프로젝트":                 {"x":9,"y":8,"w":3,"h":4},
    "프로젝트 공정별 현황":                 {"x":0,"y":13,"w":8,"h":7},
    "SIF 상태":                            {"x":8,"y":13,"w":4,"h":7},
    "KOREA · Weekly Quote · 완료 4주 + 이번 주 (Count + 계산 K USD)":
                                            {"x":0,"y":21,"w":12,"h":7},
    "Quote 계산 기준":                     {"x":0,"y":29,"w":12,"h":4},
    "월별 Revenue · VAT 제외 · M KRW (K USD)":
                                            {"x":0,"y":34,"w":12,"h":7},
    "월별 Revenue 표시 기준":              {"x":0,"y":42,"w":12,"h":4},
}


def validate_dashboard_layout(blocks=BLOCKS,positions=BLOCK_POSITIONS):
    titles=[name for name,_,_ in blocks]
    if len(set(titles))!=len(titles) or set(titles)!=set(positions):
        raise RuntimeError("DASHBOARD_LAYOUT_TITLE_SET_MISMATCH")
    used=set()
    for title,position in positions.items():
        if set(position)!={"x","y","w","h"}:
            raise RuntimeError("DASHBOARD_LAYOUT_SHAPE_INVALID")
        x,y,w,h=[position[k] for k in ("x","y","w","h")]
        if not all(isinstance(v,int) and not isinstance(v,bool) for v in (x,y,w,h)):
            raise RuntimeError("DASHBOARD_LAYOUT_NON_INTEGER")
        if x<0 or y<0 or w<1 or h<1 or x+w>12:
            raise RuntimeError("DASHBOARD_LAYOUT_OUT_OF_GRID")
        for col in range(x,x+w):
            for row in range(y,y+h):
                p=(col,row)
                if p in used:raise RuntimeError("DASHBOARD_LAYOUT_OVERLAP")
                used.add(p)
    return True


def dashboard_layout_order(rows):
    """Return only known named blocks in visual top-to-bottom, left-to-right order."""
    found={}
    for r in collect(rows):
        name=r.get("name")
        if name not in BLOCK_POSITIONS:
            continue
        pos=r.get("position")
        if not isinstance(pos,dict) or not all(isinstance(pos.get(k),int)
                                                for k in ("x","y","w","h")):
            raise RuntimeError("DASHBOARD_LAYOUT_POSITION_UNVERIFIED")
        if name in found:raise RuntimeError("DASHBOARD_LAYOUT_DUPLICATE_NAME")
        found[name]=pos
    if set(found)!=set(BLOCK_POSITIONS):
        raise RuntimeError("DASHBOARD_LAYOUT_BLOCKS_MISSING")
    return tuple(sorted(found,key=lambda n:(found[n]["y"],found[n]["x"]))),found


def apply_dashboard_layout(dashboard_id,blocks):
    """Arrange existing blocks without deletes, duplicates, or customer table writes."""
    validate_dashboard_layout()
    current_order,current=dashboard_layout_order(blocks)
    expected=tuple(sorted(BLOCK_POSITIONS,
                          key=lambda n:(BLOCK_POSITIONS[n]["y"],BLOCK_POSITIONS[n]["x"])))
    if current_order==expected and all(current[n]==BLOCK_POSITIONS[n] for n in expected):
        print("FEISHU_DASHBOARD_LAYOUT_PASS blocks="+str(len(expected))+" changed=0")
        return
    # Stage into a temporary nonoverlapping tail: moving directly to occupied
    # coordinates may cause Feishu auto-arrange to shuffle unrelated blocks.
    indexes={}
    for row in collect(blocks):
        name=row.get("name")
        if name not in BLOCK_POSITIONS:continue
        block_id=row.get("block_id") or row.get("id")
        if not isinstance(block_id,str) or not block_id.startswith(("cht","blk")):
            raise RuntimeError("DASHBOARD_LAYOUT_BLOCK_ID_INVALID")
        indexes[name]=block_id
    for i,name in enumerate(expected):
        target=dict(BLOCK_POSITIONS[name])
        target["y"]=80+10*i
        cli("+dashboard-block-update","--base-token",BASE,
            "--dashboard-id",dashboard_id,"--block-id",indexes[name],
            "--position",json.dumps(target,separators=(",",":")))
    for name in expected:
        cli("+dashboard-block-update","--base-token",BASE,
            "--dashboard-id",dashboard_id,"--block-id",indexes[name],
            "--position",json.dumps(BLOCK_POSITIONS[name],separators=(",",":")))
    final=cli("+dashboard-block-list","--base-token",BASE,"--dashboard-id",dashboard_id)
    new_order,new=dashboard_layout_order(final)
    if new_order!=expected or any(new[name]!=BLOCK_POSITIONS[name] for name in expected):
        print("FEISHU_DASHBOARD_LAYOUT_READBACK_REVIEW blocks="+str(len(new_order)))
        raise RuntimeError("DASHBOARD_LAYOUT_READBACK_MISMATCH")
    print("FEISHU_DASHBOARD_LAYOUT_PASS blocks="+str(len(expected))+
          " changed="+str(len(expected))+" order=PROVENANCE_PROJECT_QUOTE_REVENUE")


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


def source_status_notice(rows,now):
    """Evidence-based source/as-of banner, independent of dashboard rerender time.

    A newly updated Feishu chart must never imply fresh Salesforce records.
    This is the trusted ingest audit's 3-report *source-received* time, not the
    most recent successful Action or Google Sheets ingest-check timestamp.
    """
    if now.tzinfo is None:
        raise ValueError("DASHBOARD_NOW_NEEDS_TIMEZONE")
    head=("Entity","Source Received KST","Ingest Checked KST","Rows",
          "Unique IDs","Duplicate IDs","Missing IDs","Content SHA256",
          "State","Source Kind")
    if not rows or tuple(rows[0][:10])!=head:
        raise ValueError("DASHBOARD_SOURCE_AUDIT_SCHEMA")
    by={}
    for row in rows[1:]:
        if row and row[0] in {"Leads","Opportunities","Quotation"}:
            if row[0] in by or len(row)<10:
                raise ValueError("DASHBOARD_SOURCE_AUDIT_DUPLICATE")
            by[row[0]]=row
    if set(by)!={"Leads","Opportunities","Quotation"}:
        raise ValueError("DASHBOARD_SOURCE_AUDIT_MISSING_ENTITY")
    sources={}
    for entity,row in by.items():
        if row[8] not in ("STAGED_NOT_PROMOTED","PRESERVED_NO_NEW_REPORT") or row[9]!="QQ IMAP":
            raise ValueError("DASHBOARD_SOURCE_AUDIT_UNTRUSTED")
        import re
        if not re.fullmatch(r"[0-9a-fA-F]{64}",row[7]):
            raise ValueError("DASHBOARD_SOURCE_AUDIT_BAD_HASH")
        try:
            received=dt.datetime.strptime(row[1],"%Y-%m-%d %H:%M:%S KST").replace(tzinfo=KST)
        except ValueError as exc:
            raise ValueError("DASHBOARD_SOURCE_AUDIT_TIMESTAMP") from exc
        if received>now.astimezone(KST)+dt.timedelta(minutes=10):
            raise ValueError("DASHBOARD_SOURCE_IN_FUTURE")
        sources[entity]=received
    age=max(0,int((now.astimezone(KST)-min(sources.values())).total_seconds()//60))
    # No guesses about whether weekend/holiday subscriptions are actually sent.
    status=("원본 수신 지연 · 신규 Report 반영 여부 미확인" if age>360
            else "최근 수신본 · 신규 발송 여부는 별도 검증")
    stamp=", ".join(entity+" "+sources[entity].strftime("%m/%d %H:%M")
                    for entity in ("Leads","Opportunities","Quotation"))
    block=("**SFDC Report 기준시각(KST):** "+stamp+
           "  \n**원본 수신 후 경과:** "+str(age//60)+"시간 "+str(age%60)+"분"+
           " · **"+status+"**"+
           "  \n**Feishu 화면 갱신:** "+now.astimezone(KST).strftime("%Y-%m-%d %H:%M KST")+
           ". 화면을 새로고침해도 새 SFDC 원본이 수집됐다는 뜻은 아닙니다.")
    return block,age


def read_sfdc_source_notice(now):
    raw=os.environ.get("GCP_SERVICE_ACCOUNT_JSON")
    if not raw:
        raise RuntimeError("DASHBOARD_AUDIT_READ_CREDENTIAL_MISSING")
    from google.oauth2 import service_account
    from google.auth.transport.requests import AuthorizedSession
    auth=service_account.Credentials.from_service_account_info(
        json.loads(raw),scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
    rg=urllib.parse.quote("'SFDC Email Ingest Audit'!A1:J10",safe="")
    url="https://sheets.googleapis.com/v4/spreadsheets/"+AUDIT_BOOK+"/values/"+rg
    result=AuthorizedSession(auth).get(url,timeout=45)
    result.raise_for_status()
    notice,age=source_status_notice(result.json().get("values",[]),now)
    print("FEISHU_DASHBOARD_SOURCE_PROVENANCE=PASS age_minutes="+str(age)+
          " stale="+str(age>360)+" evidence=SFDC_EMAIL_INGEST_AUDIT")
    return notice


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
    """Bounded Feishu rate-limit retry; all other errors fail closed."""
    for attempt in range(6):
        process=subprocess.run(["lark-cli","base",*args,"--as","bot","--format","json"],
                               text=True,capture_output=True,timeout=70)
        if process.returncode==0:
            output=process.stdout.strip()
            if not output:raise RuntimeError("FEISHU_CLI_EMPTY_"+str(args[0]))
            try:return json.loads(output)
            except json.JSONDecodeError:
                start=output.find("{")
                if start>=0:
                    try:return json.loads(output[start:])
                    except json.JSONDecodeError:pass
                raise RuntimeError("FEISHU_CLI_UNEXPECTED_FORMAT_"+str(args[0]))
        raw=(process.stderr or process.stdout or "").strip()
        # Feishu code 800004135 = method rate limit. Do not retry any other
        # backend failure (permission, invalid source field, unsupported API).
        if "800004135" in raw and attempt<5:
            delay=(2,4,8,16,28)[attempt]
            print("FEISHU_CLI_RATE_LIMIT_RETRY op="+str(args[0])+
                  " attempt="+str(attempt+1)+" backoff_s="+str(delay),flush=True)
            time.sleep(delay)
            continue
        compact=re.sub(r"https?://[^\\s]+","[URL]",raw)
        compact=re.sub(r"(?i)(?:bearer|token|secret|authorization)\\s*[:=]\\s*[^\\s,}]+",
                       "[REDACTED]",compact)
        compact=re.sub(r"[A-Za-z0-9_\\-]{21,}","[ID]",compact)
        compact=compact[-350:].replace("\\n"," ")
        print("FEISHU_CLI_BACKEND_ERROR op="+str(args[0])+
              " code="+str(process.returncode)+" diagnostic="+compact,flush=True)
        raise RuntimeError("FEISHU_CLI_COMMAND_FAILED_"+str(args[0]))
    raise RuntimeError("FEISHU_CLI_RETRY_EXHAUSTED_"+str(args[0]))


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


QUOTE_CHART_NAME="KOREA · Weekly Quote · 완료 4주 + 이번 주 (Count + 계산 K USD)"
LEGACY_QUOTE_ALIASES=(
    "KOREA · Weekly Quote · 최근 4주 (Count + 계산 K USD)",
    "KOREA · Weekly Quote · 최근 4주 (승인 건수 + 계산액 K USD)",
    "KOREA · Quote Count / Value (K USD)",
    "Weekly Quote · 건수 + 검증금액 K USD",
)
# Remove only known obsolete dashboard widgets, after verifying the kept chart.
# Never delete source Base tables, views, fields, or quote records.
LEGACY_REDUNDANT_QUOTE_WIDGETS={
    "KOREA · Weekly Quote · 최근 4주 (Count + K USD)":"combo",

    "Weekly 승인 Quote":"column",
    "KOREA · Quote Count / Value (K USD)":"combo",
    "Weekly Quote · 건수 + 검증금액 K USD":"combo",
    "KOREA · Weekly Quote · 최근 4주 (승인 건수 + 계산액 K USD)":"combo",
    "KOREA · Quote Count / Value (M KRW)":"combo",
    "KOREA · Quote Count / Value (KRW)":"combo",
    "Weekly Quote · 건수 + 검증금액 KRW":"combo",
    "Quote 금액 검증 기준":"text",
}
LEGACY_REVENUE_NAMES=(
    "월별 Revenue · VAT 제외 (M KRW)",
    "월별 Revenue · VAT 제외",
)
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
    if mode=="apply":
        # Chart reads the editable Quote Review directly. Validate before any UI writes.
        live_quote_preflight()
        # Clear separation: chart refresh time is not Salesforce data time.
        BLOCKS[0][2]["text"]+="\n\n"+read_sfdc_source_notice(dt.datetime.now(KST))
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
        if kind=="combo" and name==QUOTE_CHART_NAME:
            chart=locate_chart(existing,name)
            if not chart:
                for alias in LEGACY_QUOTE_ALIASES:
                    chart=locate_chart(existing,alias)
                    if chart:break
            if chart:
                # Update the real existing combo instead of creating a duplicate
                # and restrict the data to four completed weeks plus this week.
                cli("+dashboard-block-update","--base-token",BASE,
                    "--dashboard-id",dashboard_id,"--block-id",chart,
                    "--name",name,
                    "--data-config",json.dumps(config,ensure_ascii=False,separators=(",",":")))
                updated+=1
                print("FEISHU_QUOTE_COMBO_UPDATED type=combo window=RECENT_4_PLUS_CURRENT")
                continue
        if name=="월별 Revenue · VAT 제외 · M KRW (K USD)":
            old=locate_chart(existing,name)
            if not old:
                for old_name in LEGACY_REVENUE_NAMES:
                    old=locate_chart(existing,old_name)
                    if old:
                        break
            if old:
                cli("+dashboard-block-update","--base-token",BASE,
                    "--dashboard-id",dashboard_id,"--block-id",old,
                    "--name",name,
                    "--data-config",json.dumps(config,ensure_ascii=False,
                                               separators=(",",":")))
                updated+=1
                print("FEISHU_MONTHLY_REVENUE_DUAL_CURRENCY_UPDATED=M_KRW,K_USD")
                continue
        if name in names:
            info=locate_chart(existing,name)
            if (name in {"Quote 금액 검증 기준","Quote 계산 기준","운영 안내",QUOTE_CHART_NAME} or
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
    final=cli("+dashboard-block-list","--base-token",BASE,"--dashboard-id",dashboard_id)
    if not legacy_dashboard_block(final,QUOTE_CHART_NAME,"combo"):
        raise RuntimeError("WEEKLY_QUOTE_CANONICAL_CHART_NOT_VERIFIED")
    # Do not remove old widgets until a single valid new chart is confirmed.
    for old_name,old_type in LEGACY_REDUNDANT_QUOTE_WIDGETS.items():
        obsolete=legacy_dashboard_block(final,old_name,old_type)
        if obsolete:
            delete_dashboard_block(dashboard_id,obsolete)
            deleted+=1
            print("FEISHU_WEEKLY_QUOTE_REDUNDANT_BLOCK_REMOVED="+old_name)
            final=cli("+dashboard-block-list","--base-token",BASE,
                      "--dashboard-id",dashboard_id)
    if legacy_dashboard_block(final,LEGACY_PROGRESS_RANK):
        raise RuntimeError("PROGRESS_RANK_STILL_EXISTS")
    if legacy_dashboard_block(final,LEGACY_RAW_STAGE_CHART):
        raise RuntimeError("LEGACY_STAGE_GRAPH_STILL_EXISTS")
    for old_name,old_type in LEGACY_REDUNDANT_QUOTE_WIDGETS.items():
        if legacy_dashboard_block(final,old_name,old_type):
            raise RuntimeError("REDUNDANT_QUOTE_BLOCK_STILL_EXISTS")
    if sum(1 for row in collect(final)
           if row.get("name")==QUOTE_CHART_NAME and
           (row.get("block_id") or row.get("id")) and row.get("type")=="combo")!=1:
        raise RuntimeError("QUOTE_SINGLE_COMBO_NOT_VERIFIED")
    found={row.get("name") for row in collect(final) if isinstance(row.get("name"),str)}
    missing={n for n,_,_ in BLOCKS}-found
    if missing:raise RuntimeError("FEISHU_NATIVE_COMPONENTS_MISSING_"+str(len(missing)))
    apply_dashboard_layout(dashboard_id,final)
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
