#!/usr/bin/env python3
"""Read verified CSS/SFDC Sheets -> 3 NEW isolated Feishu sales KPI tables.

No source or old Feishu writes. No raw customer data in Actions logs.
Modes: plan (reads only), apply (idempotent, bounded source-owned upserts).
"""
import collections
import datetime as dt
import decimal
import json
import os
import re
import sys
import urllib.parse
from zoneinfo import ZoneInfo

from google.auth.transport.requests import AuthorizedSession
from google.oauth2 import service_account
from qq_mail_ingest import auth, api, list_all, SafeError

EXPECTED_BASE = "IpMkbUD0vaFqtYs93a3csXtdn1b"
CSS_SHEET = "1753nq7_zX-6ae7srmJryHrFECEG5L9Mjf7JvjrbFxVY"
UNIFIED_SHEET = "1Fo0Tc6PQ3Ek0-33lmegScM_z8ST-ShUYQ0K3kD4PqnI"
KST = ZoneInfo("Asia/Seoul")
D = decimal.Decimal

# All other fields remain Feishu text to preserve audit/evidence labels.
SCHEMAS = {
    "Project SIF Monitor": [
        ("Source Key", 1), ("Institution", 1), ("Customer", 1), ("AMEA", 1),
        ("Project", 1), ("Service", 1), ("CSS Status", 1), ("Progress %", 2),
        ("Current Stage", 1), ("SIF No", 1), ("SIF State", 1),
        ("SIF First Seen", 1), ("SIF Approved", 1), ("Next Action", 1),
        ("Contract No", 1), ("Evidence", 1), ("Last Sync KST", 1),
    ],
    "Monthly Tax Invoice": [
        ("Source Key", 1), ("Month", 1), ("Invoice Count", 2),
        ("Tax Invoice KRW Incl VAT", 2), ("Net Revenue KRW Ex VAT", 2),
        ("Net Revenue K USD", 2), ("CSS Source Invoice Count", 2),
        ("CSS Source KRW Incl VAT", 2), ("Source Difference KRW", 2),
        ("Coverage Status", 1), ("Evidence", 1), ("Last Sync KST", 1),
    ],
    "Weekly Quote KPI": [
        ("Source Key", 1), ("Week Start", 1), ("Week End", 1),
        ("Approved Quote Count", 2), ("Created In Week Count", 2),
        ("Verified Amount Quote Count", 2), ("Verified Quote Value KRW FX", 2),
        ("Verified Quote Value K USD", 2), ("Unmatched Amount Count", 2),
        ("Amount Status", 1), ("Week Status", 1), ("Reporting KRW Per USD", 2),
        ("Evidence", 1), ("Last Sync KST", 1),
    ],
}
REQUIRED = {
    "CSS Project Dashboard": ("project_id", "institution", "customer_name", "current_stage", "progress_percent"),
    "CSS Contract-SIF Tracker": ("Status", "Institution", "AMEA No.", "SIF No.", "sif_first_seen_at"),
    "BI Project Lifecycle Overview": ("AMEA", "CSS Progress %", "Feishu Status (latest)"),
    "CSS Invoice Monthly Summary": ("invoice_month", "invoice_count", "total_amount_krw"),
    "Revenue Invoice Base": ("Invoice No", "Year-Month", "Revenue KRW (Tax Invoice)", "Net Revenue KRW (VAT excl; per invoice)"),
    "SFDC Weekly Overview": ("week_start", "week_end", "quotation_approvals", "approvals_created_in_week", "krw_per_usd"),
    "Quotation Approval List": ("week_start", "salesforce_record_id", "quotation_id"),
    "Quote Portfolio": ("Salesforce Quote ID (18)", "Quote QID", "Active", "Quote USD"),
}


def req_sheet(session,book,title,limit):
    rg=urllib.parse.quote("'" + title.replace("'","''") + "'!A1:AZ" + str(limit),safe="")
    url="https://sheets.googleapis.com/v4/spreadsheets/"+book+"/values/"+rg
    res=session.get(url,timeout=45)
    if not res.ok:
        raise SafeError("SHEETS_READ_FAILED_"+re.sub(r"[^a-zA-Z0-9]+","_",title)+"_"+str(res.status_code))
    rows=res.json().get("values") or []
    if not rows:
        raise SafeError("SHEETS_EMPTY_"+re.sub(r"[^a-zA-Z0-9]+","_",title))
    h=[str(x).strip() for x in rows[0]]
    missing=set(REQUIRED.get(title,()))-set(h)
    if missing:
        raise SafeError("SHEETS_SCHEMA_MISMATCH_"+re.sub(r"[^a-zA-Z0-9]+","_",title))
    if len(h)!=len(set(h)):
        raise SafeError("SHEETS_DUPLICATE_HEADERS")
    result=[]
    for row in rows[1:]:
        if any(str(x or "").strip() for x in row):
            result.append({k:str(row[i]).strip() if i<len(row) and row[i] is not None else "" for i,k in enumerate(h)})
    return result


def sheets_session():
    raw=os.environ.get("GCP_SERVICE_ACCOUNT_JSON","").strip()
    if not raw:raise SafeError("MISSING_GCP_SERVICE_ACCOUNT_JSON")
    creds=service_account.Credentials.from_service_account_info(
        json.loads(raw),scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
    return AuthorizedSession(creds)


def numer(value,strict=False):
    s=str(value or "").replace(",","").replace("₩","").replace("KRW","").replace("USD","").strip()
    if not s or s in ("--","-","UNKNOWN","N/A"):
        if strict:raise SafeError("REQUIRED_NUMERIC_VALUE_MISSING")
        return None
    try:
        amount=D(s)
        if not amount.is_finite():raise ValueError("nonfinite")
        return amount
    except (decimal.InvalidOperation,ValueError):
        if strict:raise SafeError("INVALID_NUMERIC_VALUE")
        return None


def currency(value):
    return int(D(value).quantize(D("1"),rounding=decimal.ROUND_HALF_UP))


def cell(row,name):
    return str(row.get(name) or "").strip()


def sheet_sources():
    s=sheets_session()
    conf=[
        (CSS_SHEET,"CSS Contract-SIF Tracker",1600),
        (CSS_SHEET,"CSS Project Dashboard",800),
        (UNIFIED_SHEET,"BI Project Lifecycle Overview",3000),
        (CSS_SHEET,"CSS Invoice Monthly Summary",160),
        (UNIFIED_SHEET,"Revenue Invoice Base",2500),
        (UNIFIED_SHEET,"SFDC Weekly Overview",1500),
        (CSS_SHEET,"Quotation Approval List",1500),
        (UNIFIED_SHEET,"Quote Portfolio",2600),
    ]
    outputs={}
    for book,tab,limit in conf:
        outputs[tab]=req_sheet(s,book,tab,limit)
    if not outputs["CSS Project Dashboard"] or not outputs["Revenue Invoice Base"] or not outputs["SFDC Weekly Overview"]:
        raise SafeError("MANDATORY_SOURCES_EMPTY")
    return outputs


def timestamp():
    return dt.datetime.now(KST).strftime("%Y-%m-%d %H:%M KST")


def project_rows(source):
    # Project dashboard is the *complete* baseline; Contract-SIF has only
    # a small subset of projects, so it is used solely as proof of SIF status.
    sif_index=collections.defaultdict(list)
    for item in source["CSS Contract-SIF Tracker"]:
        key=cell(item,"project_id").upper()
        if key:sif_index[key].append(item)
    lifecycle=collections.defaultdict(list)
    for item in source["BI Project Lifecycle Overview"]:
        key=cell(item,"AMEA").upper()
        if key:lifecycle[key].append(item)
    output={}
    for item in source["CSS Project Dashboard"]:
        project_id=cell(item,"project_id").upper()
        if not project_id:continue
        key="PROJECT:"+project_id
        if key in output:raise SafeError("DUPLICATE_PROJECT_SOURCE_KEY")
        linked_sif=sif_index.get(project_id,[])
        sif=linked_sif[0] if len(linked_sif)==1 else {}
        linked_life=lifecycle.get(project_id,[])
        life=linked_life[0] if len(linked_life)==1 else {}
        number=cell(sif,"SIF No.")
        first_seen=cell(sif,"sif_first_seen_at")
        css_status=cell(sif,"Status")
        wf=cell(sif,"workflow_status")
        words=(css_status+" "+wf).lower()
        approved=bool(re.search(r"\bsif\s+approved\b|sif\s+승인",words))
        submitted=bool(re.search(r"\bsif\s+(?:submitted|received|approved)\b|sif\s+(?:제출|접수|승인)",words)) or bool(number and first_seen)
        state="APPROVED" if approved else "SUBMITTED_EVIDENCE" if submitted else "NUMBER_ONLY_REVIEW" if number else "NOT_VERIFIED"
        progress=numer(cell(item,"progress_percent"))
        if progress is None:progress=numer(cell(life,"CSS Progress %"))
        stage=cell(life,"Feishu Status (latest)") or cell(item,"current_stage")
        data={
            "Source Key":key,
            "Institution":cell(item,"institution") or cell(sif,"Institution"),
            "Customer":cell(item,"customer_name") or cell(sif,"Customer Name"),
            "AMEA":project_id,
            "Project":cell(item,"project_description") or cell(sif,"Project Name"),
            "Service":cell(item,"service") or cell(life,"Service"),
            "CSS Status":css_status or cell(item,"current_stage"),
            "Current Stage":stage,
            "SIF No":number,"SIF State":state,"SIF First Seen":first_seen,
            "SIF Approved":"YES" if approved else "NOT_VERIFIED",
            "Next Action":cell(sif,"Next Action") or cell(item,"latest_action_required") or cell(life,"Immediate Next Step"),
            "Contract No":cell(sif,"Contract No."),
            "Evidence":"CSS Project Dashboard; SIF "+("EXACT_PROJECT_MATCH" if len(linked_sif)==1 else "NOT_MATCHED_OR_AMBIGUOUS")+
                "; lifecycle "+("EXACT_AMEA_MATCH" if len(linked_life)==1 else "NOT_MATCHED_OR_AMBIGUOUS"),
        }
        if progress is not None:data["Progress %"]=float(progress)
        output[key]=data
    # Preserve SIF-only projects that have no matching dashboard record.
    for pid,items in sif_index.items():
        key="PROJECT:"+pid
        if key in output:continue
        if len(items)!=1:raise SafeError("AMBIGUOUS_SIF_ONLY_PROJECT")
        item=items[0]
        number=cell(item,"SIF No.")
        submitted=bool(number and cell(item,"sif_first_seen_at"))
        output[key]={
            "Source Key":key,"Institution":cell(item,"Institution"),
            "Customer":cell(item,"Customer Name"),"AMEA":pid,
            "Project":cell(item,"Project Name"),"Service":"",
            "CSS Status":cell(item,"Status"),"Current Stage":cell(item,"Status"),
            "SIF No":number,
            "SIF State":"SUBMITTED_EVIDENCE" if submitted else "NUMBER_ONLY_REVIEW" if number else "NOT_VERIFIED",
            "SIF First Seen":cell(item,"sif_first_seen_at"),
            "SIF Approved":"NOT_VERIFIED",
            "Next Action":cell(item,"Next Action"),
            "Contract No":cell(item,"Contract No."),
            "Evidence":"CSS Contract-SIF ONLY; PROJECT_DASHBOARD_NOT_MATCHED",
        }
    if not output:raise SafeError("PROJECT_SOURCE_NO_KEYS")
    # Show project rows requiring attention earliest during bounded backfill.
    return sorted(output.values(),key=lambda r:(
        r["SIF State"]=="APPROVED",
        r["SIF State"]=="SUBMITTED_EVIDENCE",
        r["Source Key"],
    ))


def monthly_rows(source,fx=D("1500")):
    official={}
    invalid=0
    for item in source["Revenue Invoice Base"]:
        ident=cell(item,"Invoice No")
        month=cell(item,"Year-Month")
        if not ident or not re.fullmatch(r"20\d{2}-(?:0[1-9]|1[0-2])",month):continue
        gross=numer(cell(item,"Revenue KRW (Tax Invoice)"))
        net=numer(cell(item,"Net Revenue KRW (VAT excl; per invoice)"))
        if gross is None or net is None:
            invalid+=1
            continue
        gross,net=currency(gross),currency(net)
        if abs(gross-net*1.1)>3:raise SafeError("MONTHLY_INVOICE_VAT_PARITY_MISMATCH")
        v=(month,gross,net)
        if ident in official and official[ident]!=v:raise SafeError("MONTHLY_CONFLICTING_INVOICE_ID")
        official[ident]=v
    if not official:raise SafeError("MONTHLY_NO_VERIFIABLE_INVOICES")
    totals=collections.defaultdict(lambda:{"gross":0,"net":0,"count":0})
    for month,gross,net in official.values():
        totals[month]["gross"]+=gross
        totals[month]["net"]+=net
        totals[month]["count"]+=1
    css={}
    for r in source["CSS Invoice Monthly Summary"]:
        month=cell(r,"invoice_month")
        if not re.fullmatch(r"20\d{2}-(?:0[1-9]|1[0-2])",month):continue
        count=numer(cell(r,"invoice_count"))
        amount=numer(cell(r,"total_amount_krw"))
        if count is not None and amount is not None:
            css[month]=(int(count),currency(amount))
    output=[]
    for month,stat in sorted(totals.items(),reverse=True):
        other=css.get(month)
        gross,net=stat["gross"],stat["net"]
        state=("CSS_SOURCE_NOT_AVAILABLE" if other is None else
               "SOURCE_SCOPE_MATCH" if (other[0],other[1])==(stat["count"],gross)
               else "SOURCE_SCOPE_REVIEW")
        row={"Source Key":"INVOICE:"+month,"Month":month,
             "Invoice Count":stat["count"],"Tax Invoice KRW Incl VAT":gross,
             "Net Revenue KRW Ex VAT":net,"Net Revenue K USD":round(float(D(net)/fx/D(1000)),4),
             "Coverage Status":state,
             "Evidence":"Unified Revenue Invoice Base; deduplicated by Invoice No; excludes VAT for net. Independent CSS month cross-check."}
        if other is not None:
            row.update({"CSS Source Invoice Count":other[0],"CSS Source KRW Incl VAT":other[1],
                        "Source Difference KRW":gross-other[1]})
        output.append(row)
    if invalid:print("MONTHLY_SOURCE_EXCLUDED_UNVERIFIED_ROWS="+str(invalid))
    return output


def approved(value):
    return str(value or "").strip().upper() in ("YES","TRUE","1","ACTIVE")


def salesforce_id15(value):
    # Salesforce 15-char IDs are case-sensitive; 18-char IDs contain an
    # additional case-insensitive checksum. Keep the first 15 *unchanged*.
    value=str(value or "").strip()
    if re.fullmatch(r"[A-Za-z0-9]{15}(?:[A-Za-z0-9]{3})?",value):
        return value[:15]
    return ""


def weekly_rows(source):
    # Strict immutable Salesforce record-ID join. Quotation ID may refer to
    # an AMEA project instead of SFDC's QID and must not be force-matched.
    by_id=collections.defaultdict(list)
    for q in source["Quote Portfolio"]:
        if not approved(cell(q,"Active")):continue
        sf=salesforce_id15(cell(q,"Salesforce Quote ID (18)"))
        qid=cell(q,"Quote QID").upper()
        if sf:by_id[("SF15",sf)].append(q)
        if qid:by_id[("QID",qid)].append(q)
    by_week=collections.defaultdict(dict)
    for approval_row in source["Quotation Approval List"]:
        week=cell(approval_row,"week_start")
        if not re.fullmatch(r"20\d{2}-\d{2}-\d{2}",week):continue
        sf=salesforce_id15(cell(approval_row,"salesforce_record_id"))
        qid=cell(approval_row,"quotation_id").upper()
        key=("SF15",sf) if sf else ("QID",qid) if qid else None
        if key is None:continue
        if key in by_week[week]:continue
        candidates=[]
        if sf:candidates+=by_id.get(("SF15",sf),[])
        if qid:candidates+=by_id.get(("QID",qid),[])
        matches={id(x):x for x in candidates}
        price=None
        if len(matches)==1:
            quote=next(iter(matches.values()))
            price=numer(cell(quote,"Quote USD"))
            if price is not None and price<0:price=None
        by_week[week][key]=price
    output={}
    for item in source["SFDC Weekly Overview"]:
        week=cell(item,"week_start")
        if not re.fullmatch(r"20\d{2}-\d{2}-\d{2}",week):continue
        if week in output:raise SafeError("DUPLICATE_WEEKLY_SOURCE_WEEK")
        count=numer(cell(item,"quotation_approvals"))
        created=numer(cell(item,"approvals_created_in_week"))
        if count is None or count<0:continue
        fx=numer(cell(item,"krw_per_usd")) or D(1500)
        if fx<=0:raise SafeError("INVALID_WEEKLY_FX")
        prices=list(by_week.get(week,{}).values())
        verified=[p for p in prices if p is not None]
        unmatched=max(0,int(count)-len(verified))
        state=("NO_QUOTE_VALUE" if not verified else "VERIFIED_PARTIAL" if unmatched else "VERIFIED_ALL")
        row={"Source Key":"QUOTE:"+week,"Week Start":week,
             "Week End":cell(item,"week_end"),
             "Approved Quote Count":int(count),
             "Verified Amount Quote Count":len(verified),
             "Unmatched Amount Count":unmatched,
             "Amount Status":state,
             "Week Status":cell(item,"weekly_basis"),
             "Reporting KRW Per USD":float(fx),
             "Evidence":"SFDC Weekly Overview approval counts; Quote Portfolio active ID matches only. FX reporting estimate, not revenue."}
        if created is not None:row["Created In Week Count"]=int(created)
        if verified:
            usd=sum(verified,D(0))
            row["Verified Quote Value KRW FX"]=currency(usd*fx)
            row["Verified Quote Value K USD"]=round(float(usd/D(1000)),4)
        output[week]=row
    if not output:raise SafeError("WEEKLY_NO_VALID_SOURCE")
    return [output[k] for k in sorted(output,reverse=True)]


def prepare_data(sources):
    return {
        "Monthly Tax Invoice":monthly_rows(sources),
        "Weekly Quote KPI":weekly_rows(sources),
        "Project SIF Monitor":project_rows(sources),
    }


def table_catalog(token,root):
    tables=list_all(root+"/tables",token,"metric_table_list")
    by_name=collections.defaultdict(list)
    for r in tables:
        if r.get("name"):by_name[r["name"]].append(r.get("table_id"))
    return by_name


def table_path(root,table_id):
    return root+"/tables/"+urllib.parse.quote(table_id,safe="")


def ensure_tables(token,root):
    catalog=table_catalog(token,root)
    paths={}
    for name,spec in SCHEMAS.items():
        ids=catalog.get(name,[])
        if len(ids)>1:raise SafeError("DUPLICATE_METRIC_TABLE_"+name.replace(" ","_"))
        if not ids:
            api("POST",root+"/tables",token,data={"table":{
                "name":name,"default_view_name":"All",
                "fields":[{"field_name":f,"type":t} for f,t in spec],
            }},action="metric_create_table")
            catalog=table_catalog(token,root)
            ids=catalog.get(name,[])
            if len(ids)!=1:raise SafeError("METRIC_TABLE_CREATE_READBACK_FAILED")
            print("METRIC_TABLE_CREATED="+name)
        p=table_path(root,ids[0])
        fields=list_all(p+"/fields",token,"metric_schema")
        names={f.get("field_name"):f.get("type") for f in fields}
        if any(names.get(f)!=t for f,t in spec):
            raise SafeError("METRIC_SCHEMA_MISMATCH_"+name.replace(" ","_"))
        paths[name]=p
    return paths


def raw_value(value):
    if isinstance(value,(int,float)):return str(value)
    if isinstance(value,str):return value
    if isinstance(value,list):return "".join(raw_value(x) for x in value)
    if isinstance(value,dict):return raw_value(value.get("text") or value.get("value") or "")
    return ""


def equivalent(before,new):
    for k,v in new.items():
        if k=="Last Sync KST":continue
        a=raw_value(before.get(k)).strip()
        b=str(v).strip()
        if isinstance(v,(int,float)):
            x=numer(a)
            if x is not None and abs(x-D(str(v)))<D("0.00005"):continue
        if a!=b:return False
    return True


def batches(rows, size=25):
    for i in range(0,len(rows),size):
        yield rows[i:i+size]


def sync_table(token,path,desired,limit):
    # Read the existing ledger first, then never overwrite or duplicate a key.
    existing=list_all(path+"/records",token,"metric_records")
    index={}
    for rec in existing:
        key=raw_value((rec.get("fields") or {}).get("Source Key")).strip()
        if not key:continue
        if key in index:raise SafeError("DUPLICATE_TARGET_SOURCE_KEY")
        index[key]=rec
    pending_create=[]
    pending_update=[]
    unchanged=0
    seen=set()
    for obj in desired:
        key=obj["Source Key"]
        if key in seen:raise SafeError("DUPLICATE_SOURCE_KEY_IN_BATCH")
        seen.add(key)
        prev=index.get(key)
        if prev and equivalent(prev.get("fields") or {},obj):
            unchanged+=1
            continue
        if len(pending_create)+len(pending_update)>=limit:continue
        fields={**obj,"Last Sync KST":timestamp()}
        if prev:
            rid=prev.get("record_id")
            if not rid:raise SafeError("MISSING_TARGET_RECORD_ID")
            pending_update.append({"record_id":rid,"fields":fields})
        else:
            pending_create.append({"fields":fields})
    # Feishu officially supports at most 500 records per batch request.
    # Use 25 to bound payload sizes and minimize write-conflict risk.
    for batch in batches(pending_create):
        data=api("POST",path+"/records/batch_create",token,
                 data={"records":batch},action="metric_batch_create")
        result=data.get("records") or []
        if len(result)!=len(batch) or any(not x.get("record_id") for x in result):
            raise SafeError("METRIC_BATCH_CREATE_UNCONFIRMED")
    for batch in batches(pending_update):
        data=api("POST",path+"/records/batch_update",token,
                 data={"records":batch},action="metric_batch_update")
        result=data.get("records") or []
        if len(result)!=len(batch) or any(not x.get("record_id") for x in result):
            raise SafeError("METRIC_BATCH_UPDATE_UNCONFIRMED")
    # Independent readback is essential: responses alone do not prove all writes.
    if pending_create or pending_update:
        after=list_all(path+"/records",token,"metric_readback")
        verified={}
        for row in after:
            k=raw_value((row.get("fields") or {}).get("Source Key")).strip()
            if not k:continue
            if k in verified:raise SafeError("METRIC_READBACK_DUPLICATE_KEY")
            verified[k]=row
        expected=pending_create+[{"fields":row["fields"]} for row in pending_update]
        for rec in expected:
            fields=rec["fields"]
            k=fields["Source Key"]
            observed=verified.get(k)
            if not observed or not equivalent(observed.get("fields") or {},fields):
                raise SafeError("METRIC_BATCH_READBACK_MISMATCH")
    created=len(pending_create)
    updated=len(pending_update)
    print("METRIC_SYNC_RESULT table="+re.sub(r"[^a-zA-Z]","_",path.split("/")[-1])+
          " created="+str(created)+" updated="+str(updated)+
          " unchanged="+str(unchanged)+" desired="+str(len(desired))+
          " bounded="+str(limit))
    return created,updated,unchanged


VIEW_SPECS = {
    "Project SIF Monitor": (
        ("프로젝트 진행 · SIF", None, None),
        ("SIF 제출 미확인", "SIF State", "NOT_VERIFIED"),
        ("SIF 번호만 확인", "SIF State", "NUMBER_ONLY_REVIEW"),
        ("SIF 제출 증빙 있음", "SIF State", "SUBMITTED_EVIDENCE"),
        ("SIF 승인 완료", "SIF State", "APPROVED"),
    ),
    "Monthly Tax Invoice": (
        ("월별 Tax Invoice", None, None),
        ("Tax Invoice 원본 차이 검토", "Coverage Status", "SOURCE_SCOPE_REVIEW"),
    ),
    "Weekly Quote KPI": (
        ("매주 Quote 건수 · 금액", None, None),
        ("견적 금액 미확인", "Amount Status", "NO_QUOTE_VALUE"),
        ("견적 금액 부분확인", "Amount Status", "VERIFIED_PARTIAL"),
    ),
}


def setup_views(token, paths):
    # All URLs are base-local and require Feishu sign-in.
    from setup_sales_web import resolve_view, get_view, filter_matches, field_map
    for table, specs in VIEW_SPECS.items():
        path = paths[table]
        fields = field_map(token, path)
        for name, filterfield, value in specs:
            view_id, _ = resolve_view(token, path, name, filterfield is not None)
            view = get_view(token, path, view_id)
            if filterfield is not None:
                field_id = fields.get(filterfield)
                if not field_id:raise SafeError("VIEW_FILTER_FIELD_MISSING")
                if not (view.get("view_name") == name and filter_matches(view,field_id,value)):
                    api("PATCH",path+"/views/"+urllib.parse.quote(view_id,safe=""),token,
                        data={"view_name":name,"property":{"filter_info":{
                            "conjunction":"and","conditions":[{
                                "field_id":field_id,"operator":"is",
                                "value":json.dumps([value],ensure_ascii=False),
                            }],
                        }}},action="metric_view_filter_patch")
                    view=get_view(token,path,view_id)
                    if not (view.get("view_name")==name and filter_matches(view,field_id,value)):
                        raise SafeError("METRIC_FILTER_READBACK_FAILED")
            elif view.get("view_name")!=name:
                raise SafeError("METRIC_VIEW_READBACK_FAILED")
            table_id=path.rsplit("/",1)[-1]
            url="https://ocnz4cb25scn.feishu.cn/base/"+EXPECTED_BASE
            url+="?table="+urllib.parse.quote(table_id,safe="")
            url+="&view="+urllib.parse.quote(view_id,safe="")
            print("METRIC_WEB_VIEW="+name+" URL="+url)

def main():
    if os.environ.get("FEISHU_BASE_APP_TOKEN")!=EXPECTED_BASE:
        raise SafeError("REFUSE_UNKNOWN_FEISHU_BASE")
    mode=os.environ.get("FEISHU_METRIC_MODE","plan").strip()
    if mode not in ("plan","apply"):raise SafeError("INVALID_METRIC_MODE")
    sources=sheet_sources()  # Fetch all before any writes.
    output=prepare_data(sources)
    for name,items in output.items():
        print("METRIC_SOURCE_READY="+name+" rows="+str(len(items)))
    if mode=="plan":
        print("METRIC_PLAN_PASS writes=0")
        return
    token,root=auth()
    paths=ensure_tables(token,root)
    setup_views(token,paths)
    # Prioritize numeric KPI summaries; SIF backfill progresses across scheduled runs.
    bounds={"Monthly Tax Invoice":100,"Weekly Quote KPI":150,"Project SIF Monitor":500}
    total=0
    for name in ("Monthly Tax Invoice","Weekly Quote KPI","Project SIF Monitor"):
        result=sync_table(token,paths[name],output[name],bounds[name])
        total+=sum(result[:2])
    print("FEISHU_SALES_METRIC_APPLY_PASS record_writes="+str(total)+" all_other_feishu_bases_writes=0")


if __name__=="__main__":
    try:main()
    except Exception as exc:
        reason=str(exc) if isinstance(exc,SafeError) else type(exc).__name__
        print("FEISHU_SALES_METRIC_FAILED:"+reason,file=sys.stderr)
        sys.exit(1)
