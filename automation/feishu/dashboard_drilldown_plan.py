#!/usr/bin/env python3
"""Read-only chart member reconciliation and reversible analysis selection.

Official financial/project status, existing graphs, source rows and owner
scope never change. The prospective Revenue review table is not created by
this module. No row payload or amount is emitted to Actions logs.
"""
import copy
import datetime as dt
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import json
import re
import sys
from zoneinfo import ZoneInfo

from monthly_revenue_canonical import evidence_rows, RevenueEvidenceError

KST = ZoneInfo("Asia/Seoul")
REVIEW = "Revenue Invoice Review"
INCLUSION = "VERIFIED_MONTH_MEMBER"
EXCLUDE = "합산 제외"
EXTRACT = "CSS Tax Invoice Extract"
NET = "BI Revenue Net VAT Monthly"
LIFE = "BI Revenue Lifecycle Monthly"
AUTH = "Revenue Source Authority"
LEGACY = "Revenue Invoice Base"
CANONICAL_START = "2026-10"
ALLOWED = {"FILENAME_PARSED","VERIFIED_LEGACY_FILENAME","EXISTS_IN_LEGACY"}
NOTICE = re.compile(r"^\s*❗?\ufe0f?\s*Notice:\s*Invoice Issued\s*&\s*Statement Confirmed\b",re.I)
REPLY = re.compile(r"^\s*(?:re|fw|fwd|회신|답장|전달)\s*[:：]",re.I)
FILENAME = re.compile(
    r"TAX\s+INVOICE[-_ ]+(\d{8,15})[-_ ]+(H\d{3}SC\d{5,}|H\d{5,})[-_ ]+([A-Za-z0-9]+)"
    r"[-_ ]+(AMEA\d{7,}(?:-\d{1,3})?)[-_ ]+KRW\s*([0-9]+(?:\.[0-9]{1,2})?)\.pdf",re.I)
MONTH = re.compile(r"20\d\d-(?:0[1-9]|1[0-2])")
SCHEMAS = {
    EXTRACT: ("CSS", 5000, ("invoice_number","amount_krw","project_id","h_project_number",
                            "po_reference","attachment_filename","subject","received_at",
                            "imap_uid","ingest_key","validation_status","extracted_at_utc")),
    NET: ("UNIFIED", 5000, ("Month","Issued Invoice Gross KRW (VAT incl)",
                            "Issued Net Revenue KRW (VAT excl)","Issued Invoice Count",
                            "Issued Net Revenue kUSD @1500","Verified At KST","Evidence State")),
    LIFE: ("UNIFIED", 5000, ("Month","Actual Invoice KRW","Invoice Count")),
    AUTH: ("UNIFIED", 5000, ("Month","Source Tab","Source Role","Issued Invoice Count","Amount KRW",
                             "Tax Basis","Source Parity","Authoritative For KPI","Verified KST")),
    LEGACY: ("UNIFIED", 10000, ("Invoice No","Year-Month","Revenue KRW (Tax Invoice)",
                              "Net Revenue KRW (VAT excl; per invoice)","AMEA ID","H Project ID")),
}


class DrilldownError(RuntimeError):
    pass


def text(row, key):
    raw = row.get(key)
    return "" if raw is None else str(raw).strip()


def won(raw, optional=False):
    s = str(raw if raw is not None else "").replace(",","").replace("₩","").strip()
    if not s and optional:
        return None
    try:
        n = Decimal(s)
    except InvalidOperation:
        raise DrilldownError("DRILLDOWN_INVALID_KRW") from None
    if not n.is_finite() or n < 0 or n != n.to_integral_value():
        raise DrilldownError("DRILLDOWN_INVALID_KRW")
    return int(n)


def net_won(gross):
    return int((Decimal(gross)*10/11).quantize(Decimal("1"),rounding=ROUND_HALF_UP))


def issue_month(raw):
    try:
        stamp = dt.datetime.fromisoformat(raw.replace("Z","+00:00"))
    except ValueError:
        raise DrilldownError("DRILLDOWN_INVALID_RECEIPT_DATE") from None
    if stamp.tzinfo is None:
        raise DrilldownError("DRILLDOWN_UNZONED_RECEIPT_DATE")
    return stamp.astimezone(KST).strftime("%Y-%m")


def members_from_extract(rows):
    """Mirror the existing revenue_net_vat_publish admission/rounding rules.

    The exact row source is CSS Tax Invoice Extract; filename/subject/UID
    checks reproduce the publication evidence, not independent MIME proof.
    Additional AMEA/H/PO disagreement is preserved as a review signal.
    No source from Outstanding, Receipt, eTax, forecast or manual ERP enters.
    """
    by_id = {}
    rejected = Counter()
    for row in rows:
        ident = text(row,"invoice_number")
        subject = text(row,"subject")
        if (not re.fullmatch(r"209126\d{6}",ident) or
                text(row,"validation_status") not in ALLOWED or
                REPLY.match(subject) or not NOTICE.match(subject)):
            rejected["NOT_CANONICAL_ISSUED_NOTICE"] += 1
            continue
        # Fail closed on a row that meets the original publication admission
        # but has invalid filename/amount/date. Never just omit that member.
        f = FILENAME.search(re.sub(r"\s+"," ",text(row,"attachment_filename")))
        if not f or f.group(1)!=ident:
            raise DrilldownError("DRILLDOWN_FILENAME_REFERENCE_MISMATCH")
        gross = won(text(row,"amount_krw"))
        if gross<=0 or won(f.group(5))!=gross or not text(row,"imap_uid"):
            raise DrilldownError("DRILLDOWN_FILENAME_AMOUNT_UID_MISMATCH")
        month = issue_month(text(row,"received_at"))
        evidence = {
            "Invoice No":ident, "Month":month, "Gross KRW":gross,
            "Net KRW":net_won(gross), "AMEA":f.group(4).upper(),
            "H Contract":f.group(2).upper(), "PO Reference":f.group(3),
            "Source Table":EXTRACT, "Source Key":"REVENUE_MEMBER:"+ident,
            "Evidence State":"FILENAME_NOTICE_UID_OBSERVED",
            "Reference Review":any(text(row,col).upper()!=v.upper()
                for col,v in (("project_id",f.group(4)),("h_project_number",f.group(2)),
                              ("po_reference",f.group(3)))),
        }
        if ident in by_id:
            old = by_id[ident]
            if any(old[k]!=evidence[k] for k in ("Month","Gross KRW","Net KRW","AMEA","H Contract","PO Reference")):
                raise DrilldownError("DRILLDOWN_DUPLICATE_MEMBER_CONFLICT")
            old["Reference Review"] = old["Reference Review"] or evidence["Reference Review"]
            rejected["REPEATED_IDENTICAL_MEMBER"] += 1
        else:
            by_id[ident] = evidence
    return by_id,dict(rejected)


def member_totals(rows, excluded=()):
    """Separate original membership and scenario selection; no mutation.

    Unknown money is never a verified zero. A rejected/nonmember or
    unrecognized key cannot be toggled into the aggregate.
    """
    rows=list(rows)
    by={}
    for r in rows:
        k=text(r,"Source Key")
        if not k or k in by:
            raise DrilldownError("DRILLDOWN_MEMBER_KEY_INVALID_OR_DUPLICATE")
        by[k]=r
    omitted=set(excluded)
    if not omitted <= by.keys():
        raise DrilldownError("DRILLDOWN_EXCLUSION_OUTSIDE_MEMBERSHIP")
    def totals(rs):
        rs=list(rs)
        g=[won(r.get("Gross KRW"),optional=True) for r in rs]
        n=[won(r.get("Net KRW"),optional=True) for r in rs]
        return {"count":len(rs),"gross_known_krw":sum(x for x in g if x is not None),
                "net_known_krw":sum(x for x in n if x is not None),
                "gross_unknown_count":sum(x is None for x in g),
                "net_unknown_count":sum(x is None for x in n)}
    return {"original":totals(by.values()),"excluded":totals(by[k] for k in omitted),
            "selected":totals(r for k,r in by.items() if k not in omitted)}


def monthly_index(rows, source):
    result={}
    for r in rows:
        m=text(r,"Month")
        if not MONTH.fullmatch(m) or m in result:
            raise DrilldownError("DRILLDOWN_MONTH_KEY_INVALID_OR_DUPLICATE")
        result[m]=r
    return result


def plan(source):
    if set(source)!=set(SCHEMAS):
        raise DrilldownError("DRILLDOWN_SOURCE_SET_INCOMPLETE")
    for tab,(_,_,fields) in SCHEMAS.items():
        if any(not set(fields)<=row.keys() for row in source[tab]):
            raise DrilldownError("DRILLDOWN_SOURCE_SCHEMA_MISMATCH")
    members, rejected = members_from_extract(source[EXTRACT])
    bymonth=defaultdict(list)
    for member in members.values():
        bymonth[member["Month"]].append(member)
    net=monthly_index(source[NET],NET)
    life=monthly_index(source[LIFE],LIFE)
    legacy={}
    for row in source[LEGACY]:
        ident=text(row,"Invoice No")
        if ident:
            legacy.setdefault(ident,[]).append(row)
    # Older charts may have legacy/manual input. Membership is NOT certified
    # from a legacy ID match or from a month aggregate.
    legacy_months={text(r,"Year-Month") for r in source[LEGACY] if MONTH.fullmatch(text(r,"Year-Month"))}
    months=sorted(set(net)|set(bymonth)|legacy_months)
    summaries={}
    ready={}
    for month in months:
        rows=bymonth[month]
        actual=member_totals(rows)["original"]
        if month < CANONICAL_START:
            summaries[month]={"state":"HISTORICAL_MEMBER_AUTHORITY_NOT_ATTESTED",
                              "observed_extract_members":actual["count"]}
            continue
        row=net.get(month)
        if row is None:
            summaries[month]={"state":"NO_PUBLISHED_CANONICAL_MONTH",
                              "observed_extract_members":actual["count"]}
            continue
        count=won(row.get("Issued Invoice Count"))
        gross=won(row.get("Issued Invoice Gross KRW (VAT incl)"))
        net_w=won(row.get("Issued Net Revenue KRW (VAT excl)"))
        parity={"count":actual["count"]==count,
                "gross":actual["gross_known_krw"]==gross,
                "net":actual["net_known_krw"]==net_w}
        if count==gross==net_w==0:
            state="NO_ISSUED_POINT" if not rows else "SOURCE_MEMBER_PARITY_REVIEW"
            authority=False
        else:
            try:
                confirmed=evidence_rows({NET:[row],LIFE:[life[month]] if month in life else [],
                                        AUTH:[r for r in source[AUTH] if text(r,"Month")==month]})
                authority=(len(confirmed)==1 and confirmed[0]["Month"]==month)
            except RevenueEvidenceError:
                authority=False
            state=("SOURCE_MEMBER_PARITY_REVIEW" if not all(parity.values()) else
                   "AUTHORITY_REVIEW" if not authority else
                   "VERIFIED_PUBLISHED_MONTH_MEMBERS")
        summaries[month]={"state":state,"observed_extract_members":actual["count"],
                          "published_members":count,"member_parity":parity,"authority_parity":authority,
                          "source_reference_review_members":sum(r["Reference Review"] for r in rows)}
        if state=="VERIFIED_PUBLISHED_MONTH_MEMBERS":
            ready[month]=[{**r,"Membership State":INCLUSION,"Count Unit":1} for r in rows]
    return {"months":summaries,"extract_unique_members":len(members),
            "legacy_unique_invoice_references":len(legacy),
            "extract_legacy_identity_overlap":len(members.keys() & legacy.keys()),
            "legacy_duplicate_identity_groups":sum(len(x)>1 for x in legacy.values()),
            "extract_exclusions":rejected,
            "verified_review_members":sum(len(v) for v in ready.values()),
            "business_writes":0,"historical_revenue_certification":"NOT_ATTESTED",
            "original_mail_mime_verification":"NOT_ATTESTED_BY_THIS_AUDIT"},ready


def review_chart_config(metric="Net KRW", filtered=True):
    """Prospective native chart. Only verified member rows; no apply action.

    Use exact whole KRW rather than summing independently rounded display
    millions. Count and money remain separate series/units.
    """
    if metric not in ("Count Unit","Net KRW","Gross KRW"):
        raise DrilldownError("DRILLDOWN_UNSUPPORTED_METRIC")
    conditions=[{"field_name":"Membership State","operator":"is","value":INCLUSION}]
    if filtered:
        conditions.append({"field_name":EXCLUDE,"operator":"is","value":False})
    return {"table_name":REVIEW,"series":[{"field_name":metric,"rollup":"SUM"}],
            "group_by":[{"field_name":"Month","mode":"integrated",
                         "sort":{"type":"group","order":"asc"}}],
            "filter":{"conjunction":"and","conditions":conditions}}


def analysis_config(original, field="분석 제외"):
    """Copy a native row-backed project/payment chart into a scenario view.

    Original policy filters (including owner and lane) are retained. No
    filter is weakened. Monthly aggregate tables cannot be drilled to
    invoice members by appending a checkbox to a month row.
    """
    if original.get("table_name")!="Project Progress Board":
        raise DrilldownError("DRILLDOWN_NOT_PROJECT_MEMBER_SOURCE")
    result=copy.deepcopy(original)
    filt=result.setdefault("filter",{"conjunction":"and","conditions":[]})
    if filt.get("conjunction")!="and" or not isinstance(filt.get("conditions"),list):
        raise DrilldownError("DRILLDOWN_FILTER_NOT_SUPPORTED")
    if any(c.get("field_name")==field for c in filt["conditions"]):
        raise DrilldownError("DRILLDOWN_EXCLUSION_ALREADY_CONFIGURED")
    filt["conditions"].append({"field_name":field,"operator":"is","value":False})
    return result


def read_sources(session):
    from sales_metrics_sync import CSS_SHEET, UNIFIED_SHEET, req_sheet
    books={"CSS":CSS_SHEET,"UNIFIED":UNIFIED_SHEET}
    catalogs={}
    for name,book in books.items():
        response=session.get("https://sheets.googleapis.com/v4/spreadsheets/"+book+
            "?fields=spreadsheetId,sheets(properties(title,sheetId,gridProperties))",timeout=45)
        if not response.ok:
            raise DrilldownError("DRILLDOWN_CATALOG_READ_FAILED")
        data=response.json()
        if data.get("spreadsheetId")!=book:
            raise DrilldownError("DRILLDOWN_CATALOG_ID_MISMATCH")
        props=[s.get("properties",{}) for s in data.get("sheets",[])]
        if len({p.get("title") for p in props})!=len(props):
            raise DrilldownError("DRILLDOWN_CATALOG_DUPLICATE_TITLE")
        catalogs[name]={p.get("title"):p for p in props}
    out={}
    for name,(book,maxrows,fields) in SCHEMAS.items():
        p=catalogs[book].get(name)
        if not p:
            raise DrilldownError("DRILLDOWN_REQUIRED_TAB_MISSING")
        g=p.get("gridProperties",{})
        n,w=g.get("rowCount"),g.get("columnCount")
        if type(n)!=int or type(w)!=int or not 2<=n<=maxrows or not 1<=w<=52:
            raise DrilldownError("DRILLDOWN_SOURCE_GRID_BOUND")
        rows=req_sheet(session,books[book],name,n)
        if not rows or len(rows)>=n or any(not set(fields)<=r.keys() for r in rows):
            raise DrilldownError("DRILLDOWN_SOURCE_SCHEMA_OR_BOUND")
        out[name]=rows
    return out


def main():
    from sales_metrics_sync import sheets_session
    summary,_=plan(read_sources(sheets_session()))
    # No IDs, amounts, filenames, customer names or row-level details.
    print("CHART_DRILLDOWN_PLAN "+json.dumps(summary,sort_keys=True))
    print("CHART_DRILLDOWN_READ_ONLY business_writes=0")


if __name__=="__main__":
    try:
        main()
    except Exception as exc:
        print("CHART_DRILLDOWN_PLAN_FAILED "+(str(exc) if isinstance(exc,DrilldownError)
                                               else type(exc).__name__),file=sys.stderr)
        sys.exit(1)
