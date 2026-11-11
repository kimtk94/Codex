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
import time
import urllib.parse
from zoneinfo import ZoneInfo

from google.auth.transport.requests import AuthorizedSession
from google.oauth2 import service_account
from qq_mail_ingest import auth, api, list_all, SafeError
from project_progress_board import prepare_project_board
from project_settlement import EVIDENCE_FIELDS, finalize, counts
from latest_payment_bridge import build_payment_evidence
from quote_process_amount import weekly_calculations
from approval_mail_weekly_bridge import supplement as reconcile_mail_approvals
from weekly_quote_review import (
    TABLE as QUOTE_REVIEW_TABLE, SCHEMA as QUOTE_REVIEW_SCHEMA,
    VIEW_SPECS as QUOTE_REVIEW_VIEWS, INCLUDED as REVIEW_INCLUDED,
    review_rows as build_quote_review, membership as quote_review_membership,
    read_overrides as quote_manual_overrides, sync_review as sync_quote_review,
)
from monthly_revenue_canonical import evidence_rows,RevenueEvidenceError

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
    "Project Progress Board": [
        ("Source Key", 1), ("AMEA", 1), ("Quote Full Name", 1),
        ("Quote Match State", 1), ("Institution", 1), ("Customer", 1),
        ("Service", 1), ("Current Stage", 1), ("Progress Phase", 1), ("Progress %", 2),
        ("Progress Bar", 1), ("Prepayment", 1), ("Prepayment Evidence", 1),
        ("SIF State", 1), ("PO Evidence", 1), ("Next Action", 1),
        ("Evidence", 1), ("Project Display Name", 1),
        ("Completion Evidence", 1), ("Workflow Lane", 1),
        ("Payment State", 1), ("Payment Owner Scope", 1), ("Invoice Gross KRW", 2), ("Invoice Gross M KRW", 2),
        ("Outstanding Balance KRW", 2), ("Outstanding Balance M KRW", 2),
        ("Payment Invoice No", 1), ("Bank Receipt Reference", 1),
        ("Verified Invoice KRW", 2), ("Verified Received KRW", 2),
        ("Receipt Verified At", 1), ("Receipt Verified By", 1),
        ("Receipt Source", 1), ("Receipt Verification Status", 1),
        ("Receipt Source Snapshot Date", 1),
        ("Outstanding Source Snapshot Date", 1),
        ("Last Sync KST", 1),
    ],
    "Monthly Tax Invoice": [
        ("Source Key", 1), ("Month", 1), ("Invoice Count", 2),
        ("Tax Invoice KRW Incl VAT", 2), ("Net Revenue KRW Ex VAT", 2),
        ("Net Revenue M KRW", 2), ("Net Revenue K USD", 2), ("CSS Source Invoice Count", 2),
        ("CSS Source KRW Incl VAT", 2), ("Source Difference KRW", 2),
        ("Coverage Status", 1), ("Evidence", 1), ("Last Sync KST", 1),
    ],
    QUOTE_REVIEW_TABLE: QUOTE_REVIEW_SCHEMA,
    "Weekly Quote KPI": [
        ("Source Key", 1), ("Week Start", 1), ("Week End", 1),
        ("Chart Week Label", 1), ("Chart Window", 1),
        ("Approved Quote Count", 2), ("Included Quote Count", 2),
        ("Excluded Quote Count", 2), ("Active Unverified Quote Count", 2),
        ("Active Coverage Status", 1), ("Created In Week Count", 2),
        ("Verified Amount Quote Count", 2), ("Verified Quote Value KRW FX", 2),
        ("Verified Quote Value M KRW FX", 2), ("Verified Quote Value K USD", 2), ("Unmatched Amount Count", 2),
        ("Calculated Quote Count", 2), ("Quote Amount Exception Count", 2),
        ("Calculated Quote Value K USD", 2), ("Calculated Quote Value M KRW FX", 2),
        ("Quote Calculation Source", 1),
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
    "BI Revenue Net VAT Monthly": ("Month", "Issued Invoice Gross KRW (VAT incl)",
        "Issued Net Revenue KRW (VAT excl)", "Issued Net Revenue kUSD @1500",
        "Issued Invoice Count", "Verified At KST", "Evidence State"),
    "BI Revenue Lifecycle Monthly": ("Month", "Actual Invoice KRW", "Invoice Count"),
    "Revenue Source Authority": ("Month", "Source Tab", "Source Role",
        "Issued Invoice Count", "Amount KRW", "Tax Basis", "Source Parity",
        "Authoritative For KPI", "Verified KST"),
    "SFDC Weekly Overview": ("week_start", "week_end", "quotation_approvals", "approvals_created_in_week", "krw_per_usd"),
    "Quotation Approval List": ("week_start", "salesforce_record_id", "quotation_id"),
    "Quote Approval Dedup": ("Approval KST", "SFDC Record ID", "Quotation Name",
                             "Quote Status", "Approved AND Active"),
    "Quotation Approval Auto": ("approval_mail_at_kst","quotation_id","quotation_name",
                                "salesforce_record_id","approval_evidence",
                                "review_status","ingest_key"),
    "SFDC Quote Export": ("Salesforce Record ID", "IsActive", "Exclude Tax After Discount USD",
                           "CurrencyIsoCode", "Opportunity ID", "Exported At KST"),
    "SFDC Email Opportunities Raw": ("Opportunity ID", "Opportunity Owner"),
    "SFDC Email Ingest Audit": ("Entity", "Source Received KST", "State",
                                "Rows", "Unique IDs", "Content SHA256", "Source Kind"),
    "SFDC Email Quotation Raw": ("SFDC Quotation ID", "Quotation Product ID",
        "Opportunity ID", "Active", "Unit Price USD", "Process Name: SFDC Process ID",
        "Sample Quantity"),
    "Feishu Latest Prepayments": ("Project Number", "Quotation Number"),
    "Feishu Latest Receipts": ("CMS No.", "Amount (KRW)", "Deposit Date",
                               "CMS No. [2]", "Amount", "Date",
                               "CMS No. [3]", "Amount [2]", "Date [2]"),
    "Feishu Latest Outstanding": ("CMS Invoice Number", "Quotation Number",
                                   "Project Number", "Invoice Amount","Balance"),
    "Feishu Latest eTax": ("CMS Invoice Num", "Quotation Number",
                           "Project Number", "Amount"),
    "Feishu Source Manifest": ("Source", "Source Date", "Synced At KST",
                                 "Source ID", "Schema"),
}


def req_sheet(session,book,title,limit):
    rg=urllib.parse.quote("'" + title.replace("'","''") + "'!A1:AZ" + str(limit),safe="")
    url="https://sheets.googleapis.com/v4/spreadsheets/"+book+"/values/"+rg
    # Quotation source is large and shared Sheets quota intermittently returns
    # HTTP 429. Retry only transient statuses with bounded provider-aware
    # backoff; never label an unsuccessful read as a valid fresh snapshot.
    res=None
    for attempt in range(6):
        res=session.get(url,timeout=45)
        if res.status_code not in (429,500,502,503,504) or attempt==5:
            break
        try:
            retry_after=float(res.headers.get("Retry-After","0"))
        except (TypeError,ValueError):
            retry_after=0.0
        delay=min(45.0,max(2.0,float(2**(attempt+1)),retry_after))
        print("SHEETS_READ_TRANSIENT_RETRY tab="+
              re.sub(r"[^a-zA-Z0-9]+","_",title)+
              " status="+str(res.status_code)+
              " attempt="+str(attempt+1)+
              " delay_seconds="+str(delay),flush=True)
        time.sleep(delay)
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
        (UNIFIED_SHEET,"BI Revenue Net VAT Monthly",120),
        (UNIFIED_SHEET,"BI Revenue Lifecycle Monthly",120),
        (UNIFIED_SHEET,"Revenue Source Authority",250),
        (UNIFIED_SHEET,"SFDC Weekly Overview",1500),
        (UNIFIED_SHEET,"Quote Approval Dedup",1600),
        (CSS_SHEET,"Quotation Approval Auto",1000),
        (UNIFIED_SHEET,"SFDC Quote Export",2600),
        (UNIFIED_SHEET,"SFDC Email Opportunities Raw",950),
        (UNIFIED_SHEET,"SFDC Email Quotation Raw",4500),
        (UNIFIED_SHEET,"SFDC Email Ingest Audit",30),
        (UNIFIED_SHEET,"Quote Portfolio",2600),
        (UNIFIED_SHEET,"Feishu Latest Prepayments",500),
        (UNIFIED_SHEET,"Feishu Latest Receipts",700),
        (UNIFIED_SHEET,"Feishu Latest Outstanding",500),
        (UNIFIED_SHEET,"Feishu Latest eTax",250),
        (UNIFIED_SHEET,"Feishu Source Manifest",20),
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
    prepaid_quotation_ids={
        cell(r,"Quotation Number").upper()
        for r in source.get("Feishu Latest Prepayments",[])
        if cell(r,"Quotation Number")
    }
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
        prepaid=(cell(sif,"Prepayment").upper() in ("TRUE","YES","1") or
                 project_id in prepaid_quotation_ids)
        state="APPROVED" if approved else "SUBMITTED_EVIDENCE" if submitted else "WAIVED_PREPAYMENT" if prepaid else "NUMBER_ONLY_REVIEW" if number else "NOT_VERIFIED"
        progress=numer(cell(item,"progress_percent"))
        if progress is None:progress=numer(cell(life,"CSS Progress %"))
        stage=cell(life,"Feishu Status (latest)") or cell(item,"current_stage")
        next_action=cell(sif,"Next Action") or cell(item,"latest_action_required") or cell(life,"Immediate Next Step")
        if prepaid and not submitted:
            next_action="Prepayment 등재 · SIF 제출 필수 아님 · 샘플 입고 및 다음 단계 확인"
        elif (submitted or (progress is not None and progress>=40)) and re.search(r"\bSIF\b",next_action,re.I):
            next_action="기존 SIF 요청 제외 · 샘플 및 후속 공정 확인"
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
            "Next Action":next_action,
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
        prepaid=(cell(item,"Prepayment").upper() in ("TRUE","YES","1") or
                 pid in prepaid_quotation_ids)
        output[key]={
            "Source Key":key,"Institution":cell(item,"Institution"),
            "Customer":cell(item,"Customer Name"),"AMEA":pid,
            "Project":cell(item,"Project Name"),"Service":"",
            "CSS Status":cell(item,"Status"),"Current Stage":cell(item,"Status"),
            "SIF No":number,
            "SIF State":"SUBMITTED_EVIDENCE" if submitted else "WAIVED_PREPAYMENT" if prepaid else "NUMBER_ONLY_REVIEW" if number else "NOT_VERIFIED",
            "SIF First Seen":cell(item,"sif_first_seen_at"),
            "SIF Approved":"NOT_VERIFIED",
            "Next Action":("Prepayment 등재 · SIF 제출 필수 아님 · 샘플 입고 및 다음 단계 확인"
                           if prepaid and not submitted else
                           "기존 SIF 요청 제외 · 샘플 및 후속 공정 확인"
                           if submitted and re.search(r"\bSIF\b",cell(item,"Next Action"),re.I)
                           else cell(item,"Next Action")),
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


def scaled_m_krw(value):
    """Display-only M KRW; full KRW remains unchanged in source fields."""
    n=D(str(value))/D("1000000")
    n=n.quantize(D("0.0001"))
    return int(n) if n==n.to_integral_value() else float(n)


def scaled_k_usd(value):
    """Display-only K USD, integer when exactly whole K."""
    n=(D(str(value))/D("1000")).quantize(D("0.0001"))
    return int(n) if n==n.to_integral_value() else float(n)


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
             "Net Revenue KRW Ex VAT":net,
             "Net Revenue M KRW":scaled_m_krw(net),
             "Net Revenue K USD":scaled_k_usd(D(net)/fx),
             "Coverage Status":state,
             "Evidence":"Unified Revenue Invoice Base; deduplicated by Invoice No; excludes VAT for net. Independent CSS month cross-check."}
        if other is not None:
            row.update({"CSS Source Invoice Count":other[0],"CSS Source KRW Incl VAT":other[1],
                        "Source Difference KRW":gross-other[1]})
        output.append(row)
    # Current 2026 official monthly actuals supersede the legacy invoice
    # ledger only when independently signed by the canonical net+gross source
    # authority records. Existing historical months remain untouched.
    canonical_names=("BI Revenue Net VAT Monthly",
                     "BI Revenue Lifecycle Monthly","Revenue Source Authority")
    if any(name in source for name in canonical_names):
        try:
            canonical=evidence_rows(source,fx)
        except RevenueEvidenceError as exc:
            raise SafeError("MONTHLY_CANONICAL_AUTHORITY_BLOCKED:"+str(exc)) from exc
        by_month={row["Month"]:row for row in output}
        for row in canonical:
            original=by_month.get(row["Month"])
            print("MONTHLY_CANONICAL_AUTHORIZED month="+row["Month"]+
                  " invoice_count="+str(row["Invoice Count"])+
                  " net_m_krw="+str(row["Net Revenue M KRW"])+
                  " legacy_month_superseded="+str(original is not None))
            by_month[row["Month"]]=row
        output=[by_month[key] for key in sorted(by_month,reverse=True)]
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


def quote_chart_week_label(week_start):
    """Use the Monday within the Fri-Thu sales week to label crossover weeks.

    Friday 2026-10-30 to Thursday 2026-11-05 -> Nov W1, as in
    the user-supplied KOREA Count/Value graph.
    """
    try:
        start=dt.date.fromisoformat(week_start)
        monday=start+dt.timedelta(days=3)
        if monday.weekday()!=0:
            raise ValueError("NOT_FRIDAY_ANCHORED")
        return monday.strftime("%b")+" W"+str((monday.day-1)//7+1)
    except ValueError:
        return ""


def _recent_sfdc_time(value, now, max_hours=48):
    value=str(value or "").strip().replace(" KST","")
    try:
        when=dt.datetime.strptime(value,"%Y-%m-%d %H:%M:%S").replace(tzinfo=KST)
    except ValueError:
        return False
    seconds=(now-when).total_seconds()
    return 0<=seconds<=max_hours*3600


def _verified_quote_object_source(source, now):
    """Only a recent independently exported Salesforce Quote object proves money.

    Quote Portfolio and process-level converted totals are NOT authorized.
    """
    raw=source.get("SFDC Quote Export",[])
    if not raw:
        return {}, "WITHHELD_QUOTE_OBJECT_EXPORT_MISSING"
    if any(not _recent_sfdc_time(cell(r,"Exported At KST"),now) for r in raw):
        return {}, "WITHHELD_QUOTE_OBJECT_EXPORT_STALE"
    audits=[r for r in source.get("SFDC Email Ingest Audit",[])
            if cell(r,"Entity")=="Opportunities"]
    if len(audits)!=1 or not _recent_sfdc_time(cell(audits[0],"Source Received KST"),now):
        return {}, "WITHHELD_OPPORTUNITY_OWNER_SNAPSHOT_STALE"
    if cell(audits[0],"State") not in ("STAGED_NOT_PROMOTED","PRESERVED_NO_NEW_REPORT"):
        return {}, "WITHHELD_OPPORTUNITY_OWNER_SOURCE_UNVERIFIED"
    owners=collections.defaultdict(set)
    for r in source.get("SFDC Email Opportunities Raw",[]):
        oid=cell(r,"Opportunity ID")
        if oid:
            owners[oid].add(cell(r,"Opportunity Owner"))
    by_sf=collections.defaultdict(list)
    for r in raw:
        sid=salesforce_id15(cell(r,"Salesforce Record ID"))
        if not sid.startswith("a0P"):
            return {}, "WITHHELD_QUOTE_EXPORT_INVALID_IMMUTABLE_ID"
        by_sf[sid].append(r)
    if any(len(items)!=1 for items in by_sf.values()):
        return {}, "WITHHELD_QUOTE_EXPORT_DUPLICATE_ID"
    verified={}
    for sid,records in by_sf.items():
        q=records[0]
        if not approved(cell(q,"IsActive")) or cell(q,"CurrencyIsoCode").upper()!="USD":
            continue
        usd=numer(cell(q,"Exclude Tax After Discount USD"))
        if usd is None or usd<=0:
            continue
        oid=cell(q,"Opportunity ID")
        if owners.get(oid,set())!={"Kim Taehoon"}:
            continue
        verified[sid]=usd
    return verified,"QUOTE_OBJECT_ACTIVE_OWNER_FRESH_VERIFIED"


def weekly_rows(source, now=None, review=None):
    """Retain all approvals; sum only Active + user-included Quotes."""
    now=now or dt.datetime.now(KST)
    review=review if review is not None else build_quote_review(source,now=now)
    approval_members,include_members=quote_review_membership(review)
    unverified_by_week=collections.Counter(
        r["Week Start"] for r in review
        if r.get("제외 이유")=="ACTIVE_NOT_VERIFIED")
    permitted_ids=set().union(*include_members.values()) if include_members else set()
    quote_values,proof=_verified_quote_object_source(source,now)
    calculated,process_info=weekly_calculations(source,now,included_sids=permitted_ids)
    by_week=collections.defaultdict(dict)
    for entry in source.get("Quote Approval Dedup",[]):
        try:
            date=dt.date.fromisoformat(cell(entry,"Approval KST")[:10])
        except ValueError:
            continue
        wk=(date-dt.timedelta(days=(date.weekday()-4)%7)).isoformat()
        sid=salesforce_id15(cell(entry,"SFDC Record ID"))
        if sid.startswith("a0P"):
            by_week[wk][sid]=quote_values.get(sid) if sid in permitted_ids else None
    output={}
    for item in source["SFDC Weekly Overview"]:
        week=cell(item,"week_start")
        if not re.fullmatch(r"20\d{2}-\d{2}-\d{2}",week):
            continue
        if week in output:
            raise SafeError("DUPLICATE_WEEKLY_SOURCE_WEEK")
        count_text=cell(item,"quotation_approvals")
        count=numer(count_text)
        created=numer(cell(item,"approvals_created_in_week"))
        if count is None:
            if count_text:
                # Nonempty malformed data must fail; never silently drop a week.
                raise SafeError("WEEKLY_APPROVAL_COUNT_NOT_NUMERIC")
            # A blank weekly count does not prove zero approvals. Keep the
            # historical week visible in the target Base as a source-gap
            # record, with every count and money measure explicitly withheld.
            # This also clears a formerly populated, unverified old Feishu
            # value instead of leaving an apparently valid orphaned week.
            output[week]={
                "Source Key":"QUOTE:"+week,
                "Week Start":week,
                "Week End":cell(item,"week_end"),
                "Approved Quote Count":None,
                "Included Quote Count":None,
                "Excluded Quote Count":None,
                "Active Unverified Quote Count":None,
                "Active Coverage Status":"NO_VALUE_APPROVAL_SOURCE",
                "Created In Week Count":None,
                "Verified Amount Quote Count":None,
                "Unmatched Amount Count":None,
                "Calculated Quote Count":None,
                "Quote Amount Exception Count":None,
                "Verified Quote Value KRW FX":None,
                "Verified Quote Value M KRW FX":None,
                "Verified Quote Value K USD":None,
                "Calculated Quote Value K USD":None,
                "Calculated Quote Value M KRW FX":None,
                "Reporting KRW Per USD":None,
                "Quote Calculation Source":"WITHHELD_WEEKLY_APPROVAL_COUNT_MISSING",
                "Amount Status":"WITHHELD_WEEKLY_APPROVAL_COUNT_MISSING",
                "Week Status":cell(item,"weekly_basis"),
                "Evidence":"SFDC Weekly Overview has a blank approval count; "
                           "no verified weekly count is asserted. "
                           "Zero must not be inferred from absent evidence."
            }
            continue
        if count<0 or count!=count.to_integral_value():
            raise SafeError("WEEKLY_APPROVAL_COUNT_INVALID")
        current=calculated.get(week,{})
        # The legacy Weekly Overview can lag its event-level approvals by one
        # week. Exact immutable Salesforce-ID approvals are authoritative.
        # Never shift a count based on a guessed week/row offset.
        legacy_count=int(count)
        evidence_count=current.get("approval_ids",0)
        if evidence_count>0 and not (current.get("issues") or {}).get(
                "invalid_approval_identifier",0):
            count=D(evidence_count)
            created=D(current.get("created_in_week_count",0))
            if evidence_count!=legacy_count:
                print("QUOTE_WEEKLY_COUNT_RECONCILED week="+week+
                      " source="+str(legacy_count)+
                      " dedup="+str(evidence_count))
            count_source="IMMUTABLE_APPROVAL_DEDUP"
        else:
            count_source="LEGACY_WEEKLY_FALLBACK"
        fx=numer(cell(item,"krw_per_usd")) or D(1500)
        if fx<=0:
            raise SafeError("INVALID_WEEKLY_FX")
        entries=by_week.get(week,{})
        complete_evidence=len(entries)==int(count)
        selection_covered=(len(approval_members.get(week,set()))==int(count)
                           and complete_evidence)
        eligible_count=(len(include_members.get(week,set()))
                        if selection_covered else None)
        excluded_count=(int(count)-eligible_count
                        if eligible_count is not None else None)
        unverified_count=(unverified_by_week.get(week,0)
                          if selection_covered else None)
        # A missing Active snapshot is NOT proof that there are zero Active
        # Quotes. Keep numeric chart/amount series NULL (displayed as '-')
        # when no confirmed Active and some source statuses are unknown.
        no_value_active=(eligible_count==0 and (unverified_count or 0)>0)
        active_coverage=("NO_VALUE_ACTIVE_STATUS" if no_value_active else
                         "PARTIAL_ACTIVE_STATUS" if (unverified_count or 0)>0 else
                         "VERIFIED_ACTIVE_SCOPE" if selection_covered else
                         "NO_VALUE_APPROVAL_COVERAGE")
        included_display=None if no_value_active else eligible_count
        verified=([p for p in entries.values() if p is not None]
                  if proof=="QUOTE_OBJECT_ACTIVE_OWNER_FRESH_VERIFIED" and complete_evidence
                  else [])
        unmatched=(max(0,eligible_count-len(verified))
                   if eligible_count is not None else None)
        process_state=process_info["source_state"]
        process_count=0
        process_usd=None
        if process_state!="SOURCE_QQ_REPORT_VERIFIED":
            calc_status=process_state
        elif int(count)==0:
            calc_status=("NO_APPROVALS" if current.get("approval_ids",0)==0
                         else "WITHHELD_APPROVAL_COUNT_MISMATCH")
        elif not selection_covered:
            calc_status="WITHHELD_ACTIVE_MEMBERSHIP_COVERAGE_GAP"
        elif no_value_active:
            calc_status="NO_VALUE_ACTIVE_STATUS"
        elif eligible_count==0:
            calc_status="NO_ELIGIBLE_ACTIVE_QUOTES"
        elif current.get("approval_ids",0)!=int(count):
            calc_status="WITHHELD_APPROVAL_COUNT_MISMATCH"
        else:
            process_count=current["calculated_count"]
            process_usd=current["candidate_usd"] if process_count else None
            calc_status=("PROCESS_PRICE_CALCULATED_COMPLETE" if count and process_count==eligible_count
                         else "PROCESS_PRICE_CALCULATED_PARTIAL" if process_count
                         else "NO_SAFE_PROCESS_QUOTE_PRICE")
        status=(proof if proof!="QUOTE_OBJECT_ACTIVE_OWNER_FRESH_VERIFIED"
                else "WITHHELD_APPROVAL_COUNT_MISMATCH" if not complete_evidence
                else "NO_QUOTE_VALUE" if not verified
                else "VERIFIED_PARTIAL" if unmatched else "VERIFIED_ALL")
        if process_state=="SOURCE_QQ_REPORT_VERIFIED" and process_count:
            status=calc_status  # visible calculation status; verified object proof remains separate
        row={"Source Key":"QUOTE:"+week,"Week Start":week,
             "Week End":cell(item,"week_end"),
             "Approved Quote Count":int(count),
             "Included Quote Count":included_display,
             "Excluded Quote Count":excluded_count,
             "Active Unverified Quote Count":unverified_count,
             "Active Coverage Status":active_coverage,
             "Verified Amount Quote Count":(None if no_value_active else len(verified)),
             "Unmatched Amount Count":(None if no_value_active else unmatched),
             "Amount Status":status,
             "Week Status":cell(item,"weekly_basis"),
             "Reporting KRW Per USD":float(fx),
             "Calculated Quote Count":(None if no_value_active else process_count),
             "Quote Amount Exception Count":(
                 None if no_value_active or eligible_count is None else
                 max(0,eligible_count-process_count)),
             "Calculated Quote Value K USD":None,
             "Calculated Quote Value M KRW FX":None,
             "Quote Calculation Source":calc_status+" / "+process_state+
                  " / count="+count_source+" / active_only=TRUE / manual_exclude=ON"
                  +" / coverage="+active_coverage,
             "Evidence":"Quote approval count="+count_source+
                        "; Active=Quote Status ACTIVE + Approved AND Active YES + SFDC IsActive 1; "
                         "manual exclusion respected; SFDC Weekly Overview; "
                        "money requires fresh Salesforce Quote Object Exclude Tax USD, "
                        "Active, owner and exact count proof. Status: "+status,
             # Explicit nulls clear stale number cells in the existing Feishu record.
             "Verified Quote Value KRW FX":None,
             "Verified Quote Value M KRW FX":None,
             "Verified Quote Value K USD":None}
        if created is not None:
            row["Created In Week Count"]=int(created)
        if process_usd is not None:
            row["Calculated Quote Value K USD"]=scaled_k_usd(process_usd)
            row["Calculated Quote Value M KRW FX"]=scaled_m_krw(currency(process_usd*fx))
        if verified:
            usd=sum(verified,D(0))
            row["Verified Quote Value KRW FX"]=currency(usd*fx)
            row["Verified Quote Value M KRW FX"]=scaled_m_krw(currency(usd*fx))
            row["Verified Quote Value K USD"]=scaled_k_usd(usd)
        output[week]=row
    if not output:
        raise SafeError("WEEKLY_NO_VALID_SOURCE")
    gaps=sum(row["Approved Quote Count"] is None for row in output.values())
    print("QUOTE_WEEKLY_COVERAGE source_weeks="+str(len(output))+
          " counted="+str(len(output)-gaps)+" missing_count="+str(gaps)+
          " policy=RETAIN_WEEK_WITH_NULL_MEASURES")
    completed=sorted((week for week,row in output.items()
                      if "IN_PROGRESS" not in row["Week Status"].upper()),reverse=True)[:4]
    # Show the actual ongoing week as a separate fifth point. An approved
    # count of 0 is not evidence that the 3-report mail ingest is missing.
    progress_weeks=sorted((week for week,row in output.items()
                           if "IN_PROGRESS" in row["Week Status"].upper()),reverse=True)
    current_week=progress_weeks[0] if progress_weeks else None
    included=set(completed)
    if current_week:
        included.add(current_week)
    for week,row in output.items():
        label=quote_chart_week_label(week)
        if not label:
            raise SafeError("WEEKLY_CHART_INVALID_START")
        # ISO prefix makes the x-axis lexical group order identical to
        # chronological Friday week_start, including Dec/Jan year rollover.
        # Keep the familiar Oct W2/Nov W1 label as a readable suffix.
        row["Chart Week Label"]=week+" · "+label+(" · 진행 중" if week==current_week else "")
        row["Chart Window"]="RECENT_4_PLUS_CURRENT" if week in included else "HISTORY"
    return [output[k] for k in sorted(output,reverse=True)]

def prepare_data(sources,review=None):
    projects = project_rows(sources)
    return {
        "Monthly Tax Invoice":monthly_rows(sources),
        "Weekly Quote KPI":weekly_rows(sources,review=review),
        "Project SIF Monitor":projects,
        "Project Progress Board":prepare_project_board(sources,projects),
    }


def table_catalog(token,root):
    tables=list_all(root+"/tables",token,"metric_table_list")
    by_name=collections.defaultdict(list)
    for r in tables:
        if r.get("name"):by_name[r["name"]].append(r.get("table_id"))
    return by_name


def table_path(root,table_id):
    return root+"/tables/"+urllib.parse.quote(table_id,safe="")


# Source Base numeric display format governs chart labels. Keep raw numbers.
COUNT_FIELD_FORMATS={
    "Weekly Quote KPI":{
        "Approved Quote Count","Included Quote Count","Excluded Quote Count",
        "Active Unverified Quote Count","Created In Week Count",
        "Verified Amount Quote Count","Unmatched Amount Count",
        "Calculated Quote Count","Quote Amount Exception Count",
    },
    "Monthly Tax Invoice":{"Invoice Count","CSS Source Invoice Count"},
}
def ensure_integer_field_display(token,path,table,fields):
    targets=COUNT_FIELD_FORMATS.get(table,set())
    by_name={row.get("field_name"):row for row in fields}
    for name in sorted(targets):
        item=by_name.get(name)
        if not item or item.get("type")!=2 or not item.get("field_id"):
            raise SafeError("METRIC_NUMERIC_FORMAT_SOURCE_MISSING")
        prop=item.get("property") or {}
        if prop.get("formatter")=="0":continue
        # PUT is a full field-definition update; refuse non-numeric/UI types.
        if item.get("ui_type") not in (None,"Number"):
            raise SafeError("METRIC_NUMERIC_FORMAT_UI_TYPE_UNSAFE")
        data=api("PUT",path+"/fields/"+urllib.parse.quote(
                 item["field_id"],safe=""),token,
                 data={"field_name":name,"type":2,
                       "property":{"formatter":"0"}},
                 action="metric_integer_format_update")
        updated=data.get("field") or {}
        if updated.get("field_name")!=name or (
                updated.get("property") or {}).get("formatter")!="0":
            raise SafeError("METRIC_NUMERIC_FORMAT_UPDATE_UNVERIFIED")
        print("METRIC_INTEGER_FIELD_FORMAT_SET="+table+":"+name)
    if not targets:return
    verified={r.get("field_name"):r for r in
              list_all(path+"/fields",token,"metric_integer_format_readback")}
    if any((verified.get(name,{}).get("property") or {}).get("formatter")!="0"
           for name in targets):
        raise SafeError("METRIC_INTEGER_FIELD_FORMAT_READBACK_FAILED")


def ensure_tables(token,root):
    catalog=table_catalog(token,root)
    paths={}
    for name,spec in SCHEMAS.items():
        ids=catalog.get(name,[])
        if len(ids)>1:raise SafeError("DUPLICATE_METRIC_TABLE_"+name.replace(" ","_"))
        if not ids:
            api("POST",root+"/tables",token,data={"table":{
                "name":name,"default_view_name":("전체 Quote 목록"
                                                if name==QUOTE_REVIEW_TABLE else "All"),
                "fields":[{"field_name":f,"type":t} for f,t in spec],
            }},action="metric_create_table")
            catalog=table_catalog(token,root)
            ids=catalog.get(name,[])
            if len(ids)!=1:raise SafeError("METRIC_TABLE_CREATE_READBACK_FAILED")
            print("METRIC_TABLE_CREATED="+name)
        p=table_path(root,ids[0])
        fields=list_all(p+"/fields",token,"metric_schema")
        names={f.get("field_name"):f.get("type") for f in fields}
        allowed={
            "Project Display Name","Completion Evidence",
            "Workflow Lane","Payment State","Payment Owner Scope","Progress Phase","Invoice Gross KRW","Invoice Gross M KRW",
            "Outstanding Balance KRW","Outstanding Balance M KRW",*EVIDENCE_FIELDS,
        }
        for field_name,field_type in spec:
            if field_name in names:
                if names[field_name]!=field_type:
                    raise SafeError("METRIC_SCHEMA_TYPE_MISMATCH")
            elif (name=="Project Progress Board" and field_name in allowed) or (
                    name==QUOTE_REVIEW_TABLE and field_name in
                    {"Active Evidence Source","Active Evidence KST",
                     "Chart Window","기관","Opportunity","서비스·공정",
                     "샘플수(공정별)","참고 금액 K USD","참고 견적 USD","금액 근거"}) or (
                    name=="Weekly Quote KPI" and field_name in
                    {"Chart Week Label","Chart Window","Verified Quote Value M KRW FX",
                     "Included Quote Count","Excluded Quote Count",
                     "Active Unverified Quote Count","Active Coverage Status",
                     "Calculated Quote Count","Quote Amount Exception Count",
                     "Calculated Quote Value K USD","Calculated Quote Value M KRW FX",
                     "Quote Calculation Source"}) or (
                    name=="Monthly Tax Invoice" and field_name in
                    {"Net Revenue M KRW"}):
                api("POST",p+"/fields",token,
                    data={"field_name":field_name,"type":field_type},
                    action="metric_project_payment_field_add")
                print("METRIC_PAYMENT_FIELD_CREATED="+field_name)
            else:
                raise SafeError("METRIC_SCHEMA_UNEXPECTED_MISSING_FIELD")
        fields=list_all(p+"/fields",token,"metric_schema_readback")
        names={f.get("field_name"):f.get("type") for f in fields}
        if any(names.get(f)!=t for f,t in spec):
            raise SafeError("METRIC_SCHEMA_MISMATCH_"+name.replace(" ","_"))
        ensure_integer_field_display(token,p,name,fields)
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
        if v is None:
            if a=="":continue
            return False
        b=str(v).strip()
        if isinstance(v,(int,float)):
            x=numer(a)
            if x is not None and abs(x-D(str(v)))<D("0.00005"):continue
        if a!=b:return False
    return True


def board_list_with_retry(token,path,action):
    """Read-only bounded retry for transient Feishu list failures only."""
    for attempt in range(4):
        try:
            return list_all(path+"/records",token,action)
        except SafeError as exc:
            if not re.search(r"HTTP_(?:429|500|502|503|504)(?:$|[^0-9])",str(exc)) or attempt==3:
                raise
            # Keep a 503 from causing partial/false success or extra writes.
            print("PROJECT_BOARD_TRANSIENT_READ_RETRY attempt="+str(attempt+1))
            time.sleep(2*(attempt+1))


def sync_board_table(token,path,desired,payment_matches=None,billing_context=None):
    """Batch 25, source-owned upsert; independent readback of all project keys."""
    existing=board_list_with_retry(token,path,"project_board_existing")
    indexed={}
    for rec in existing:
        key=raw_value((rec.get("fields") or {}).get("Source Key")).strip()
        if not key:continue
        if key in indexed:raise SafeError("PROJECT_BOARD_DUPLICATE_RECORD")
        indexed[key]=rec
    creates=[];updates=[];unchanged=0
    final_rows=[]
    payment_matches=payment_matches or {}
    billing_context=billing_context or {}
    for raw in desired:
        row=dict(raw)
        key=row["Source Key"]
        old=indexed.get(key)
        original=old.get("fields") or {} if old else {}
        if "Completion Evidence" in row:
            pid=raw_value(row.get("AMEA")).upper()
            proof=payment_matches.get(pid)
            billing=billing_context.get(pid)
            if billing:
                row.update(billing)
            # Never overwrite a manually verified bank/ERP receipt with an
            # automatically matched spreadsheet receipt.
            manual=(raw_value(original.get("Receipt Verification Status"))=="VERIFIED"
                    and raw_value(original.get("Receipt Source")) in
                        {"BANK_RECEIPT","ERP_CASH_RECEIPT"})
            evidence=original if manual else (proof or original)
            if proof and not manual:
                row.update(proof)
            row=finalize(row,evidence)
        # Derive display-only M KRW; do not alter CMS/Receipt evidence.
        for raw_name,display_name in (
            ("Invoice Gross KRW","Invoice Gross M KRW"),
            ("Outstanding Balance KRW","Outstanding Balance M KRW"),
        ):
            if raw_name in row and row[raw_name] is not None and row[raw_name]!="":
                row[display_name]=scaled_m_krw(row[raw_name])
        final_rows.append(row)
        if old and equivalent(original,row):
            unchanged+=1
            continue
        fields={**row,"Last Sync KST":timestamp()}
        if old:
            rid=old.get("record_id")
            if not rid:raise SafeError("PROJECT_BOARD_MISSING_RECORD_ID")
            updates.append({"record_id":rid,"fields":fields})
        else:
            creates.append({"fields":fields})
    for verb,records in (("batch_create",creates),("batch_update",updates)):
        for start in range(0,len(records),25):
            chunk=records[start:start+25]
            result=api("POST",path+"/records/"+verb,token,
                       data={"records":chunk},action="project_board_"+verb)
            if len(result.get("records") or [])!=len(chunk):
                raise SafeError("PROJECT_BOARD_BATCH_WRITE_NOT_CONFIRMED")
    if final_rows and all("Workflow Lane" in r for r in final_rows):
        lanes=counts(final_rows)
        print("PROJECT_LANE_COUNTS active="+str(lanes["PRODUCTION_ACTIVE"])+
              " payment="+str(lanes["PAYMENT_FOLLOWUP"])+
              " archived="+str(lanes["PAID_ARCHIVED"]))
    if not creates and not updates:
        # All desired rows were individually compared with the initial live
        # Feishu listing. A second full scan only burns API quota and can 503.
        print("PROJECT_BOARD_SYNC_PASS desired="+str(len(desired))+
              " created=0 updated=0 unchanged="+str(unchanged)+" readback=EXISTING_VERIFIED")
        return 0,0,unchanged
    readback=board_list_with_retry(token,path,"project_board_readback")
    got={}
    for record in readback:
        key=raw_value((record.get("fields") or {}).get("Source Key")).strip()
        if not key:continue
        if key in got:raise SafeError("PROJECT_BOARD_READBACK_DUPLICATE")
        got[key]=record.get("fields") or {}
    for item in final_rows:
        if item["Source Key"] not in got or not equivalent(got[item["Source Key"]],item):
            raise SafeError("PROJECT_BOARD_READBACK_MISMATCH")
    print("PROJECT_BOARD_SYNC_PASS desired="+str(len(desired))+
          " created="+str(len(creates))+" updated="+str(len(updates))+
          " unchanged="+str(unchanged))
    return len(creates),len(updates),unchanged


def sync_table(token,path,desired,limit):
    existing=list_all(path+"/records",token,"metric_records")
    index={}
    for rec in existing:
        key=raw_value((rec.get("fields") or {}).get("Source Key")).strip()
        if not key:continue
        if key in index:raise SafeError("DUPLICATE_TARGET_SOURCE_KEY")
        index[key]=rec
    is_weekly_quote=bool(desired) and all(
        str(obj.get("Source Key","")).startswith("QUOTE:") for obj in desired)
    if is_weekly_quote:
        source_keys={obj["Source Key"] for obj in desired}
        orphans={key for key in index if key.startswith("QUOTE:")}-source_keys
        if orphans:
            print("QUOTE_KPI_ORPHAN_REVIEW count="+str(len(orphans))+
                  " policy=NO_AUTOMATIC_DELETE")
    created=updated=unchanged=0
    for obj in desired:
        key=obj["Source Key"]
        prev=index.get(key)
        if prev and equivalent(prev.get("fields") or {},obj):
            unchanged+=1
            continue
        if created+updated>=limit:break
        fields={**obj,"Last Sync KST":timestamp()}
        if prev:
            record_id=prev.get("record_id")
            if not record_id:raise SafeError("MISSING_TARGET_RECORD_ID")
            api("PUT",path+"/records/"+urllib.parse.quote(record_id,safe=""),token,
                data={"fields":fields},action="metric_record_update")
            updated+=1
        else:
            data=api("POST",path+"/records",token,data={"fields":fields},action="metric_record_create")
            rid=(data.get("record") or {}).get("record_id")
            if not rid:raise SafeError("METRIC_CREATE_RESPONSE_NO_RECORD_ID")
            created+=1
    if is_weekly_quote and (created or updated):
        records=board_list_with_retry(token,path,"quote_kpi_readback")
        seen={}
        for record in records:
            key=raw_value((record.get("fields") or {}).get("Source Key")).strip()
            if key.startswith("QUOTE:"):
                if key in seen:raise SafeError("QUOTE_KPI_DUPLICATE_READBACK")
                seen[key]=record.get("fields") or {}
        for obj in desired:
            if obj["Source Key"] not in seen or not equivalent(
                    seen[obj["Source Key"]],obj):
                raise SafeError("QUOTE_KPI_READBACK_MISMATCH")
        print("QUOTE_KPI_READBACK_PASS checked="+str(len(desired))+
              " missing_count="+str(sum(obj.get("Approved Quote Count") is None
                                       for obj in desired)))
    print("METRIC_SYNC_RESULT table="+re.sub(r"[^a-zA-Z]","_",path.split("/")[-1])+
          " created="+str(created)+" updated="+str(updated)+
          " unchanged="+str(unchanged)+" desired="+str(len(desired))+
          " bounded="+str(limit))
    return created,updated,unchanged



VIEW_SPECS = {
    "Project Progress Board": (
        ("프로젝트별 진행률", None, None),
        ("진행 중 프로젝트", "Workflow Lane", "PRODUCTION_ACTIVE"),
        ("완료 · 결제 관리", "Workflow Lane", "PAYMENT_FOLLOWUP", "Payment Owner Scope", "MY_VERIFIED"),
        ("결제 완료 · 보관", "Workflow Lane", "PAID_ARCHIVED", "Payment Owner Scope", "MY_VERIFIED"),
        ("Prepayment · SIF 면제", "SIF State", "WAIVED_PREPAYMENT"),
        ("Quote 원문 검토", "Quote Match State", "CSS_ORIGINAL_UNVERIFIED"),
    ),
    "Project SIF Monitor": (
        ("프로젝트 진행 · SIF", None, None),
        ("SIF 제출 미확인", "SIF State", "NOT_VERIFIED"),
        ("Prepayment · SIF 면제", "SIF State", "WAIVED_PREPAYMENT"),
        ("SIF 번호만 확인", "SIF State", "NUMBER_ONLY_REVIEW"),
        ("SIF 제출 증빙 있음", "SIF State", "SUBMITTED_EVIDENCE"),
        ("SIF 승인 완료", "SIF State", "APPROVED"),
    ),
    "Monthly Tax Invoice": (
        ("월별 Tax Invoice", None, None),
        ("Tax Invoice 원본 차이 검토", "Coverage Status", "SOURCE_SCOPE_REVIEW"),
    ),
    QUOTE_REVIEW_TABLE: QUOTE_REVIEW_VIEWS,
    "Weekly Quote KPI": (
        ("매주 Quote 건수 · 금액", None, None),
        ("견적 금액 미확인", "Amount Status", "NO_QUOTE_VALUE"),
        ("견적 금액 부분확인", "Amount Status", "VERIFIED_PARTIAL"),
    ),
}


def setup_views(token, paths):
    # All URLs are base-local and require Feishu sign-in.
    from setup_sales_web import resolve_view, get_view, field_map
    def matches(view, expected):
        info=((view.get("property") or {}).get("filter_info") or {})
        conditions=info.get("conditions") or []
        if info.get("conjunction")!="and" or len(conditions)!=len(expected):
            return False
        actual=set()
        for condition in conditions:
            try:vals=json.loads(condition.get("value") or "null")
            except (ValueError,TypeError):return False
            if condition.get("operator")!="is" or not isinstance(vals,list) or len(vals)!=1:
                return False
            actual.add((condition.get("field_id"),str(vals[0])))
        return actual==set(expected)
    for table, specs in VIEW_SPECS.items():
        path = paths[table]
        fields = field_map(token, path)
        for spec in specs:
            name=spec[0]
            pairs=list(zip(spec[1::2],spec[2::2]))
            filtered=bool(pairs and pairs[0][0])
            view_id, _ = resolve_view(token, path, name, filtered)
            view = get_view(token, path, view_id)
            if filtered:
                expected=[]
                for field_name,target in pairs:
                    field_id=fields.get(field_name)
                    if not field_id:raise SafeError("VIEW_FILTER_FIELD_MISSING")
                    expected.append((field_id,str(target)))
                if not (view.get("view_name")==name and matches(view,expected)):
                    api("PATCH",path+"/views/"+urllib.parse.quote(view_id,safe=""),token,
                        data={"view_name":name,"property":{"filter_info":{
                            "conjunction":"and","conditions":[{
                                "field_id":fid,"operator":"is",
                                "value":json.dumps([val],ensure_ascii=False)
                            } for fid,val in expected],
                        }}},action="metric_view_filter_patch")
                    view=get_view(token,path,view_id)
                    if not (view.get("view_name")==name and matches(view,expected)):
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
    scope=os.environ.get("FEISHU_METRIC_SCOPE","all").strip().lower()
    if scope not in ("all","quote","operations"):
        raise SafeError("INVALID_METRIC_SCOPE")
    sources=sheet_sources()  # Fetch all required source evidence before writing.
    if scope in ("all","quote"):
        # Never mutate the canonical Sheet. Exact recent approval mail rows
        # are reconciled in memory with authenticated QQ Report + owner proof.
        effective,_=reconcile_mail_approvals(sources)
        sources["Quote Approval Dedup"]=effective
    if scope=="operations":
        projects=project_rows(sources)
        output={"Project SIF Monitor":projects,
                "Project Progress Board":prepare_project_board(sources,projects)}
    elif scope=="quote":
        # The 17:00 Salesforce Quote report is independent of Revenue.
        # Never call monthly_rows/Revenue canonical authority in Quote-only mode.
        output={"Weekly Quote KPI":weekly_rows(sources)}
    else:
        output=prepare_data(sources)
    print("METRIC_SCOPE="+scope+" source_integrity=VERIFIED",flush=True)
    for q in output.get("Weekly Quote KPI",[]):
        if q.get("Chart Window")!="RECENT_4_PLUS_CURRENT":
            continue
        print("QUOTE_PROCESS_WEEK_RECALC week="+q["Week Start"]+
              " approved="+str(q["Approved Quote Count"])+
              " calculated="+str(q["Calculated Quote Count"])+
              " exception="+str(q["Quote Amount Exception Count"])+
              " k_usd="+str(q.get("Calculated Quote Value K USD"))+
              " m_krw="+str(q.get("Calculated Quote Value M KRW FX"))+
              " status="+q["Quote Calculation Source"])
    matched=billing=None
    if scope!="quote":
        matched,billing,audit=build_payment_evidence(
            sources,sources.get("Feishu Source Manifest",[]))
        print("PAYMENT_SNAPSHOT_AUDIT projects_with_invoices="+
              str(audit["projects_with_invoices"])+
              " projects_source_receipt_complete="+
              str(audit["projects_source_receipt_complete"])+
              " my_verified="+str(audit["my_verified_invoice_projects"])+
              " other_sales="+str(audit["other_sales_invoice_projects"])+
              " owner_review="+str(audit["owner_review_projects"])+
              " review_required="+str(audit["projects_review_required"]))
    for name,items in output.items():
        print("METRIC_SOURCE_READY="+name+" rows="+str(len(items)))
    if mode=="plan":
        print("METRIC_PLAN_PASS scope="+scope+" writes=0")
        return
    token,root=auth()
    paths=ensure_tables(token,root)
    if scope!="operations":
        existing_review=board_list_with_retry(
            token,paths[QUOTE_REVIEW_TABLE],"weekly_review_existing")
        overrides=quote_manual_overrides(existing_review)
        review=build_quote_review(sources,overrides,now=dt.datetime.now(KST))
        output["Weekly Quote KPI"]=weekly_rows(sources,review=review)
    setup_views(token,paths)
    if scope!="operations":
        review_flags=sync_quote_review(
            token,paths[QUOTE_REVIEW_TABLE],review,existing_review,timestamp())
        if any(overrides.get(r["Source Key"],False)!=
               review_flags.get(r["Source Key"],False) for r in review):
            raise SafeError("WEEKLY_REVIEW_OVERRIDE_CONFLICT_BEFORE_KPI")
    bounds={"Monthly Tax Invoice":50,"Weekly Quote KPI":120,"Project SIF Monitor":70}
    total=0
    if scope!="quote":
        board=sync_board_table(token,paths["Project Progress Board"],
                               output["Project Progress Board"],matched,billing)
        total+=sum(board[:2])
    targets={
        "quote":("Weekly Quote KPI",),
        "operations":("Project SIF Monitor",),
        "all":("Monthly Tax Invoice","Weekly Quote KPI","Project SIF Monitor"),
    }[scope]
    for name in targets:
        result=sync_table(token,paths[name],output[name],bounds[name])
        total+=sum(result[:2])
    print("FEISHU_SALES_METRIC_APPLY_PASS scope="+scope+
          " record_writes="+str(total)+" all_other_feishu_bases_writes=0")

if __name__=="__main__":
    try:main()
    except Exception as exc:
        reason=str(exc) if isinstance(exc,SafeError) else type(exc).__name__
        print("FEISHU_SALES_METRIC_FAILED:"+reason,file=sys.stderr)
        sys.exit(1)
