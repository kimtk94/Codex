#!/usr/bin/env python3
"""Feishu Base native sales home: evidence-safe links to source-backed views.

This is an internal Feishu Base page, not a separate deployed web application.
Only the dedicated 00 영업 홈 table is written. Other tables are inspected via
read-only API metadata and one-row presence checks. No client payload in logs.
"""
import collections
import datetime as dt
import json
import os
import sys
import urllib.parse
from zoneinfo import ZoneInfo

from qq_mail_ingest import SafeError, api, auth, get_fields, list_all, plain_field
from setup_sales_web import BASE_URL, EXPECTED_BASE, list_views

HOME = "00 영업 홈"
KST = ZoneInfo("Asia/Seoul")
FIELDS = ("Menu Key", "그룹", "화면", "바로가기 URL", "데이터 상태",
          "업무 내용", "원본 기준", "표시", "갱신 시각")

# All are known Feishu Base grid views; not external Vercel or speculative URLs.
# The navigation distinguishes native QQ mail from legacy KPI/CRM source snapshots.
MENUS = (
    ("MONTHLY_TREND","00 대시보드","월별 Revenue 추이","02 매출 견적 추이",
     "월별 Revenue 추이","Feishu Monthly Tax Invoice","연도·월별 VAT 제외 매출과 VAT 포함 Invoice 비교용 데이터"),
    ("WEEKLY_TREND","00 대시보드","Weekly Quote 추이","02 매출 견적 추이",
     "Weekly Quote 추이","Feishu Weekly Quote KPI","주별 Quote 승인 건수와 검증 금액 추이 데이터"),
    ("DASHBOARD","00 대시보드","핵심 KPI 카드","01 핵심 KPI 대시보드",
     "01 KPI 카드","Feishu 원본 집계","메일·고객·프로젝트·매출·견적 핵심 지표"),
    ("MAIL_CURRENT","01 메일","최근 30일 메일","QQ Mail Intake",
     "현재 메일 · 최근 30일","QQ 메일 · Feishu 원본","현재 수신/발신을 날짜 기준으로 확인"),
    ("MAIL_HISTORY","01 메일","2026년 과거 메일","QQ Mail Intake",
     "과거 메일 · 2026","QQ 메일 · Feishu 원본","과거 메일·진행 중 프로젝트 이력 검색"),
    ("MAIL_INBOUND","01 메일","수신 메일","QQ Mail Intake",
     "수신 메일","QQ 메일 · Feishu 원본","실제 수신함에서 저장된 메일"),
    ("MAIL_OUTBOUND","01 메일","발신 메일","QQ Mail Intake",
     "발신 메일","QQ 메일 · Feishu 원본","답변 여부 검증용 발신 기록"),
    ("CUSTOMER_REVIEW","02 고객","고객 메일 검토","Mail Identity 2026",
     "고객 메일 검토","QQ 메일 + SFDC 참조","미응답 확정 아님; 회신 이력 확인 필요"),
    ("CONTACT_EXACT","02 고객","고객 이메일 연결","Mail Identity 2026",
     "고객 이메일 확인","QQ 메일 + SFDC 참조","Contact 이메일 정확 일치만 연결"),
    ("CONTACT_FOLLOWUP","02 고객","기관·연락처 연결 검토","Mail Link Review 2026",
     "메일 추가연결 검토","QQ 메일 + SFDC 참조","본문·도메인 근거는 확인 후보만 표시"),
    ("INTERNAL_EXCLUDE","02 고객","내부 메일 제외","Mail Identity 2026",
     "내부 메일 제외","QQ 메일 · Feishu 분석","Novogene 내부 메일을 고객 업무에서 제외"),
    ("PROJECT_MAIL","03 프로젝트","프로젝트 관련 메일","Mail Identity 2026",
     "프로젝트별 메일","QQ 메일 + 프로젝트 참조","AMEA/H 프로젝트 ID 정확 매칭"),
    ("CSS_NOTICES","03 프로젝트","CSS 진행 알림","Mail Identity 2026",
     "CSS 진행 안내","QQ 메일 · Feishu 분석","CSS 단계별 알림, 고객 회신 대상 아님"),
    ("PROJECT_PROGRESS","03 프로젝트","프로젝트별 진행률 · Quote Full Name","Project Progress Board",
     "프로젝트별 진행률","원본 CSS·SFDC·Prepayment·SIF","프로젝트별 0~100% 진행 바와 전체 Quote 이름, SIF/PO 후속 업무"),
    ("X_MY_PROJECTS","03 프로젝트","내 X 하위 프로젝트","X Project Registry",
     "내 X 프로젝트","Feishu Online + BI Lifecycle","본인 담당 X 상태·남은 TAT·Invoice와 SAM 연결"),
    ("X_ALL_PROJECTS","03 프로젝트","전체 X 하위 프로젝트","X Project Registry",
     "전체 X 프로젝트","Feishu Online","X별 실제 상태, AMEA 연결 불명확은 검토 분리"),
    ("X_URGENT","03 프로젝트","내 X 즉시 확인","X Project Registry",
     "내 즉시 확인 X","Feishu Online 상태·잔여 TAT","Abnormal 또는 잔여 TAT 음수 등 근거 기반 우선 검토"),
    ("X_FOLLOWUP","03 프로젝트","내 X 후속 확인","X Project Registry",
     "내 후속 확인 X","Feishu 상태 + 상세 진행 기록","재제출·추가 시퀀싱·회신 대기 등 현재 상태 확인"),
    ("X_NOTE_AGING","03 프로젝트","내 X 오래된 날짜 메모","X Project Registry",
     "내 오래된 메모 30일+","Feishu Progression Details","메모 속 날짜 30일 경과; 실제 마지막 수정일·정체 여부는 별도 확인"),
    ("X_SAMPLE_LINK","03 프로젝트","AMEA·H·X·SAM 연결","AMEA H X SAM Link",
     "X-SAM 확정 연결","CSS / Feishu / BI Lifecycle","X가 유일하게 확인된 시료만 프로젝트에 부착"),
    ("X_SAMPLE_REVIEW","03 프로젝트","공유 SAM 검토","AMEA H X SAM Link",
     "공유 SAM 검토","CSS Timeline","다른 AMEA에도 나타난 SAM은 자동 확정 금지"),
    ("PAYMENT_FOLLOWUP","03 프로젝트","내 결제 대기 프로젝트","Project Progress Board",
     "완료 · 결제 관리","Feishu Payment Receipt / Outstanding","본인 담당이며 작업 완료된 프로젝트의 Invoice·잔액 확인"),
    ("X_MY_INVOICE","04 지표","내 X별 Invoice","X Invoice Ledger",
     "내 X Invoice","최신 Feishu eTax / Outstanding","CMS·X·AMEA 정확 연결, 결제 완료 단독 확정 금지"),
    ("SIF","03 프로젝트","SIF 진행 현황","Project SIF Monitor",
     "프로젝트 진행 · SIF","기존 프로젝트·SIF 검증 시트","SIF 제출/승인 증빙 기준"),
    ("SIF_EVIDENCE","03 프로젝트","SIF 승인 확인 필요","SIF Evidence Tracker",
     "SIF 승인 확인 필요","공식 CSS·CRM 원본 메일","SIF 제출·접수·승인 통지와 미확인 상태, 실제 문서 확인 별도"),
    ("PO_REQUIRED","03 프로젝트","Contract 생성 후 PO 수령 필요","Contract PO Tracker",
     "PO 수령 필요","원본 CSS·CRM Contract 통지","Contract 통지 이후 PO 접수 확인·요청 목록"),
    ("INVOICE","04 지표","월별 Tax Invoice","Monthly Tax Invoice",
     "월별 Tax Invoice","기존 매출·Invoice 검증 시트","VAT 포함 Invoice와 VAT 제외 Revenue 구분"),
    ("QUOTE","04 지표","Weekly Quote","Weekly Quote KPI",
     "매주 Quote 건수 · 금액","기존 SFDC Quote 검증 시트","주간 승인 건수·확인된 금액만 표시"),
    ("ACCOUNTS","05 SFDC 준비","기관별 고객","Accounts",
     "기관별 고객","새 Feishu Base 운영 테이블","빈 테이블이면 데이터 연결 준비로 표시"),
    ("CONTACTS","05 SFDC 준비","한글 고객 검색","Contacts",
     "한글 고객 검색","새 Feishu Base 운영 테이블","빈 테이블이면 데이터 연결 준비로 표시"),
    ("OPPOS","05 SFDC 준비","영업기회","Opportunities",
     "영업 기회","새 Feishu Base 운영 테이블","SFDC Oppo 자동 생성과는 별개"),
    ("QUOTES","05 SFDC 준비","견적 관리","Quotes",
     "견적 관리","새 Feishu Base 운영 테이블","SFDC Quote 자동 생성과는 별개"),
    ("PROJECTS","05 SFDC 준비","프로젝트 현황","Projects",
     "프로젝트 현황","새 Feishu Base 운영 테이블","QQ Mail Identity / SIF Monitor와는 별도"),
    ("REVENUE","05 SFDC 준비","월별 매출","Revenue",
     "월별 매출","새 Feishu Base 운영 테이블","검증되지 않은 Revenue 값을 추가하지 않음"),
)


# Ordered by daily usage, not by underlying table creation order.
CURATED_ORDER=(
    "DASHBOARD", "WEEKLY_TREND", "MONTHLY_TREND",
    "MAIL_CURRENT", "CUSTOMER_REVIEW",
    "X_MY_PROJECTS", "X_URGENT", "X_FOLLOWUP",
    "SIF_EVIDENCE", "PO_REQUIRED",
    "PAYMENT_FOLLOWUP", "X_MY_INVOICE",
)
PINNED_KEYS=frozenset(CURATED_ORDER)
# Official Feishu single-select option color indices: red=0, orange=1,
# green=10, blue=20. Business urgency is expressed only for explicit urgent views.
MENU_COLORS=(
    ("핵심 KPI",20),
    ("고객·메일",20),
    ("프로젝트",20),
    ("즉시 확인",0),
    ("확인·증빙",1),
    ("매출·결제",10),
    ("관리용",20),
)
COLOR_KEY_MAP={
    **dict.fromkeys(("DASHBOARD","WEEKLY_TREND","MONTHLY_TREND"),"핵심 KPI"),
    **dict.fromkeys(("MAIL_CURRENT","CUSTOMER_REVIEW"),"고객·메일"),
    **dict.fromkeys(("X_MY_PROJECTS","X_FOLLOWUP"),"프로젝트"),
    "X_URGENT":"즉시 확인",
    **dict.fromkeys(("SIF_EVIDENCE","PO_REQUIRED"),"확인·증빙"),
    **dict.fromkeys(("PAYMENT_FOLLOWUP","X_MY_INVOICE"),"매출·결제"),
}
MENU_EXTRA_FIELDS={
    "표시순서":{"field_name":"표시순서","type":2},
    "메뉴 구분":{"field_name":"메뉴 구분","type":3,
               "property":{"options":[{"name":n,"color":c} for n,c in MENU_COLORS]}},
}

def presentation(key,title,source_index):
    if key in PINNED_KEYS:
        rank=CURATED_ORDER.index(key)+1
        return rank, f"{rank:02d} · {title}", COLOR_KEY_MAP[key]
    return 100+source_index, title, "관리용"
CURATED_VIEW="업무용 메뉴"
CURATED_DISPLAY="주요"
ARCHIVE_DISPLAY="관리용"



def target_path(root, table_id):
    return root + "/tables/" + urllib.parse.quote(table_id, safe="")


def table_map(token, root):
    byname = {}
    for entry in list_all(root + "/tables", token, "portal_list_tables"):
        name, tid = entry.get("name"), entry.get("table_id")
        if not name or not tid or name in byname:
            raise SafeError("PORTAL_DUPLICATE_OR_EMPTY_TABLE")
        byname[name] = tid
    return byname


def source_rows(token,root,tables,now):
    output = []
    cached = {}
    status = collections.Counter()
    for source_index, (key, group, title, table_name, view_name, source, instruction) in enumerate(MENUS, 1):
        rank, display, color = presentation(key,title,source_index)
        tid = tables.get(table_name)
        url = ""
        state = "SOURCE_TABLE_NOT_READY"
        if tid:
            if table_name not in cached:
                path = target_path(root, tid)
                views = list_views(token, path)
                # page_size=1 checks for data without exposing client content.
                check = api("GET", path + "/records?page_size=1", token,
                            action="portal_check_data")
                has_rows = bool(check.get("items"))
                cached[table_name] = (views,has_rows)
            views,has_rows = cached[table_name]
            vid = views.get(view_name)
            if key == "DASHBOARD" and not vid:
                vid = views.get("02 KPI 상세")  # Feishu gallery API may be unavailable.
            if vid:
                url = BASE_URL + "?table=" + urllib.parse.quote(tid,safe="") + "&view=" + urllib.parse.quote(vid,safe="")
                state = "DATA_PRESENT" if has_rows else "SOURCE_EMPTY"
            else:
                state = "VIEW_NOT_READY"
        status[state] += 1
        output.append({
            "Menu Key":key, "그룹":group, "화면":display,
            "표시순서":rank, "메뉴 구분":color,
            "바로가기 URL":url, "데이터 상태":state,
            "업무 내용":instruction, "원본 기준":source,
            "표시":CURATED_DISPLAY if key in PINNED_KEYS else ARCHIVE_DISPLAY,
        })
    for state,count in sorted(status.items()):
        print("PORTAL_ROUTE_"+state+"="+str(count))
    return output


def ensure_home(token,root,tables):
    tid = tables.get(HOME)
    if tid is None:
        api("POST",root+"/tables",token,data={"table":{
            "name":HOME,"default_view_name":"바로가기",
            "fields":[{"field_name":name,"type":1} for name in FIELDS]
                     + list(MENU_EXTRA_FIELDS.values()),
        }},action="portal_create_home")
        tid = table_map(token,root).get(HOME)
    if not tid:
        raise SafeError("PORTAL_HOME_CREATE_FAILED")
    path = target_path(root,tid)
    required={name:{"field_name":name,"type":1} for name in FIELDS}
    required.update(MENU_EXTRA_FIELDS)
    fields={r.get("field_name"):r.get("type") for r in get_fields(token,path)}
    if any(name in fields and fields[name]!=spec["type"]
           for name,spec in required.items()):
        raise SafeError("PORTAL_HOME_FIELD_CONFLICT")
    for name,spec in required.items():
        if name not in fields:
            api("POST",path+"/fields",token,data=spec,action="portal_add_field")
    actual=get_fields(token,path)
    final={r.get("field_name"):r for r in actual}
    if any(final.get(name,{}).get("type")!=spec["type"]
           for name,spec in required.items()):
        raise SafeError("PORTAL_HOME_SCHEMA_READBACK_FAILED")
    tag_field=final["메뉴 구분"]
    existing_options=(tag_field.get("property") or {}).get("options") or []
    current={option.get("name"):option.get("color") for option in existing_options}
    if any(current.get(n)!=c for n,c in MENU_COLORS):
        raise SafeError("PORTAL_MENU_COLOR_OPTIONS_MISMATCH")
    return tid,path


def as_display(value):
    if isinstance(value,(int,float)) and not isinstance(value,bool):
        return str(int(value)) if value==int(value) else str(value)
    return plain_field(value).strip()


def same(original,expected):
    return all(as_display(original.get(k))==str(v).strip()
               for k,v in expected.items())


def update_home(token,path,desired):
    existing = list_all(path+"/records",token,"portal_existing")
    indexed={}
    for record in existing:
        key=plain_field((record.get("fields") or {}).get("Menu Key")).strip()
        if not key:
            continue
        if key in indexed:
            raise SafeError("PORTAL_DUPLICATE_MENU_KEY")
        indexed[key]=record
    creates=[]; updates=[]; unchanged=0
    now=dt.datetime.now(KST).strftime("%Y-%m-%d %H:%M KST")
    for item in desired:
        old=indexed.get(item["Menu Key"])
        if old and same(old.get("fields") or {},item):
            unchanged+=1
            continue
        row={**item,"갱신 시각":now}
        if old:
            updates.append({"record_id":old["record_id"],"fields":row})
        else:
            creates.append({"fields":row})
    for operation,records in (("batch_create",creates),("batch_update",updates)):
        for start in range(0,len(records),25):
            chunk=records[start:start+25]
            result=api("POST",path+"/records/"+operation,token,data={"records":chunk},
                       action="portal_"+operation)
            if len(result.get("records") or [])!=len(chunk):
                raise SafeError("PORTAL_UPSERT_NOT_CONFIRMED")
    if creates or updates:
        check=list_all(path+"/records",token,"portal_readback")
        found={}
        for r in check:
            key=plain_field((r.get("fields") or {}).get("Menu Key")).strip()
            if key in found:
                raise SafeError("PORTAL_READBACK_DUPLICATE_MENU")
            found[key]=r.get("fields") or {}
        for item in desired:
            if item["Menu Key"] not in found or not same(found[item["Menu Key"]],item):
                raise SafeError("PORTAL_READBACK_MISMATCH")
    print("PORTAL_APPLY_PASS created="+str(len(creates))+" updated="+str(len(updates))+
          " unchanged="+str(unchanged)+" routes="+str(len(desired))+
          " source_table_record_writes=0")


def ensure_curated_view(token,path):
    """A safe filtered home view; all raw Base tables remain accessible."""
    from setup_sales_web import resolve_view,get_view,field_map
    vid,_=resolve_view(token,path,CURATED_VIEW,True)
    fid=field_map(token,path).get("표시")
    if not fid:raise SafeError("PORTAL_VISIBILITY_FIELD_MISSING")
    target_path=path+"/views/"+urllib.parse.quote(vid,safe="")
    def valid():
        v=get_view(token,path,vid)
        info=((v.get("property") or {}).get("filter_info") or {})
        conditions=info.get("conditions") or []
        if v.get("view_name")!=CURATED_VIEW or info.get("conjunction")!="and":
            return False
        if len(conditions)!=1:return False
        condition=conditions[0]
        try:values=json.loads(condition.get("value") or "null")
        except (TypeError,ValueError):return False
        return (condition.get("field_id")==fid and condition.get("operator")=="is"
                and values==[CURATED_DISPLAY])
    if not valid():
        api("PATCH",target_path,token,data={
            "view_name":CURATED_VIEW,
            "property":{"filter_info":{"conjunction":"and",
                "conditions":[{"field_id":fid,"operator":"is",
                               "value":json.dumps([CURATED_DISPLAY],
                                   ensure_ascii=False)}]}}
        },action="portal_curated_view_filter")
        if not valid():raise SafeError("PORTAL_CURATED_FILTER_READBACK_FAILED")
    return vid


def main():
    if os.environ.get("FEISHU_BASE_APP_TOKEN") != EXPECTED_BASE:
        raise SafeError("PORTAL_REFUSE_NON_SALES_BASE")
    mode=os.environ.get("FEISHU_PORTAL_MODE","plan")
    if mode not in ("plan","apply"):
        raise SafeError("PORTAL_UNKNOWN_MODE")
    token,root=auth()
    tables=table_map(token,root)
    desired=source_rows(token,root,tables,dt.datetime.now(KST))
    if mode=="plan":
        print("PORTAL_PLAN_PASS routes="+str(len(desired))+" writes=0")
        return
    tid,path=ensure_home(token,root,tables)
    update_home(token,path,desired)
    curated_id=ensure_curated_view(token,path)
    print("PORTAL_CURATED_VIEW_PASS shown="+str(len(PINNED_KEYS))+
          " hidden_from_curated="+str(len(desired)-len(PINNED_KEYS))+
          " records_deleted=0 source_tables_removed=0")
    print("PORTAL_CURATED_HOME_URL="+BASE_URL+"?table="+tid+"&view="+curated_id)
    views=list_views(token,path)
    if not views:
        raise SafeError("PORTAL_HOME_NO_VIEWS")
    view = views.get("바로가기") or next(iter(views.values()))
    print("PORTAL_HOME_URL="+BASE_URL+"?table="+tid+"&view="+view)


if __name__=="__main__":
    try: main()
    except Exception as ex:
        reason=str(ex) if isinstance(ex,SafeError) else type(ex).__name__
        print("PORTAL_FAILED:"+reason,file=sys.stderr)
        sys.exit(1)
