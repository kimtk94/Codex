"""Preclassify Quote references for instant local Oppo/Quote drafts.

Source: already ingested, SHA256-audited QQ SFDC 25-column Quote report.
Sink: two dedicated private Feishu Bitable tables, not Salesforce.

This happens during scheduled report synchronization, NOT when a user opens
an Opportunity. Shared Product classes are stored ONCE across Contacts.
A class is (Product process template, production Gb), never old process qty.
Prices remain attached to their historical Quote and are USD converted only.
"""
from __future__ import annotations
from collections import defaultdict
from decimal import Decimal, InvalidOperation
import json
import re
import sys

from sfdc_quote_report_bridge import (
    ReportSourceError, LINE_TAB, SHEET_RANGE_LINES, AUDIT_TAB, AUDIT_RANGE,
    HEAD_TAB, SHEET_RANGE_HEAD, checksum, canonical, google,
    spreadsheet_values, verify_qq_process_report_audit, build_records,
    SCHEMAS, ensure_table, sync_one, auth
)

TABLE_CLASS="SFDC Quote GB Project Classes"
TABLE_REFERENCE="SFDC Quote Reference Index"

SCHEMAS[TABLE_CLASS]=[
    "Class Key","Product Template Key","Production Gb","Gb Status",
    "Source Exported KST","Source Received KST"
]
SCHEMAS[TABLE_REFERENCE]=[
    "Quote ID","Quote Record ID","Opportunity External ID","Opportunity Name",
    "Account ID","Account Name","Contact ID","Contact External ID","Contact Name","Contact Email",
    "Account Contact Status","Products JSON","Product Count",
    "Reference Status","Source Exported KST","Source Received KST","Reference SHA256"
]

SOURCE_REQUIRED={
    "SFDC Quotation ID","Quotation Product ID","Contact Name: Full Name",
    "Contact ID","Email","Opportunity Name: Opportunity Name","Opportunity ID",
    "Account Name: Account Name","*Account Id","Data Unit","Data Size"
}
ACCOUNT_PATTERN=re.compile(r"^001[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?$")
CONTACT_PATTERN=re.compile(r"^003[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?$")
QID_PATTERN=re.compile(r"^QID-[0-9-]{8,50}$")
GB_UNIT=re.compile(r"^(?:g(?:b)?\s*(?:raw\s*data|data|produced|production)?|gigabytes?)$",re.I)

def plain(raw):
    value=str(raw or "").strip()
    return "" if value.lower() in ("null","none","-","no value") else value

def resolve_single(rows,key):
    values={plain(row.get(key,"")) for row in rows}
    values.discard("")
    return (next(iter(values)),"PASS") if len(values)==1 else (
        "","MISSING" if not values else "CONFLICT"
    )

def gb_value(raw):
    text=plain(raw).replace(",","")
    if not re.fullmatch(r"\d+(?:\.\d+)?",text):
        return ""
    try:
        value=Decimal(text)
        if value<=0 or value>Decimal("1000000") or not value.is_finite():
            return ""
        return format(value.normalize(),"f")
    except InvalidOperation:
        return ""

def preclassify(raw_rows,original,verified_mail):
    """Return compact reusable project classes and per-Quote references.

    Every Quote has one reference, every Product has one class key.
    Existing process quantities are never inspected (intentional).
    """
    if not raw_rows or not SOURCE_REQUIRED.issubset(set(raw_rows[0])):
        raise ReportSourceError("PREINDEX_REQUIRED_FIELDS_MISSING")
    lines=original["tables"]["SFDC Quote Report Lines"]
    grouped=defaultdict(list)
    for row in raw_rows:
        qid=plain(row.get("SFDC Quotation ID"))
        if not QID_PATTERN.fullmatch(qid):
            raise ReportSourceError("PREINDEX_QUOTE_ID_INVALID")
        grouped[qid].append(row)

    by_product=defaultdict(list)
    for row in lines:
        by_product[(row["Quote ID"],row["Quote Product ID"])].append(row)
    template_map={}
    for row in lines:
        template_map[(row["Quote ID"],row["Quote Product ID"])]=row["Product Template Key"]

    classes={}
    references=[]
    for qid,rows in sorted(grouped.items()):
        quote_line_product_ids={product for (q,product) in by_product if q==qid}
        raw_product_ids={plain(r.get("Quotation Product ID")) for r in rows}
        if quote_line_product_ids!=raw_product_ids:
            raise ReportSourceError("PREINDEX_PRODUCT_SOURCE_MISMATCH")
        account_id,acc_id_status=resolve_single(rows,"*Account Id")
        account_name,acc_name_status=resolve_single(rows,"Account Name: Account Name")
        raw_contact_id,con_id_status=resolve_single(rows,"Contact ID")
        contact_id=raw_contact_id if CONTACT_PATTERN.fullmatch(raw_contact_id) else ""
        contact_external_id=raw_contact_id if raw_contact_id and not contact_id else ""
        contact_name,con_name_status=resolve_single(rows,"Contact Name: Full Name")
        contact_email,con_email_status=resolve_single(rows,"Email")
        opp_external,opp_id_status=resolve_single(rows,"Opportunity ID")
        opp_name,opp_name_status=resolve_single(rows,"Opportunity Name: Opportunity Name")
        if account_id and not ACCOUNT_PATTERN.fullmatch(account_id):
            acc_id_status="INVALID";account_id=""
        if contact_external_id:
            con_id_status="EXTERNAL_ONLY" if re.fullmatch(r"CP[A-Za-z0-9-]{5,40}",contact_external_id) else "UNKNOWN_FORMAT"
        id_valid=acc_id_status=="PASS" and acc_name_status=="PASS" and con_name_status=="PASS"
        identity_state=("PASS" if id_valid and con_id_status=="PASS"
                        else "CONTACT_EXTERNAL_ONLY" if id_valid and con_id_status=="EXTERNAL_ONLY"
                        else "HOLD_IDENTITY")
        linked_id={r["Quote Record ID"] for r in lines if r["Quote ID"]==qid}
        if len(linked_id)!=1:
            raise ReportSourceError("PREINDEX_LINKED_RECORD_CONFLICT")
        record_id=next(iter(linked_id))
        product_refs=[]
        for product in sorted(raw_product_ids):
            product_rows=[r for r in rows if plain(r.get("Quotation Product ID"))==product]
            gb_values={gb_value(r.get("Data Size")) for r in product_rows
                       if GB_UNIT.fullmatch(plain(r.get("Data Unit")))}
            gb_values.discard("")
            gb=next(iter(gb_values)) if len(gb_values)==1 else ""
            gb_state=("PASS" if gb else "CONFLICT" if len(gb_values)>1 else "NOT_SPECIFIED")
            tkey=template_map[(qid,product)]
            ckey=checksum([tkey,gb if gb else "UNVERIFIED"])
            classes[ckey]={
                "Class Key":ckey,"Product Template Key":tkey,
                "Production Gb":gb,"Gb Status":gb_state,"Source Exported KST":"",
                "Source Received KST":verified_mail["received_kst"]
            }
            totals={plain(r.get("Total Price USD (converted)")) for r in product_rows}
            totals.discard("")
            total=next(iter(totals)) if len(totals)==1 else ""
            product_refs.append({
                "quoteProductId":product,
                "classKey":ckey,
                "referenceTotalUsd":total,
                "gbStatus":gb_state,
                "productionGb":gb,
            })
        reference_status="REFERENCE_ONLY" if record_id and identity_state=="PASS" else "HOLD"
        ref={
            "Quote ID":qid,"Quote Record ID":record_id,
            "Opportunity External ID":opp_external,"Opportunity Name":opp_name,
            "Account ID":account_id,"Account Name":account_name,
            "Contact ID":contact_id,"Contact External ID":contact_external_id,
            "Contact Name":contact_name,
            "Contact Email":contact_email,
            "Account Contact Status":identity_state,
            "Products JSON":canonical(product_refs),
            "Product Count":str(len(product_refs)),
            "Reference Status":reference_status,"Source Exported KST":"",
            "Source Received KST":verified_mail["received_kst"]
        }
        ref["Reference SHA256"]=checksum(ref)
        references.append(ref)
    if len(references)!=original["summary"]["quote_count"]:
        raise ReportSourceError("PREINDEX_QUOTE_COUNT_MISMATCH")
    if sum(int(x["Product Count"]) for x in references)!=original["summary"]["quote_product_count"]:
        raise ReportSourceError("PREINDEX_PRODUCT_COUNT_MISMATCH")
    if len({r["Quote ID"] for r in references})!=len(references):
        raise ReportSourceError("PREINDEX_DUPLICATE_QUOTE")
    return {
        "tables":{TABLE_CLASS:list(sorted(classes.values(),key=lambda x:x["Class Key"])),
                  TABLE_REFERENCE:references},
        "summary":{
            "source_mail_sha256":verified_mail["source_sha256"],
            "source_received_kst":verified_mail["received_kst"],
            "quote_references":len(references),
            "quote_products":sum(int(x["Product Count"]) for x in references),
            "shared_project_classes":len(classes),
            "account_contact_hold":sum(r["Account Contact Status"]!="PASS" for r in references),
            "record_id_hold":sum(not r["Quote Record ID"] for r in references),
            "source_price":"USD_CONVERTED_ONLY",
            "reference_only":True,"crm_writes":0
        }
    }

def load_source():
    session=google()
    raw=spreadsheet_values(session,LINE_TAB,SHEET_RANGE_LINES)
    audit=spreadsheet_values(session,AUDIT_TAB,AUDIT_RANGE)
    verified=verify_qq_process_report_audit(raw,audit)
    headers=spreadsheet_values(session,HEAD_TAB,SHEET_RANGE_HEAD)
    normalized=build_records(raw,headers,verified_evidence=verified)
    return preclassify(raw[0],normalized,verified)

def execute(mode):
    if mode not in ("audit","sync"):
        raise ReportSourceError("PREINDEX_MODE_INVALID")
    indexed=load_source()
    if mode=="audit":
        return {"status":"PASS","mode":"audit",
            "summary":indexed["summary"],"feishu_writes":0,"crm_writes":0}
    token=auth()
    # This is the only allowed schema migration: add external Contact ID
    # to the dedicated preindex table. Salesforce 003 IDs never inherit CP IDs.
    from sfdc_quote_report_bridge import list_tables,pages,path,call
    existing=list_tables(token).get(TABLE_REFERENCE)
    if existing:
        tid=existing.get("table_id","")
        fields=pages(token,path()+"/tables/"+tid+"/fields")
        field_map={x.get("field_name"):x.get("type") for x in fields}
        if "Contact External ID" not in field_map:
            missing=set(SCHEMAS[TABLE_REFERENCE])-set(field_map)
            if missing!={"Contact External ID"}:
                raise ReportSourceError("PREINDEX_SCHEMA_MIGRATION_BLOCK")
            call("POST",path()+"/tables/"+tid+"/fields",token,
                 {"field_name":"Contact External ID","type":1})
    keys={TABLE_CLASS:"Class Key",TABLE_REFERENCE:"Quote ID"}
    results={}
    for table,rows in indexed["tables"].items():
        tid=ensure_table(token,table)
        results[table]=sync_one(token,tid,keys[table],rows)
    return {"status":"PASS","mode":"sync","summary":indexed["summary"],
        "table_results":results,"crm_writes":0,
        "source":"QQ_MAIL_SHA256_VERIFIED",
        "readback":"PASS"}

if __name__=="__main__":
    try:
        mode=sys.argv[1] if len(sys.argv)>1 else "audit"
        print(json.dumps(execute(mode),ensure_ascii=False,sort_keys=True))
    except Exception as e:
        code=str(e) if isinstance(e,ReportSourceError) and re.fullmatch(r"[A-Z0-9_]{5,100}",str(e)) else "PREINDEX_FAILED"
        print(json.dumps({"status":"BLOCK","code":code,"crm_writes":0}),file=sys.stderr)
        sys.exit(2)
