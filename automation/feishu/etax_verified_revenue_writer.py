#!/usr/bin/env python3
"""Evidence-gated one-certificate October manual ERP issued-Revenue source row.

The Feishu Monthly Tax Invoice base already contains October QQ/CMS 48-invoice
subtotal under INVOICE:2026-10. This writes a *different* stable Source Key for
a single original Korean eTax certificate with two ERP component rows. The
native chart SUMs both source rows by Month. It never rewrites the canonical
QQ subtotal, Source Authority audit, Pending, Forecast, customer records or
ERP/QQ source data. This is issued invoice tracking, NOT IFRS 15 accrual or cash.
"""
import decimal
import os
import sys

from qq_mail_ingest import auth,list_all,SafeError
from etax_original_tracking_proof import read_tracking,build_index,scalar
from etax_h_semantics_audit import find_sheet,row_read
from etax_grouped_manual_invoice_audit import evidence,TARGETS,date_hint
from monthly_revenue_actual_sync import index_records,safe_existing_fields
from sales_metrics_sync import (
    CSS_SHEET,UNIFIED_SHEET,EXPECTED_BASE,SCHEMAS,
    req_sheet,sheets_session,table_catalog,table_path,
    raw_value,numer,equivalent,sync_table,
)

MONTH="2026-10"
AMEA="AMEA2026090309"
X="X209SC26107211"
OPP="Opp-2026-09-03-282202"
QID="QID-2026-10-19-407028"
MANUAL_KEY="ERP_ETAX:2026-10:20910000208+20910000209"
QQ_KEY="INVOICE:2026-10"
EXPECTED_QQ_NET=144129000
EXPECTED_QQ_GROSS=158541900
EXPECTED_QQ_COUNT=48
EXPECTED_MANUAL_NET=9640000
EXPECTED_MANUAL_GROSS=10604000
EXPECTED_COMBINED_NET=153769000
EXPECTED_COMBINED_GROSS=169145900
EXPECTED_COMBINED_COUNT=49
REPORTING_FX=decimal.Decimal("1500")


def v(row,name):
    return str(row.get(name) or "").strip()


def require_unique(rows,predicate,error):
    hits=[row for row in rows if predicate(row)]
    if len(hits)!=1:
        raise SafeError(error+":"+str(len(hits)))
    return hits[0]


def check_source_spreadsheets(source):
    """Four different live source snapshots, all matched on immutable IDs."""
    needed=("Feishu Latest eTax","SFDC Quote Export",
            "SFDC Email Opportunities Raw","CSS Tax Invoice Extract")
    if any(not source.get(name) for name in needed):
        raise SafeError("MANUAL_ETAX_REQUIRED_SOURCE_MISSING")
    etax=source["Feishu Latest eTax"]
    source_records=[]
    for erp,gross in TARGETS.items():
        rec=require_unique(etax,lambda x:v(x,"ERP Invoice Number")==erp,
                           "MANUAL_ETAX_DUPLICATE_OR_MISSING_ERP_"+erp)
        if (v(rec,"Source")!="Manual Invoice" or
                v(rec,"Org Name")!="Novogene KR" or
                v(rec,"Currency")!="KRW" or
                v(rec,"Quotation Number")!=AMEA or
                v(rec,"Project Number")!=X or
                v(rec,"CMS Invoice Num") or
                v(rec,"Sales")!="Kim Taehoon" or
                numer(v(rec,"Amount"),strict=True)!=gross or
                date_hint(v(rec,"GL Date"))!="20261022"):
            raise SafeError("MANUAL_ETAX_MIRROR_ID_OWNER_AMOUNT_DATE_MISMATCH_"+erp)
        source_records.append(rec)
    same_project=[r for r in etax if v(r,"Project Number")==X
                  or v(r,"Quotation Number")==AMEA]
    if len(same_project)!=2:
        raise SafeError("MANUAL_ETAX_UNEXPECTED_SAME_PROJECT_BILLING_ROWS")
    quotes=source["SFDC Quote Export"]
    quote=require_unique(
        quotes,lambda r:v(r,"AMEA Quotation ID")==AMEA and
        v(r,"IsActive") in {"1","true","True"},
        "MANUAL_ETAX_ACTIVE_QUOTE_NOT_UNIQUE")
    if (v(quote,"Quotation Name")!=QID or
            v(quote,"Opportunity ID")!=OPP or
            "Changwon" not in v(quote,"Account Name").casefold() or
            "SungPilMo" not in v(quote,"Contact Name")):
        raise SafeError("MANUAL_ETAX_ACTIVE_QUOTE_ACCOUNT_LINK_MISMATCH")
    opp=require_unique(source["SFDC Email Opportunities Raw"],
                       lambda r:v(r,"Opportunity ID")==OPP,
                       "MANUAL_ETAX_OPPORTUNITY_NOT_UNIQUE")
    if (v(opp,"Opportunity Owner")!="Kim Taehoon"
            or v(opp,"Stage")!="Closed Won"
            or "Changwon" not in v(opp,"Account Name").casefold()
            or "SungPilMo" not in v(opp,"Main Contact")):
        raise SafeError("MANUAL_ETAX_SFDC_OWNER_CONTACT_UNVERIFIED")
    css=source["CSS Tax Invoice Extract"]
    if not all(field in css[0] for field in
               ("invoice_number","project_id","subject","validation_status")):
        raise SafeError("MANUAL_ETAX_QQ_SOURCE_SCHEMA_UNVERIFIED")
    overlap=[r for r in css
             if v(r,"project_id")==AMEA or AMEA in v(r,"subject")
             or X in v(r,"subject") or
             "H209SC26107211" in v(r,"h_project_number")]
    if overlap:
        raise SafeError("MANUAL_ETAX_ALREADY_IN_ORIGINAL_QQ_INVOICES")
    print("MANUAL_ETAX_GOOGLE_SOURCE_PASS erp_rows=2 "+
          "quote_active_id="+QID+" opportunity="+OPP+
          " owner=Kim_Taehoon qq_overlap=0 "+
          "same_project_other_rows=0 "+
          "gross_verified="+str(EXPECTED_MANUAL_GROSS),flush=True)
    return quote,opp


def load_source_spreadsheets():
    sess=sheets_session()
    return {
        "Feishu Latest eTax":req_sheet(sess,UNIFIED_SHEET,"Feishu Latest eTax",190),
        "SFDC Quote Export":req_sheet(sess,UNIFIED_SHEET,"SFDC Quote Export",1900),
        "SFDC Email Opportunities Raw":req_sheet(sess,UNIFIED_SHEET,
                                                 "SFDC Email Opportunities Raw",850),
        "CSS Tax Invoice Extract":req_sheet(sess,CSS_SHEET,"CSS Tax Invoice Extract",1000),
    }


def check_original_certificate(token):
    full,_=read_tracking(token)
    index=build_index(full)
    sid=find_sheet(token)
    values={}
    for erp in TARGETS:
        if erp not in index:
            raise SafeError("MANUAL_ETAX_ORIGINAL_NOT_FOUND_"+erp)
        expected_h,line=index[erp]
        response=row_read(token,sid,line,line)
        if (len(response)!=1 or len(response[0])<10
                or scalar(response[0][3])!=erp
                or scalar(response[0][7])!=expected_h):
            raise SafeError("MANUAL_ETAX_ORIGINAL_ID_CERT_CHANGED")
        values[erp]=response[0]
    proof=evidence(values,full)
    if (not proof["document_proof_consistent"]
            or not proof["same_certificate"]
            or not proof["certificate_group_exact_pair"]
            or not proof["no_cancel"]
            or not proof["issuance_remark_positive"]
            or proof["cms_month_hints"]!=[MONTH]
            or proof["gross_sum"]!=EXPECTED_MANUAL_GROSS
            or proof["net_sum"]!=EXPECTED_MANUAL_NET):
        raise SafeError("MANUAL_ETAX_ORIGINAL_CERTIFICATE_GROSS_OR_CANCEL_UNVERIFIED")
    # Original tracking G uses only "Taehoon"; the independent SFDC
    # Quote->Opportunity owner and mirrored ERP sales label prove surname.
    for erp in TARGETS:
        line=proof["details"][erp]
        if (not line["sales_token_clues"]["has_taehoon"]
                or line["num_digits"]!=24
                or not line["cert_prefix_date_matches_C"]
                or line["cms_date_hint"]!="20261022"):
            raise SafeError("MANUAL_ETAX_ORIGINAL_SALES_OR_ISSUE_DATE_NOT_CORROBORATED")
    print("MANUAL_ETAX_ORIGINAL_PASS rows_scanned="+str(len(full))+
          " ERP_lines=2 tax_certificates=1 tax_date=2026-10-22"+
          " H_number_digits=24 F_gross=10604000 J_cancel=EMPTY"+
          " I_issued=YES original_sales_given_name=Taehoon",flush=True)


def manual_record():
    k=(decimal.Decimal(EXPECTED_MANUAL_NET)/REPORTING_FX/
       decimal.Decimal(1000)).quantize(decimal.Decimal("0.0001"))
    return {
        "Source Key":MANUAL_KEY,"Month":MONTH,"Invoice Count":1,
        "Tax Invoice KRW Incl VAT":EXPECTED_MANUAL_GROSS,
        "Net Revenue KRW Ex VAT":EXPECTED_MANUAL_NET,
        "Net Revenue M KRW":9.64,
        "Net Revenue K USD":float(k),
        "CSS Source Invoice Count":None,
        "CSS Source KRW Incl VAT":None,
        "Source Difference KRW":None,
        "Coverage Status":"ISSUED_ETAX_MANUAL_PREPAYMENT_ACCOUNTING_RECOGNITION_REVIEW",
        "Evidence":("Feishu original Tracking file 2026: "+
                    "CMS invoice date 2026-10-22; ERP 20910000208+20910000209; "+
                    "one unique 24-digit eTax certificate (redacted), "+
                    "F gross amounts 1287000+9317000, I issued, J no cancel, "+
                    "G Taehoon; Feishu eTax mirror quote "+AMEA+
                    " / X209SC26107211; SFDC active "+QID+
                    " linked "+OPP+" owner Kim Taehoon; "+
                    "QQ original invoices no overlapping AMEA/X. "+
                    "VAT excluded issued-invoice-only; "+
                    "prepayment is NOT proof of accrual revenue or bank payment.")
    }


def monthly_kpi_guard(rows,record_present):
    index=index_records(rows)
    if QQ_KEY not in index:
        raise SafeError("MANUAL_ETAX_CANONICAL_QQ_OCT_MISSING")
    old=index[QQ_KEY]["fields"]
    if (numer(raw_value(old.get("Net Revenue KRW Ex VAT")),strict=True)!=EXPECTED_QQ_NET
            or numer(raw_value(old.get("Tax Invoice KRW Incl VAT")),strict=True)!=EXPECTED_QQ_GROSS
            or numer(raw_value(old.get("Invoice Count")),strict=True)!=EXPECTED_QQ_COUNT):
        raise SafeError("MANUAL_ETAX_QQ_OCT_SOURCE_PARITY_CHANGED")
    october={key for key,row in index.items() if raw_value(
        (row.get("fields") or {}).get("Month")).strip()==MONTH}
    allowed={QQ_KEY,MANUAL_KEY} if record_present else {QQ_KEY}
    if october!=allowed:
        raise SafeError("MANUAL_ETAX_UNEXPECTED_OCT_MONTHLY_SOURCES")
    if record_present:
        obj=manual_record()
        manual=index[MANUAL_KEY]["fields"]
        if not equivalent(manual,obj):
            raise SafeError("MANUAL_ETAX_SOURCE_READBACK_PARITY_FAILED")
    expected_net=EXPECTED_COMBINED_NET if record_present else EXPECTED_QQ_NET
    expected_gross=EXPECTED_COMBINED_GROSS if record_present else EXPECTED_QQ_GROSS
    expected_count=EXPECTED_COMBINED_COUNT if record_present else EXPECTED_QQ_COUNT
    actual_net=sum(numer(raw_value((r.get("fields") or {}).get(
        "Net Revenue KRW Ex VAT")),strict=True) or 0 for key,r in index.items()
                   if key in allowed)
    actual_gross=sum(numer(raw_value((r.get("fields") or {}).get(
        "Tax Invoice KRW Incl VAT")),strict=True) or 0 for key,r in index.items()
                     if key in allowed)
    actual_count=sum(numer(raw_value((r.get("fields") or {}).get(
        "Invoice Count")),strict=True) or 0 for key,r in index.items()
                     if key in allowed)
    if (actual_net,actual_gross,actual_count)!=(
            expected_net,expected_gross,expected_count):
        raise SafeError("MANUAL_ETAX_MONTH_TOTAL_READBACK_MISMATCH")
    print("MANUAL_ETAX_MONTH_SUM_PASS month="+MONTH+
          " issued_certificates="+str(actual_count)+
          " gross_vat_included="+str(actual_gross)+
          " net_vat_excluded="+str(actual_net)+
          " manual_record_present="+str(record_present).lower(),flush=True)


def main():
    mode=os.environ.get("FEISHU_METRIC_MODE","plan")
    if mode not in {"plan","apply"}:
        raise SafeError("MANUAL_ETAX_UNSUPPORTED_MODE")
    if os.environ.get("FEISHU_BASE_APP_TOKEN")!=EXPECTED_BASE:
        raise SafeError("MANUAL_ETAX_WRONG_BASE")
    # External source evidence, corroboration and dedup before ANY writes.
    sources=load_source_spreadsheets()
    check_source_spreadsheets(sources)
    token,root=auth()
    check_original_certificate(token)
    ids=table_catalog(token,root).get("Monthly Tax Invoice") or []
    if len(ids)!=1:raise SafeError("MANUAL_ETAX_TARGET_TABLE_AMBIGUOUS")
    path=table_path(root,ids[0])
    actual={x.get("field_name"):x.get("type") for x in
            list_all(path+"/fields",token,"manual_etax_schema")}
    if any(actual.get(k)!=t for k,t in SCHEMAS["Monthly Tax Invoice"]):
        raise SafeError("MANUAL_ETAX_TARGET_SCHEMA_MISMATCH")
    before=list_all(path+"/records",token,"manual_etax_before")
    index=index_records(before)
    monthly_kpi_guard(before,MANUAL_KEY in index)
    print("MANUAL_ETAX_WRITE_PLAN mode="+mode+
          " one_certificate=YES source_rows=2 month="+MONTH+
          " net="+str(EXPECTED_MANUAL_NET)+
          " target_existing="+str(MANUAL_KEY in index),flush=True)
    if mode=="plan":return
    created,updated,unchanged=sync_table(token,path,[manual_record()],limit=1)
    if created+updated+unchanged!=1:
        raise SafeError("MANUAL_ETAX_WRITE_NOT_EXACT_ONE")
    after=list_all(path+"/records",token,"manual_etax_readback")
    old=index_records(before)
    new=index_records(after)
    if not set(old).issubset(new):
        raise SafeError("MANUAL_ETAX_UNEXPECTED_ROW_REMOVED")
    for key,rec in old.items():
        if key==MANUAL_KEY:continue
        if safe_existing_fields(rec)!=safe_existing_fields(new[key]):
            raise SafeError("MANUAL_ETAX_UNRELATED_MONTHLY_ROW_CHANGED")
    monthly_kpi_guard(after,True)
    print("MANUAL_ETAX_APPLY_PASS created="+str(created)+
          " updated="+str(updated)+" unchanged="+str(unchanged)+
          " QQ_original_rows_written=0 ERP_data_rows_written=0"+
          " other_months_untouched=true",flush=True)


if __name__=="__main__":
    try:main()
    except Exception as exc:
        err=str(exc) if isinstance(exc,SafeError) else type(exc).__name__
        print("MANUAL_ETAX_APPLY_FAILED="+err,file=sys.stderr)
        sys.exit(1)
