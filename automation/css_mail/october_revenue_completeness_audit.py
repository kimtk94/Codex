#!/usr/bin/env python3
"""Read-only October issued-invoice completeness audit across QQ and eTax.

QQ 'received_at' is an evidence-collection date, not an accounting GL date.
eTax sales label and GL date are not certified owner or issuance evidence.
This audit NEVER changes financial tables or automatically includes manual,
gap, or other-sales invoice candidates.
"""
import datetime as dt
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
import os
import re
import sys
from zoneinfo import ZoneInfo

from tax_invoice_extract import extract
from unified_followup_sync import SRC, DST, get
import incremental_sync as css

KST=ZoneInfo("Asia/Seoul")
OCT="2026-10"
ALLOWED={"FILENAME_PARSED","VERIFIED_LEGACY_FILENAME","EXISTS_IN_LEGACY"}
NOTICE=re.compile(r"^\s*❗?\ufe0f?\s*Notice:\s*Invoice Issued\s*&\s*Statement Confirmed\b",re.I)
REPLY=re.compile(r"^\s*(?:re|fw|fwd|회신|답장|전달)\s*[:：]",re.I)
XNUMBER=re.compile(r"(J\d{3})-(X\d+SC\d+-Z\d+)",re.I)


def cell(row,i):
    return str(row[i]).strip() if len(row)>i and row[i] is not None else ""


def won(value):
    try:
        result=Decimal(str(value).replace(",","").replace("₩","").strip())
        if not result.is_finite() or result!=result.to_integral_value() or result<=0:
            raise ValueError("INVALID_GROSS_KRW")
        return int(result)
    except Exception as exc:
        raise ValueError("INVALID_GROSS_KRW") from exc


def net_won(gross):
    return int((Decimal(gross)*Decimal(10)/Decimal(11)).quantize(
        Decimal("1"),rounding=ROUND_HALF_UP))


def kst_month(received):
    when=dt.datetime.fromisoformat(received.replace("Z","+00:00"))
    if when.tzinfo is None:raise ValueError("UNZONED_QQ_MAIL_RECEIVED_DATE")
    return when.astimezone(KST).strftime("%Y-%m")


def gl_month(serial):
    """Only a source period hint; NEVER proof an invoice was issued."""
    n=int(str(serial).strip())
    if not 44000<n<47000:raise ValueError("INVALID_GL_DATE")
    return (dt.datetime(1899,12,30)+dt.timedelta(days=n)).strftime("%Y-%m")


def qq_original_october(rows):
    if not rows or cell(rows[0],0)!="invoice_number":
        raise ValueError("QQ_INVOICE_SOURCE_SCHEMA_MISMATCH")
    found={}
    for row in rows[1:]:
        invoice=cell(row,0)
        if not re.fullmatch(r"209126\d{6}",invoice) or cell(row,10) not in ALLOWED:
            continue
        subject=cell(row,6)
        if REPLY.match(subject) or not NOTICE.match(subject):continue
        p=extract(cell(row,5))
        if not p or p[0]!=invoice or p[4] is None:raise ValueError("QQ_FILENAME_INVALID_"+invoice)
        amount=won(cell(row,1))
        if amount!=p[4] or not cell(row,8):raise ValueError("QQ_GROSS_OR_UID_CONFLICT_"+invoice)
        if kst_month(cell(row,7))!=OCT:continue
        x=XNUMBER.search(subject)
        if not x:raise ValueError("QQ_MISSING_PROJECT_STATEMENT_"+invoice)
        record={"gross":amount,"net":net_won(amount),
                "project":x.group(2).upper().split("-")[0],
                "ameax":p[3],"email_received":cell(row,7),
                "attachment_status":cell(row,10)}
        if invoice in found and record!=found[invoice]:
            raise ValueError("QQ_DUPLICATE_INVOICE_CONFLICT_"+invoice)
        found[invoice]=record
    if not found:raise ValueError("QQ_OCT_ISSUED_EMPTY")
    return found


def etax_evidence(rows,qq,sales="Kim Taehoon"):
    if not rows or cell(rows[0],4)!="ERP Invoice Number" or cell(rows[0],25)!="Sales":
        raise ValueError("ETAX_SOURCE_SCHEMA_MISMATCH")
    by_cms={}
    manual_candidates=[]
    all_manual=[]
    for row in rows[1:]:
        if cell(row,25)!=sales:continue
        gross=won(cell(row,15))
        cms=cell(row,5)
        erp=cell(row,4)
        project=cell(row,9).upper().split("-")[0]
        if cms:
            if cms in by_cms:raise ValueError("ETAX_DUPLICATE_CMS_KEY")
            by_cms[cms]={"gross":gross,"erp":erp,"project":project,
                         "gl_month":gl_month(cell(row,16))}
        elif cell(row,2)=="Manual Invoice":
            r={"erp":erp,"gross":gross,"net":net_won(gross),
               "project":project,"gl_month":gl_month(cell(row,16))}
            all_manual.append(r)
            if r["gl_month"]==OCT:
                manual_candidates.append(r)
    exact=set()
    wrong=[]
    conflicting_period=[]
    for invoice,detail in qq.items():
        evidence=by_cms.get(invoice)
        if not evidence:continue
        if evidence["gross"]!=detail["gross"] or evidence["project"]!=detail["project"]:
            wrong.append(invoice)
        else:
            exact.add(invoice)
            if evidence["gl_month"]!=OCT:
                conflicting_period.append(invoice)
    if wrong:raise ValueError("ETAX_QQ_ID_GROSS_PROJECT_CONFLICT_"+",".join(wrong))
    duals=[]
    for manual in all_manual:
        for invoice,detail in qq.items():
            if manual["project"]==detail["project"] and manual["gross"]==detail["gross"]:
                duals.append({"erp":manual["erp"],"qq_invoice":invoice,
                              "gross":manual["gross"],"gl_month":manual["gl_month"]})
    return {"matched_qq":exact,"not_in_etax":sorted(set(qq)-exact),
            "gl_mismatch":sorted(conflicting_period),
            "manual_candidates":manual_candidates,"possible_double":duals}


def gap_evidence(rows,qq):
    if not rows or cell(rows[0],0)!="Invoice Number":
        raise ValueError("GAP_SOURCE_SCHEMA_MISMATCH")
    candidates={}
    for row in rows[1:]:
        invoice=cell(row,0)
        if cell(row,1)!=OCT or invoice in qq:continue
        if not re.fullmatch(r"209126\d{6}",invoice):
            raise ValueError("GAP_INVOICE_KEY_INVALID")
        gross=won(cell(row,2))
        if invoice in candidates and candidates[invoice]!=gross:
            raise ValueError("GAP_DUPLICATE_INVOICE_GROSS_CONFLICT")
        candidates[invoice]=gross
    return candidates


def audit(qq_rows,etax_rows,gap_rows):
    qq=qq_original_october(qq_rows)
    et=etax_evidence(etax_rows,qq)
    gap=gap_evidence(gap_rows,qq)
    qq_gross=sum(x["gross"] for x in qq.values())
    qq_net=sum(x["net"] for x in qq.values())
    manual_gross=sum(x["gross"] for x in et["manual_candidates"])
    manual_net=sum(x["net"] for x in et["manual_candidates"])
    gap_gross=sum(gap.values())
    gap_net=sum(net_won(x) for x in gap.values())
    if qq_gross<qq_net:raise ValueError("QQ_NET_GREATER_THAN_GROSS")
    review=bool(manual_gross or gap_gross or et["not_in_etax"]
                or et["gl_mismatch"] or et["possible_double"])
    report={
        "status":"REVIEW_REQUIRED" if review else "COMPLETE_SOURCE_SCOPE",
        "qq_count":len(qq),"qq_gross":qq_gross,"qq_net":qq_net,
        "etax_qq_exact_match":len(et["matched_qq"]),
        "etax_qq_unmatched":et["not_in_etax"],
        "etax_gl_period_mismatch":et["gl_mismatch"],
        "manual_candidate_count":len(et["manual_candidates"]),
        "manual_candidate_gross":manual_gross,
        "manual_candidate_net":manual_net,
        "manual_erp_ids":[x["erp"] for x in et["manual_candidates"]],
        "possible_double":et["possible_double"],
        "gap_candidate_count":len(gap),"gap_candidate_gross":gap_gross,
        "gap_candidate_net":gap_net,"gap_invoice_ids":sorted(gap),
        "hypothetical_if_manual_verified_net":qq_net+manual_net,
    }
    return report


def main():
    session=css.authorize()
    qq=get(session,SRC,"CSS Tax Invoice Extract","A1:L1000")
    etax=get(session,DST,"Feishu Latest eTax","A1:AZ200")
    gaps=get(session,DST,"CSS Invoice Gap Review","A1:L120")
    a=audit(qq,etax,gaps)
    print("OCT_REVENUE_AUDIT_STATUS="+a["status"]+
          " basis=QQ_RECEIVED_MONTH_NOT_ERP_GL_OR_ACCOUNTING_RECOGNITION",flush=True)
    print("OCT_REVENUE_QQ_VALIDATED invoices="+str(a["qq_count"])+
          " gross_krw="+str(a["qq_gross"])+" net_krw="+str(a["qq_net"]),flush=True)
    print("OCT_REVENUE_ETAX_CMS_CROSSMATCH exact="+str(a["etax_qq_exact_match"])+
          " unmatched="+",".join(a["etax_qq_unmatched"])+
          " gl_period_mismatch_count="+str(len(a["etax_gl_period_mismatch"])),flush=True)
    print("OCT_REVENUE_MANUAL_REVIEW candidates="+str(a["manual_candidate_count"])+
          " gross_krw="+str(a["manual_candidate_gross"])+
          " net_krw="+str(a["manual_candidate_net"])+
          " erp_ids="+",".join(a["manual_erp_ids"])+
          " issuance=NOT_INDEPENDENTLY_VERIFIED",flush=True)
    print("OCT_REVENUE_POSSIBLE_DOUBLE_COUNT review="+str(len(a["possible_double"]))+
          " entries="+str(a["possible_double"]),flush=True)
    print("OCT_REVENUE_QQ_GAP_NOT_ADDED count="+str(a["gap_candidate_count"])+
          " gross_krw="+str(a["gap_candidate_gross"])+
          " net_krw="+str(a["gap_candidate_net"])+
          " ids="+",".join(a["gap_invoice_ids"])+
          " owner=UNVERIFIED",flush=True)
    print("OCT_REVENUE_CONDITIONAL_NET_NOT_ACTUAL="+
          str(a["hypothetical_if_manual_verified_net"])+
          " conditions=MANUAL_ISSUANCE_AND_OWNER_AND_DEDUP_EVIDENCE_REQUIRED",flush=True)
    print("OCT_REVENUE_MUTATIONS=0 original_mail=UNCHANGED financial_actual=UNCHANGED",
          flush=True)


if __name__=="__main__":
    try:
        main()
    except Exception as exc:
        print("OCT_REVENUE_AUDIT_FAILED="+type(exc).__name__+":"+str(exc),file=sys.stderr)
        sys.exit(1)
