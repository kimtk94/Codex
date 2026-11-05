#!/usr/bin/env python3
"""Feishu Base native sales home: evidence-safe links to source-backed views.

This is an internal Feishu Base page, not a separate deployed web application.
Only the dedicated 00 영업 홈 table is written. Other tables are inspected via
read-only API metadata and one-row presence checks. No client payload in logs.
"""
import collections
import datetime as dt
import os
import sys
import urllib.parse
from zoneinfo import ZoneInfo

from qq_mail_ingest import SafeError, api, auth, get_fields, list_all, plain_field
from setup_sales_web import BASE_URL, EXPECTED_BASE, list_views

HOME = "00 영업 홈"
KST = ZoneInfo("Asia/Seoul")
FIELDS = ("Menu Key", "그룹", "화면", "바로가기 URL", "데이터 상태",
          "업무 내용", "원본 기준", "갱신 시각")

# All are known Feishu Base grid views; not external Vercel or speculative URLs.
# The navigation distinguishes native QQ mail from legacy KPI/CRM source snapshots.
MENUS = (
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
    ("SIF","03 프로젝트","SIF 진행 현황","Project SIF Monitor",
     "SIF 전체 현황","기존 프로젝트·SIF 검증 시트","SIF 제출/승인 증빙 기준"),
    ("INVOICE","04 지표","월별 Tax Invoice","Monthly Tax Invoice",
     "월별 Tax Invoice","기존 매출·Invoice 검증 시트","VAT 포함 Invoice와 VAT 제외 Revenue 구분"),
    ("QUOTE","04 지표","Weekly Quote","Weekly Quote KPI",
     "Weekly Quote 현황","기존 SFDC Quote 검증 시트","주간 승인 건수·확인된 금액만 표시"),
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
    for key, group, title, table_name, view_name, source, instruction in MENUS:
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
            if vid:
                url = BASE_URL + "?table=" + urllib.parse.quote(tid,safe="") + "&view=" + urllib.parse.quote(vid,safe="")
                state = "DATA_PRESENT" if has_rows else "SOURCE_EMPTY"
            else:
                state = "VIEW_NOT_READY"
        status[state] += 1
        output.append({
            "Menu Key":key, "그룹":group, "화면":title,
            "바로가기 URL":url, "데이터 상태":state,
            "업무 내용":instruction, "원본 기준":source,
        })
    for state,count in sorted(status.items()):
        print("PORTAL_ROUTE_"+state+"="+str(count))
    return output


def ensure_home(token,root,tables):
    tid = tables.get(HOME)
    if tid is None:
        api("POST",root+"/tables",token,data={"table":{
            "name":HOME,"default_view_name":"바로가기",
            "fields":[{"field_name":name,"type":1} for name in FIELDS],
        }},action="portal_create_home")
        tid = table_map(token,root).get(HOME)
    if not tid:
        raise SafeError("PORTAL_HOME_CREATE_FAILED")
    path = target_path(root,tid)
    fields = {r.get("field_name"):r.get("type") for r in get_fields(token,path)}
    if any(name in fields and fields[name] != 1 for name in FIELDS):
        raise SafeError("PORTAL_HOME_FIELD_CONFLICT")
    for name in FIELDS:
        if name not in fields:
            api("POST",path+"/fields",token,
                data={"field_name":name,"type":1},action="portal_add_field")
    final={r.get("field_name"):r.get("type") for r in get_fields(token,path)}
    if any(final.get(name)!=1 for name in FIELDS):
        raise SafeError("PORTAL_HOME_SCHEMA_READBACK_FAILED")
    return tid,path


def same(original,expected):
    return all(plain_field(original.get(k)).strip()==str(v).strip()
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
