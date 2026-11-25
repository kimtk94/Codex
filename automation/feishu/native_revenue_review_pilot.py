#!/usr/bin/env python3
"""One-time, reviewed Feishu Revenue member pilot. Default is read-only.

A dedicated frozen October-November 2026 analysis snapshot, not the official chart
and not a recurring writer. Create only when both named targets are absent
and the exact reviewed source digest and original monthly totals still match.
An explicit one-time recovery can populate the independently verified empty
table from run 45605295885 with the same frozen snapshot.
Never update/delete existing tables, rows, views, or dashboard blocks.
"""
import argparse
from collections import Counter
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
import re
import sys
import urllib.parse

from dashboard_drilldown_plan import (
    DrilldownError, EXCLUDE, INCLUSION, REVIEW, REVIEW_FIELDS, SOURCE_FIELDS,
    USER_FIELDS, member_totals, plan, read_sources, review_chart_config,
    text, validate_review_member, won,
)
from monthly_revenue_canonical import evidence_rows

BASE = "IpMkbUD0vaFqtYs93a3csXtdn1b"
ROOT = "/open-apis/bitable/v1/apps/" + BASE
OFFICIAL = "Monthly Tax Invoice"
OFFICIAL_ID = "tblXLFQWiEK9REZL"
TITLE = "Revenue 집계 검토 · 2026-10~11 스냅샷"
LEGACY_TITLE = "Revenue 집계 검토 · 2026-10 스냅샷"
# Reviewed source snapshot 2026-11-25. A count change requires a new
# review, not a silent expansion of the approved frozen cohort.
EXPECTED_COUNTS = {"2026-10":48,"2026-11":42}
MONTHS = tuple(EXPECTED_COUNTS)
EXPECTED_COUNT = sum(EXPECTED_COUNTS.values())
DEFAULT_VIEW = "01 전체 집계 원본"
RECOVERY_TABLE = "tblvAmPu7fpHHta1"
RECOVERY_DIGEST = "7d0808b8d0880564164d5c59f5e4bdceab860fdcadb1624c3f89cfd0f55608de"
# These are the only permissible business API write paths. The new table ID
# is established by the create response + unique catalog readback.
FIELD_SPECS = [{"field_name":name,"type":kind} for name,kind in REVIEW_FIELDS.items()]
OFFICIAL_METRICS = ("Invoice Count","Tax Invoice KRW Incl VAT","Net Revenue KRW Ex VAT",
                    "Net Revenue M KRW","Net Revenue K USD")


def fail(code):
    raise DrilldownError("REVENUE_PILOT_"+code)


def canonical_json(obj):
    return json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(",",":"))


def sha(obj):
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()


def snapshot(source):
    summary,ready=plan(source)
    ordered=[]
    official={}
    stamps={}
    for month,count in EXPECTED_COUNTS.items():
        rows=ready.get(month,[])
        if summary["months"].get(month,{}).get("state")!="VERIFIED_PUBLISHED_MONTH_MEMBERS":
            fail("SOURCE_MONTH_NOT_READY:"+month)
        if len(rows)!=count:
            fail("EXPECTED_MEMBER_COUNT_CHANGED:"+month)
        if any(USER_FIELDS & r.keys() or set(r)!=SOURCE_FIELDS or r["Month"]!=month for r in rows):
            fail("MEMBER_SCHEMA_OR_SCOPE")
        authoritative=evidence_rows({
            name:[r for r in source[name] if text(r,"Month")==month]
            for name in ("BI Revenue Net VAT Monthly","BI Revenue Lifecycle Monthly","Revenue Source Authority")})
        if len(authoritative)!=1 or authoritative[0]["Month"]!=month:
            fail("AUTHORITY_CHANGED:"+month)
        totals=member_totals(rows)["original"]
        official[month]=authoritative[0]
        if (totals["count"],totals["gross_known_krw"],totals["net_known_krw"])!=(
                official[month]["Invoice Count"],official[month]["Tax Invoice KRW Incl VAT"],
                official[month]["Net Revenue KRW Ex VAT"]):
            fail("MEMBER_AUTHORITY_MISMATCH:"+month)
        month_stamps={r["Verified At KST"] for r in rows}
        if len(month_stamps)!=1:
            fail("MEMBER_SNAPSHOT_MISMATCH:"+month)
        stamps[month]=next(iter(month_stamps))
        ordered.extend(rows)
    ordered.sort(key=lambda row:(row["Month"],row["Source Key"]))
    if len({validate_review_member(row) for row in ordered})!=EXPECTED_COUNT:
        fail("MEMBER_KEY_NOT_UNIQUE")
    digest=sha({"months":list(MONTHS),"members":ordered,
                "official":{m:{k:official[m][k] for k in OFFICIAL_METRICS} for m in MONTHS}})
    return {"rows":ordered,"digest":digest,"official":official,"stamps":stamps}


def plain(value):
    if value is None:return ""
    if isinstance(value,str):return value.strip()
    if isinstance(value,(int,float)) and not isinstance(value,bool):return str(value)
    if isinstance(value,list):
        if any(not isinstance(x,dict) or not isinstance(x.get("text"),str) for x in value):
            fail("TEXT_CELL_FORMAT")
        return "".join(x["text"] for x in value).strip()
    fail("TEXT_CELL_FORMAT")


def decimal_value(value):
    try:
        d=Decimal(plain(value).replace(",",""))
    except (InvalidOperation,ValueError):
        fail("OFFICIAL_NUMERIC_FORMAT")
    if not d.is_finite() or d<0:
        fail("OFFICIAL_NUMERIC_FORMAT")
    return d


def verify_official(records,expected):
    if set(expected)!=set(MONTHS):
        fail("OFFICIAL_SCOPE_MISMATCH")
    for month in MONTHS:
        hits=[rec for rec in records if plain(rec.get("fields",{}).get("Source Key"))=="INVOICE:"+month]
        if len(hits)!=1:
            fail("OFFICIAL_MONTH_MISSING_OR_DUPLICATE:"+month)
        row=hits[0].get("fields",{})
        if plain(row.get("Month"))!=month or not hits[0].get("record_id"):
            fail("OFFICIAL_MONTH_IDENTITY:"+month)
        for key in OFFICIAL_METRICS:
            if decimal_value(row.get(key))!=Decimal(str(expected[month][key])):
                fail("OFFICIAL_CHART_TOTAL_MISMATCH:"+month)


def check_schema(fields):
    observed={}
    ids=set()
    for f in fields:
        n,i=f.get("field_name"),f.get("field_id")
        if not isinstance(n,str) or n in observed or not isinstance(i,str) or not i or i in ids:
            fail("REVIEW_FIELD_ID_OR_NAME")
        observed[n]=f;ids.add(i)
    if set(observed)!=set(REVIEW_FIELDS) or any(observed[k].get("type")!=v for k,v in REVIEW_FIELDS.items()):
        fail("REVIEW_FIELD_SCHEMA")
    primaries=[n for n,f in observed.items() if f.get("is_primary") is True]
    if primaries!=["Invoice No"]:
        fail("REVIEW_PRIMARY_FIELD")


def normalize(record):
    f=record.get("fields")
    if not isinstance(f,dict) or set(f)-set(REVIEW_FIELDS):
        fail("REVIEW_RECORD_SCHEMA")
    rid=record.get("record_id")
    if not isinstance(rid,str) or not re.fullmatch(r"rec[A-Za-z0-9]+",rid):
        fail("REVIEW_RECORD_ID")
    out={}
    for k,kind in REVIEW_FIELDS.items():
        v=f.get(k)
        if kind==1:
            out[k]=plain(v)
        elif kind==2:
            out[k]=won(v,optional=True)
        elif kind==7:
            if v is not None and type(v) is not bool:
                fail("REVIEW_CHECKBOX_FORMAT")
            out[k]=v is True
        else:
            fail("REVIEW_FIELD_TYPE")
    if all(v in ("",None,False) for v in out.values()):
        return None
    return {**out,"record_id":rid}


def inspect_members(records,expected):
    desired={r["Source Key"]:r for r in expected}
    observed={}
    seen=set()
    blank=0
    for record in records:
        rid=record.get("record_id")
        if rid in seen:
            fail("REVIEW_RECORD_ID_DUPLICATE")
        seen.add(rid)
        row=normalize(record)
        if row is None:
            blank+=1
            continue
        key=validate_review_member(row)
        if key in observed or key not in desired:
            fail("REVIEW_MEMBER_UNEXPECTED_OR_DUPLICATE")
        if any(row[k]!=desired[key][k] for k in SOURCE_FIELDS):
            fail("REVIEW_MEMBER_READBACK_MISMATCH")
        observed[key]=row
    return observed,blank


def verify_members(records,expected):
    observed,blank=inspect_members(records,expected)
    if len(observed)!=len(expected):
        fail("REVIEW_MEMBER_SET_INCOMPLETE")
    exclusions={k for k,r in observed.items() if r[EXCLUDE]}
    totals=member_totals(expected,exclusions)
    per_month={}
    for month in MONTHS:
        subset=[r for r in expected if r["Month"]==month]
        selected_keys={r["Source Key"] for r in subset}
        month_totals=member_totals(subset,exclusions & selected_keys)
        per_month[month]={"original":month_totals["original"]["count"],
                          "excluded":month_totals["excluded"]["count"],
                          "selected":month_totals["selected"]["count"]}
    return {"members":len(observed),"excluded":len(exclusions),
            "selected":totals["selected"]["count"],"blank_nonmember_rows":blank,
            "selection_by_month":per_month}


def specs(stamps):
    if set(stamps)!=set(MONTHS):
        fail("CHART_MONTH_SCOPE")
    label=" / ".join(m+" "+stamps[m] for m in MONTHS)
    note=("**2026년 10~11월 검증 스냅샷 · "+label+"**\n"
          "공식 Revenue 그래프는 변경하지 않습니다. 10월 48건, 11월 42건의 검증 Invoice만 포함합니다. "
          "자동 갱신하지 않는 분석 전용 스냅샷입니다. 이후 신규 Invoice는 포함되지 않습니다.\n"
          "월별 그래프 점/막대 클릭 → 실제 집계 목록 확인. Revenue Invoice Review의 "
          "'01 전체 집계 원본'에서 합산 제외 체크/해제로 분석 집계를 변경하고, "
          "제외 사유를 기록할 수 있습니다. 원래 집계는 체크와 무관합니다. "
          "공유 체크박스이므로 다른 사용자에게도 영향을 줍니다. "
          "원본·결제 상태·공식 매출은 그대로 유지됩니다.")
    out=[{"name":"집계 검토 안내","type":"text","data_config":{"text":note},
          "position":{"x":0,"y":0,"w":12,"h":6}}]
    for i,(metric,label) in enumerate((("Count Unit","Invoice 건수"),("Net KRW","VAT 제외 Revenue (KRW)"))):
        for j,(selected,suffix) in enumerate(((False,"원래 집계"),(True,"분석 합계"))):
            config=review_chart_config(metric,filtered=selected)
            # Group by month over the exact frozen two-month member table.
            # Do not invent an unverified native multi-value filter operator.
            # The backend admits only MONTHS and verifies the full member set.
            out.append({"name":label+" · "+suffix,"type":"bar" if metric=="Count Unit" else "line",
                        "data_config":config,"position":{"x":j*6,"y":6+i*7,"w":6,"h":7}})
    return out


def named_id(catalog,name):
    ids=[k for k,v in catalog.items() if v==name]
    if len(ids)>1:
        fail("TARGET_NAME_AMBIGUOUS")
    return ids[0] if ids else None


def reconcile(source,backend,mode="plan",expected_digest=""):
    if mode not in {"plan","apply","resume-empty"}:
        fail("INVALID_MODE")
    if mode!="plan" and not re.fullmatch(r"[0-9a-f]{64}",expected_digest):
        fail("REVIEWED_DIGEST_REQUIRED")
    recovery=mode=="resume-empty"
    if recovery and expected_digest!=RECOVERY_DIGEST:
        fail("RECOVERY_DIGEST_MISMATCH")
    snap=snapshot(source)
    if expected_digest and expected_digest!=snap["digest"]:
        fail("SOURCE_DIGEST_CHANGED")
    tables,pages=backend.tables(),backend.pages()
    if named_id(tables,OFFICIAL)!=OFFICIAL_ID:
        fail("OFFICIAL_TABLE_ID_MISMATCH")
    verify_official(backend.records(OFFICIAL_ID),snap["official"])
    if named_id(pages,LEGACY_TITLE):
        fail("LEGACY_OCTOBER_PILOT_REQUIRES_REVIEW")
    t,p=named_id(tables,REVIEW),named_id(pages,TITLE)
    if recovery and t!=RECOVERY_TABLE:
        fail("RECOVERY_TABLE_ID_MISMATCH")
    charts=specs(snap["stamps"])
    public={"months":list(MONTHS),"members":EXPECTED_COUNT,
            "expected_members_by_month":EXPECTED_COUNTS,
            "snapshot_verified_at_kst_by_month":snap["stamps"],
            "review_digest":snap["digest"],"official_totals_parity":True,
            "target_table":t,"target_dashboard":p,"expected_new_chart_blocks":len(charts),
            "source_writes":0,"scheduled_sync":False,
            "ui_click_edit_restore":"NOT_TESTED"}
    if (t or p) and not (recovery and t and not p):
        if not t or not p:
            if mode=="apply":
                fail("PARTIAL_TARGET_REQUIRES_REVIEW")
            detail={**public,"state":"PARTIAL_TARGET_REQUIRES_REVIEW","review_writes":0,
                    "observed_members":None,"missing_members":None}
            if t:
                try:
                    check_schema(backend.fields(t))
                    rows,blank=inspect_members(backend.records(t),snap["rows"])
                except DrilldownError:
                    print("REVENUE_REVIEW_PILOT "+canonical_json(detail),file=sys.stderr)
                    raise
                detail.update(observed_members=len(rows),missing_members=EXPECTED_COUNT-len(rows),
                              observed_by_month={m:sum(row["Month"]==m for row in rows.values())
                                                 for m in MONTHS},
                              blank_nonmember_rows=blank)
            return detail
        check_schema(backend.fields(t))
        verify=verify_members(backend.records(t),snap["rows"])
        backend.verify_page(p,charts)
        return {**public,**verify,"state":"EXISTING_SNAPSHOT_VERIFIED_NO_WRITES","review_writes":0}
    if mode=="plan":
        return {**public,"state":"READY_NEW_REVIEW_PILOT","review_writes":0}
    # Recheck names before binding the single approved empty table or
    # creating a fresh target. Neither mode retries an ambiguous write.
    if backend.tables()!=tables or backend.pages()!=pages:
        fail("TARGET_CATALOG_CHANGED")
    if recovery:
        backend.bind_empty_recovery_table(t)
    else:
        t=backend.create_table()
        after=backend.tables()
        if t in tables or named_id(after,REVIEW)!=t or any(after.get(k)!=v for k,v in tables.items()):
            fail("TABLE_CREATE_READBACK")
    check_schema(backend.fields(t))
    initial_records=backend.records(t)
    if (recovery and initial_records) or any(normalize(r) is not None for r in initial_records):
        fail("NEW_TABLE_NOT_EMPTY")
    for i in range(0,len(snap["rows"]),25):
        backend.create_members(t,[{**r,EXCLUDE:False,"제외 사유":""}
                                  for r in snap["rows"][i:i+25]])
    verify=verify_members(backend.records(t),snap["rows"])
    if verify["excluded"]!=0:
        fail("NEW_MANUAL_STATE_CHANGED")
    verify_official(backend.records(OFFICIAL_ID),snap["official"])
    if backend.pages()!=pages:
        fail("DASHBOARD_CATALOG_CHANGED")
    p=backend.create_page()
    now_pages=backend.pages()
    if p in pages or named_id(now_pages,TITLE)!=p or any(now_pages.get(k)!=v for k,v in pages.items()):
        fail("DASHBOARD_CREATE_READBACK")
    for chart in charts:
        backend.create_block(p,chart)
    backend.verify_page(p,charts)
    final=verify_members(backend.records(t),snap["rows"])
    verify_official(backend.records(OFFICIAL_ID),snap["official"])
    # No official chart/source edits; preserve original catalogs.
    final_tables,final_pages=backend.tables(),backend.pages()
    if (any(final_tables.get(k)!=v for k,v in tables.items()) or
        any(final_pages.get(k)!=v for k,v in pages.items()) or
        named_id(final_tables,REVIEW)!=t or named_id(final_pages,TITLE)!=p):
        fail("FINAL_CATALOG_DRIFT")
    return {**public,**final,"state":"RECOVERED_FROZEN_REVIEW_PILOT" if recovery else "CREATED_FROZEN_REVIEW_PILOT",
            "target_table":t,"target_dashboard":p,"review_writes":int(not recovery)+1+len(charts)+len(snap["rows"]),
            "review_write_unit":"new resources and records; not API requests"}


class NativeBackend:
    def __init__(self,token,root,request,runner,allow_write=False,allow_empty_recovery=False):
        if root!=ROOT:
            fail("WRONG_BASE")
        self.token=token;self.request=request;self.runner=runner
        self.allow_write=allow_write;self.write_table=None;self.created_page=None
        self.allow_empty_recovery=allow_empty_recovery

    def listing(self,path):
        out=[];seen=set();cursor=None
        for _ in range(200):
            query=urllib.parse.urlencode({"page_size":100,**({"page_token":cursor} if cursor else {})})
            obj=self.request("GET",path+"?"+query,self.token,action="revenue_pilot_list")
            # Feishu may omit items on an empty records table. Accept only
            # an explicit zero total on the first and terminal records page.
            if (path.endswith("/records") and cursor is None and "items" not in obj
                    and type(obj.get("total")) is int and obj["total"]==0
                    and obj.get("has_more") is False and not obj.get("page_token")):
                return []
            if not isinstance(obj.get("items"),list) or type(obj.get("has_more")) is not bool:
                resource=path.rsplit("/",1)[-1]
                fail("INCOMPLETE_LIST:"+resource+":items="+type(obj.get("items")).__name__
                     +":has_more="+type(obj.get("has_more")).__name__
                     +":zero_total="+str(type(obj.get("total")) is int and obj["total"]==0))
            out.extend(obj["items"])
            if not obj["has_more"]:
                return out
            cursor=obj.get("page_token")
            if not isinstance(cursor,str) or not cursor or cursor in seen:
                fail("PAGINATION")
            seen.add(cursor)
        fail("PAGINATION_BOUND")

    def tables(self):
        out={}
        for r in self.listing(ROOT+"/tables"):
            i,n=r.get("table_id"),r.get("name")
            if not isinstance(i,str) or not re.fullmatch(r"tbl[A-Za-z0-9]+",i) or i in out or not isinstance(n,str):
                fail("TABLE_CATALOG_SCHEMA")
            out[i]=n
        return out

    def pages(self):
        from native_project_center import inventory
        return {k:r["name"] for k,r in inventory(self.runner,"+dashboard-list").items()}

    def fields(self,t):
        if t==OFFICIAL_ID or not re.fullmatch(r"tbl[A-Za-z0-9]+",t):
            fail("UNAPPROVED_REVIEW_SCHEMA")
        return self.listing(ROOT+"/tables/"+t+"/fields")

    def records(self,t):
        catalog=self.tables()
        if catalog.get(t) not in (REVIEW,OFFICIAL) or (catalog.get(t)==OFFICIAL and t!=OFFICIAL_ID):
            fail("UNAPPROVED_RECORD_READ")
        return self.listing(ROOT+"/tables/"+t+"/records")

    def create_table(self):
        if not self.allow_write or self.allow_empty_recovery or self.write_table or named_id(self.tables(),REVIEW):
            fail("TABLE_WRITE_NOT_AUTHORIZED")
        result=self.request("POST",ROOT+"/tables",self.token,
            data={"table":{"name":REVIEW,"default_view_name":DEFAULT_VIEW,"fields":FIELD_SPECS}},
            action="revenue_pilot_new_table")
        t=(result.get("table") or {}).get("table_id") or result.get("table_id")
        if not isinstance(t,str) or not re.fullmatch(r"tbl[A-Za-z0-9]+",t) or t==OFFICIAL_ID:
            fail("TABLE_CREATE_ID")
        self.write_table=t
        return t

    def bind_empty_recovery_table(self,t):
        if (not self.allow_write or not self.allow_empty_recovery or self.write_table
                or t!=RECOVERY_TABLE or named_id(self.tables(),REVIEW)!=t
                or named_id(self.pages(),TITLE) or named_id(self.pages(),LEGACY_TITLE)):
            fail("RECOVERY_BIND_NOT_AUTHORIZED")
        check_schema(self.fields(t))
        page=self.request("GET",ROOT+"/tables/"+t+"/records?page_size=1",self.token,
                          action="revenue_pilot_verify_empty_table")
        if (page.get("has_more") is not False or type(page.get("total")) is not int
                or page["total"]!=0 or page.get("items",[])!=[] or page.get("page_token")):
            fail("RECOVERY_TABLE_NOT_PROVEN_EMPTY")
        self.write_table=t

    def create_members(self,t,rows):
        if not self.allow_write or t!=self.write_table or named_id(self.tables(),REVIEW)!=t:
            fail("ROW_WRITE_NOT_AUTHORIZED")
        if not 1<=len(rows)<=25:
            fail("ROW_BATCH_BOUND")
        for row in rows:
            validate_review_member(row)
            if (set(row)!=set(REVIEW_FIELDS) or row["Month"] not in MONTHS
                    or row[EXCLUDE] is not False or row["제외 사유"]!=""):
                fail("ROW_CREATE_SCOPE")
        result=self.request("POST",ROOT+"/tables/"+t+"/records/batch_create",self.token,
            data={"records":[{"fields":r} for r in rows]},action="revenue_pilot_new_members")
        records=result.get("records")
        if not isinstance(records,list) or len(records)!=len(rows):
            fail("ROW_CREATE_UNVERIFIED")

    def create_page(self):
        from native_project_center import response_entity,dashboard_identity
        if not self.allow_write or not self.write_table or self.created_page or named_id(self.pages(),TITLE):
            fail("DASHBOARD_WRITE_NOT_AUTHORIZED")
        r=response_entity(self.runner("+dashboard-create","--base-token",BASE,"--name",TITLE),"dashboard")
        if r.get("name")!=TITLE:
            fail("DASHBOARD_CREATE_NAME")
        self.created_page=dashboard_identity(r)
        return self.created_page

    def create_block(self,p,chart):
        from native_project_center import inventory,response_entity
        from native_overview_dashboard import block_id,encoded
        if not self.allow_write or p!=self.created_page or named_id(self.pages(),TITLE)!=p:
            fail("CHART_WRITE_NOT_AUTHORIZED")
        current=inventory(self.runner,"+dashboard-block-list",p)
        if any(r.get("name")==chart["name"] for r in current.values()):
            fail("DUPLICATE_CHART")
        if chart["type"]!="text" and chart["data_config"].get("table_name")!=REVIEW:
            fail("CHART_WRONG_SOURCE")
        r=response_entity(self.runner("+dashboard-block-create","--base-token",BASE,
            "--dashboard-id",p,"--name",chart["name"],"--type",chart["type"],
            "--data-config",encoded(chart["data_config"]),"--position",encoded(chart["position"])),"block")
        if block_id(r) in current or r.get("name")!=chart["name"] or r.get("type")!=chart["type"]:
            fail("CHART_CREATE_READBACK")

    def verify_page(self,p,charts):
        from native_project_center import inventory,response_entity,dashboard_identity
        from native_overview_dashboard import block_id,config_patch
        r=response_entity(self.runner("+dashboard-get","--base-token",BASE,"--dashboard-id",p),"dashboard")
        if dashboard_identity(r)!=p or r.get("name")!=TITLE:
            fail("DASHBOARD_ID_MISMATCH")
        current=inventory(self.runner,"+dashboard-block-list",p)
        if len(current)!=len(charts):
            fail("CHART_COUNT_MISMATCH")
        for chart in charts:
            hits=[i for i,r in current.items() if r.get("name")==chart["name"]]
            if len(hits)!=1:
                fail("CHART_NAME_MISMATCH")
            bid=hits[0]
            r=response_entity(self.runner("+dashboard-block-get","--base-token",BASE,
                "--dashboard-id",p,"--block-id",bid),"block")
            if (block_id(r)!=bid or r.get("name")!=chart["name"] or r.get("type")!=chart["type"]
                    or not isinstance(r.get("data_config"),dict)
                    or config_patch(r["data_config"],chart["data_config"])):
                fail("CHART_CONFIG_MISMATCH")


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--mode",choices=("plan","apply","resume-empty"),default="plan")
    parser.add_argument("--expected-digest",default="")
    args=parser.parse_args()
    if os.environ.get("FEISHU_BASE_APP_TOKEN")!=BASE:
        fail("WRONG_BASE")
    if args.mode!="plan" and (os.environ.get("GITHUB_REF")!="refs/heads/main" or
            os.environ.get("GITHUB_EVENT_NAME")!="workflow_dispatch" or
            not re.fullmatch(r"[0-9a-f]{64}",args.expected_digest)):
        fail("APPLY_REQUIRES_REVIEWED_MAIN_DISPATCH")
    from sales_metrics_sync import sheets_session
    from qq_mail_ingest import auth,api
    from native_dashboard_cli import cli
    source=read_sources(sheets_session())
    token,root=auth()
    backend=NativeBackend(token,root,api,cli,allow_write=args.mode!="plan",
                          allow_empty_recovery=args.mode=="resume-empty")
    result=reconcile(source,backend,args.mode,args.expected_digest)
    print("REVENUE_REVIEW_PILOT "+canonical_json(result))
    if result["state"]=="PARTIAL_TARGET_REQUIRES_REVIEW":
        fail("PARTIAL_TARGET_REQUIRES_REVIEW")


if __name__=="__main__":
    try:
        main()
    except Exception as exc:
        print("REVENUE_REVIEW_PILOT_FAILED "+(str(exc) if isinstance(exc,DrilldownError)
                                              else type(exc).__name__),file=sys.stderr)
        sys.exit(1)
