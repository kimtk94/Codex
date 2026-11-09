"""Mirror mail-ingested SFDC Quotation Report DETAILS to user-owned Feishu Base.

Canonical source is the existing private Google Sheet populated by the QQ
Quotation Report importer. No Salesforce/browser access, no manual XLS read,
no GitHub storage of customer rows. Only new dedicated Feishu detail/dictionary
tables are written; the existing 'Quotes' aggregate and command queue remain
untouched. Historical USD-converted report rates are NEVER approved KRW rates.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
import sys
import urllib.parse as up

from sfdc_command_queue import auth, path, pages, call, google, gs

HEAD_TAB="SFDC Quote Export"
LINE_TAB="SFDC Email Quotation Raw"
AUDIT_TAB="SFDC Email Ingest Audit"
AUDIT_RANGE="A1:J15"
SHEET_RANGE_HEAD="A1:O2000"
SHEET_RANGE_LINES="A1:Y6000"
TABLE_LINES="SFDC Quote Report Lines"
TABLE_PROCESS="SFDC Quote Process Dictionary"
TABLE_PRODUCT="SFDC Quote Product Templates"

PROCESS_FIELDS=["Process Key","Process ID","Process Name","Data Unit","Source Exported KST"]
PRODUCT_FIELDS=["Product Template Key","Process Keys","Process Count","Source Exported KST"]
LINE_FIELDS=[
    "Line Key","Quote ID","Quote Record ID","Quote Product ID",
    "Product Template Key","Process Key",
    "Unit Price USD","Sales Price USD","Process Total USD",
    "Sample Qty","Data Size","Active","Quote Created",
    "Source Exported KST","Source Row Hash","Source Status"]
TEXT_FIELDS={
    "Unit Price USD","Sales Price USD","Process Total USD",
    "Sample Qty","Data Size"}  # Preserve original decimal precision as text.
SCHEMAS={TABLE_PROCESS:PROCESS_FIELDS,TABLE_PRODUCT:PRODUCT_FIELDS,TABLE_LINES:LINE_FIELDS}
MAX_LINES=4500


class ReportSourceError(ValueError):
    pass


def canonical(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"))


def checksum(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def spreadsheet_values(session,tab,range_):
    addr=up.quote("'"+tab+"'!"+range_,safe="")
    response=gs(session,"GET","/values/"+addr)
    matrix=response.get("values",[])
    if len(matrix)<2:raise ReportSourceError("REPORT_TAB_EMPTY")
    heads=matrix[0]
    if not isinstance(heads,list) or len(heads)!=len(set(heads)):
        raise ReportSourceError("REPORT_HEADERS_DUPLICATE")
    return [dict(zip(heads,row+[""]*(len(heads)-len(row))))
            for row in matrix[1:] if isinstance(row,list) and any(str(v).strip() for v in row)],heads



def verify_qq_process_report_audit(source_lines,source_audit):
    """Cross-check the complete 25-column report against QQ mail receipt evidence.

    The three-report importer stores SHA256(JSON([headers, rows])) under
    SFDC Email Ingest Audit. Recompute from the exact Sheets raw records;
    never infer report freshness from Quote Created Date or header Quote Export.
    """
    rows,headers=source_lines
    audit_rows,audit_headers=source_audit
    required={
      "Entity","Source Received KST","Ingest Checked KST","Rows","Unique IDs",
      "Duplicate IDs","Missing IDs","Content SHA256","State","Source Kind"}
    if not required.issubset(set(audit_headers)):
        raise ReportSourceError("QUOTE_MAIL_AUDIT_SCHEMA_MISSING")
    matching=[r for r in audit_rows if r.get("Entity")=="Quotation"]
    if len(matching)!=1:
        raise ReportSourceError("QUOTE_MAIL_AUDIT_NOT_UNIQUE")
    a=matching[0]
    if a.get("Source Kind")!="QQ IMAP" or a.get("State") not in (
            "STAGED_NOT_PROMOTED","PRESERVED_NO_NEW_REPORT"):
        raise ReportSourceError("QUOTE_MAIL_AUDIT_STATE_UNVERIFIED")
    if not rows or len(rows)>MAX_LINES:
        raise ReportSourceError("QUOTE_MAIL_DETAIL_COUNT_INVALID")
    values=[[str(row.get(header,"")) for header in headers] for row in rows]
    sha=hashlib.sha256(json.dumps([headers,values],ensure_ascii=False,
                        separators=(",",":")).encode("utf-8")).hexdigest()
    if not re.fullmatch(r"[a-f0-9]{64}",str(a.get("Content SHA256",""))) or sha!=a["Content SHA256"]:
        raise ReportSourceError("QUOTE_MAIL_AUDIT_HASH_MISMATCH")
    if "SFDC Quotation ID" not in headers:
        raise ReportSourceError("QUOTE_MAIL_QID_FIELD_MISSING")
    keys=[r.get("SFDC Quotation ID","") for r in rows]
    unique=len(set(keys))
    stats=(len(rows),unique,len(rows)-unique,sum(not k for k in keys))
    try:
        expected=tuple(int(a[k]) for k in ("Rows","Unique IDs","Duplicate IDs","Missing IDs"))
    except (ValueError,TypeError):
        raise ReportSourceError("QUOTE_MAIL_AUDIT_COUNTER_INVALID")
    if stats!=expected or stats[3]!=0:
        raise ReportSourceError("QUOTE_MAIL_AUDIT_COUNT_MISMATCH")
    fmt="%Y-%m-%d %H:%M:%S KST"
    try:
        received=datetime.strptime(a["Source Received KST"],fmt).replace(
            tzinfo=timezone(timedelta(hours=9)))
        checked=datetime.strptime(a["Ingest Checked KST"],fmt).replace(
            tzinfo=timezone(timedelta(hours=9)))
    except (TypeError,ValueError):
        raise ReportSourceError("QUOTE_MAIL_AUDIT_DATE_INVALID")
    current=datetime.now(timezone.utc)
    if received>current+timedelta(minutes=10) or checked>current+timedelta(minutes=10):
        raise ReportSourceError("QUOTE_MAIL_AUDIT_FUTURE_TIMESTAMP")
    if checked<received:
        raise ReportSourceError("QUOTE_MAIL_AUDIT_TEMPORAL_ORDER_INVALID")
    return {
       "received_kst":a["Source Received KST"],
       "checked_kst":a["Ingest Checked KST"],
       "source_sha256":sha,
       "audit_state":a["State"],
       "source_age_hours":round(max(0,(current-received).total_seconds()/3600),2),
       "source_checked_age_hours":round(max(0,(current-checked).total_seconds()/3600),2),
       "source_mail_hash_verified":True,
       "source_mail_timestamp_verified":True,
    }


def num_text(value):
    text=str(value if value is not None else "").strip().replace(",","")
    if text.lower() in ("","null","-"):return ""
    try:
        n=Decimal(text)
    except InvalidOperation:
        raise ReportSourceError("REPORT_NUMBER_MALFORMED")
    if not n.is_finite() or abs(n)>Decimal("999999999999"):
        raise ReportSourceError("REPORT_NUMBER_INVALID")
    return format(n,"f")


def build_records(source_lines,source_headers,now=None,verified_evidence=None):
    """Build normalized Feishu records; fail before writes on bad join/source."""
    required_lines={
      "SFDC Quotation ID","Quotation Product ID","Process Name: SFDC Process ID",
      "Quote Process Name","Data Unit","Unit Price USD",
      "Total Price USD (converted)","Sample Quantity","Data Size",
      "Active","Created Date","Sales Price USD (converted)"}
    required_head={"AMEA Quotation ID","Salesforce Record ID","Exported At KST"}
    if not required_lines.issubset(source_lines[1]) or not required_head.issubset(source_headers[1]):
        raise ReportSourceError("REPORT_REQUIRED_FIELDS_MISSING")
    lines=source_lines[0];heads=source_headers[0]
    if not 1<=len(lines)<=MAX_LINES or not heads:
        raise ReportSourceError("REPORT_ROW_COUNT_INVALID")
    by_quote={}
    exports=set()
    for row in heads:
        qid=str(row.get("AMEA Quotation ID","")).strip()
        rid=str(row.get("Salesforce Record ID","")).strip()
        if not re.fullmatch(r"QID-[0-9-]{8,50}",qid):
            raise ReportSourceError("REPORT_QUOTE_KEY_INVALID")
        if not re.fullmatch(r"a0P[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?",rid):
            raise ReportSourceError("REPORT_NATIVE_ID_INVALID")
        if qid in by_quote:raise ReportSourceError("REPORT_HEADER_DUPLICATED")
        by_quote[qid]=row
        exports.add(str(row.get("Exported At KST","")).strip())
    if len(exports)!=1 or not next(iter(exports)).endswith(" KST"):
        raise ReportSourceError("REPORT_EXPORT_TIME_CONFLICT")
    exported=next(iter(exports))
    try:
        date=datetime.strptime(exported,"%Y-%m-%d %H:%M:%S KST").replace(tzinfo=timezone(timedelta(hours=9)))
    except ValueError:
        raise ReportSourceError("REPORT_EXPORT_TIME_INVALID")
    if date>datetime.now(timezone.utc)+timedelta(minutes=10):
        raise ReportSourceError("REPORT_EXPORT_IN_FUTURE")
    # Header metadata refers to the older Quote EXPORT, not the source
    # 25-column process-price report. Never stamp old header time onto
    # newer process rows as if that proves the process report was current.
    report_status="DETAIL_REPORT_TIME_UNVERIFIED"
    received=verified_evidence["received_kst"] if verified_evidence else ""
    product_groups=defaultdict(list)
    process_defs={}
    occurrences=Counter()
    prepared=[]
    for i,row in enumerate(lines,1):
        qid=str(row["SFDC Quotation ID"]).strip()
        linked=by_quote.get(qid)
        # Report details may precede the separately exported Quote header.
        # Preserve those rows with an empty SFDC record ID and a HOLD flag;
        # do not invent an a0P record or block the whole report.
        product=str(row["Quotation Product ID"]).strip()
        proc=str(row["Process Name: SFDC Process ID"]).strip()
        label=str(row["Quote Process Name"]).strip()
        unit=str(row["Data Unit"]).strip()
        if not product or not proc or not label:
            raise ReportSourceError("REPORT_PRODUCT_PROCESS_INVALID")
        unit_price=num_text(row["Unit Price USD"])
        sales=num_text(row["Sales Price USD (converted)"])
        total=num_text(row["Total Price USD (converted)"])
        qty=num_text(row["Sample Quantity"])
        size=num_text(row["Data Size"])
        definition={"Process ID":proc,"Process Name":label,"Data Unit":unit}
        pkey=checksum(definition)
        process_defs[pkey]=definition
        key_base=(qid,product,pkey)
        occurrences[key_base]+=1
        if occurrences[key_base]>10:raise ReportSourceError("REPORT_DUPLICATE_PROCESS_EXCESS")
        linekey=checksum([qid,product,pkey,occurrences[key_base]])
        product_groups[(qid,product)].append(pkey)
        prepared.append({
          "Line Key":linekey,"Quote ID":qid,
          "Quote Record ID":linked["Salesforce Record ID"] if linked else "",
          "Quote Product ID":product,"Process Key":pkey,
          "Unit Price USD":unit_price,"Sales Price USD":sales,
          "Process Total USD":total,"Sample Qty":qty,"Data Size":size,
          "Active":str(row.get("Active","")).strip(),
          "Quote Created":str(row.get("Created Date","")).strip(),
          "Source Exported KST":"",
          "Source Received KST":received,
          "Source Row Hash":checksum(row),
          "Source Status":report_status if linked else "QUOTE_RECORD_ID_UNVERIFIED",
        })
    if not prepared:raise ReportSourceError("REPORT_EMPTY_LINES")
    # Created Date describes the Quote, not when the subscribed
    # process report arrived. Some older rows omit or null this date.
    # Keep these distinctions visible and never block all 3,904 rows
    # simply because one historical date is missing.
    process_dates=[]
    date_missing=0
    for row in lines:
        raw=str(row.get("Created Date","")).strip()
        try:
            process_dates.append(datetime.strptime(raw,"%m/%d/%Y"))
        except ValueError:
            date_missing+=1
    if not process_dates:
        raise ReportSourceError("REPORT_NO_PROCESS_DATES_VERIFIABLE")
    newest_process_created=max(process_dates)
    product_template_defs={}
    product_to_key={}
    for group,process_sequence in product_groups.items():
        # Sequence and repeated processes are part of the canonical structure.
        tkey=checksum(process_sequence)
        product_template_defs[tkey]={"Product Template Key":tkey,
          "Process Keys":canonical(process_sequence),
          "Process Count":str(len(process_sequence)),
          "Source Exported KST":""}
        product_to_key[group]=tkey
    for item in prepared:
        item["Product Template Key"]=product_to_key[(item["Quote ID"],item["Quote Product ID"])]
    process_items=[
      {"Process Key":key,**definition,"Source Exported KST":""}
      for key,definition in sorted(process_defs.items())]
    product_items=[product_template_defs[k] for k in sorted(product_template_defs)]
    if len({x["Line Key"] for x in prepared})!=len(prepared):
        raise ReportSourceError("REPORT_ROW_KEY_COLLISION")
    return {
        "tables":{TABLE_PROCESS:process_items,
                  TABLE_PRODUCT:product_items,TABLE_LINES:prepared},
        "summary":{
           "status":"DETAIL_REPORT_TIME_UNVERIFIED",
           "header_exported_kst":exported,
           "source_tab":LINE_TAB,
           "process_created_latest":newest_process_created.date().isoformat(),
           "process_date_missing_rows":date_missing,
           "quote_count":len({r["Quote ID"] for r in prepared}),
           "quote_record_ids_matched":len({r["Quote ID"] for r in prepared if r["Quote Record ID"]}),
           "quote_record_ids_unmapped":len({r["Quote ID"] for r in prepared if not r["Quote Record ID"]}),
           "quote_product_count":len(product_groups),
           "report_lines":len(prepared),
           "process_templates":len(process_items),
           "product_templates":len(product_items),
           "currency":"USD_CONVERTED_ONLY",
           "krw_rate_verified":False,
           "source_is_live":False,
           "process_report_export_time_verified":False,
           "source_mail_timestamp_verified":bool(verified_evidence),
           "source_mail_hash_verified":bool(verified_evidence),
           "process_report_received_kst":received,
           "source_mail_audit_checked_kst":verified_evidence["checked_kst"] if verified_evidence else "",
           "source_mail_audit_state":verified_evidence["audit_state"] if verified_evidence else "UNVERIFIED",
           "source_mail_sha256":verified_evidence["source_sha256"] if verified_evidence else "",
           "crm_writes":0
        }
    }


def load_source():
    s=google()
    lines=spreadsheet_values(s,LINE_TAB,SHEET_RANGE_LINES)
    audit=spreadsheet_values(s,AUDIT_TAB,AUDIT_RANGE)
    evidence=verify_qq_process_report_audit(lines,audit)
    heads=spreadsheet_values(s,HEAD_TAB,SHEET_RANGE_HEAD)
    return build_records(lines,heads,verified_evidence=evidence)


def field_spec(name):
    return {"field_name":name,"type":1}


def list_tables(token):
    return {i.get("name"):i for i in pages(token,path()+"/tables")}


def ensure_table(token,name):
    found=list_tables(token)
    item=found.get(name)
    if item is None:
        call("POST",path()+"/tables",token,{
            "table":{"name":name,"default_view_name":"Source evidence",
                     "fields":[field_spec(x) for x in SCHEMAS[name]]}})
        found=list_tables(token)
        item=found.get(name)
    if not item or not item.get("table_id"):
        raise ReportSourceError("FEISHU_TABLE_NOT_FOUND")
    tid=item["table_id"]
    field_items=pages(token,path()+"/tables/"+tid+"/fields")
    existing={x.get("field_name"):x.get("type") for x in field_items}
    if not set(existing).issuperset(SCHEMAS[name]):
        # Never mutate an already created table with a partial/conflicting schema.
        raise ReportSourceError("FEISHU_TABLE_SCHEMA_MISSING")
    if any(existing[x]!=1 for x in SCHEMAS[name]):
        raise ReportSourceError("FEISHU_TABLE_SCHEMA_TYPE_MISMATCH")
    return tid


def plain(v):
    if isinstance(v,list):return "".join(str(i.get("text","")) if isinstance(i,dict) else str(i) for i in v)
    return str(v or "")


def write_batch(token,url,records,update=False):
    method="POST"
    endpoint=url+("/batch_update" if update else "/batch_create")
    result=call(method,endpoint,token,{"records":records})
    return result.get("records") or []


def sync_one(token,tid,key_field,rows,legacy_header_exported_kst=None):
    base=path()+"/tables/"+tid+"/records"
    current=pages(token,base)
    old={}
    for row in current:
        field=row.get("fields") or {}
        key=plain(field.get(key_field))
        if not key or key in old:raise ReportSourceError("FEISHU_EXISTING_KEY_DUPLICATED")
        old[key]=row
    wanted={r[key_field]:r for r in rows}
    if len(wanted)!=len(rows):raise ReportSourceError("FEISHU_SOURCE_KEY_DUPLICATED")
    # Source timestamp regression is never allowed to overwrite newer reports.
    for key,prior in old.items():
        if key in wanted:
            timestamp=plain((prior.get("fields") or {}).get("Source Exported KST"))
            target_time=wanted[key]["Source Exported KST"]
            if timestamp and (not target_time or timestamp>target_time):
                before_status=plain((prior.get("fields") or {}).get("Source Status"))
                after_status=wanted[key].get("Source Status","")
                # The original mirror mislabeled an Oct 24 HEADER timestamp
                # as a process-detail export time. Clearing it is safe only
                # for explicitly unverified legacy rows, never a verified one.
                legacy=before_status in ("STALE","PROCESS_REPORT_FRESHNESS_UNVERIFIED")
                unverified=after_status in ("DETAIL_REPORT_TIME_UNVERIFIED",
                                            "QUOTE_RECORD_ID_UNVERIFIED")
                # Previously both template tables (without Source Status)
                # copied the *header* export stamp into a misleading
                # process-detail export field. Only clear that EXACT
                # independently identified incorrect historical stamp.
                legacy_dictionary=(
                    key_field in ("Process Key","Product Template Key")
                    and timestamp==legacy_header_exported_kst
                    and before_status==""
                    and after_status==""
                )
                if not (not target_time and (
                    (legacy and unverified) or legacy_dictionary
                )):
                    raise ReportSourceError("FEISHU_REPORT_SOURCE_REGRESSION")
    to_create=[]
    to_update=[]
    unchanged=0
    for key,row in wanted.items():
        existing=old.get(key)
        if existing is None:
            to_create.append({"fields":row})
            continue
        before=existing.get("fields") or {}
        if all(plain(before.get(k))==plain(v) for k,v in row.items()):
            unchanged+=1
        else:
            to_update.append({"record_id":existing["record_id"],"fields":row})
    if len(current)>len(rows)+5000:
        raise ReportSourceError("FEISHU_TARGET_UNEXPECTED_SIZE")
    superseded=0
    # Previous reports may have 1-2 retired process rows per Quote.
    # Never delete user records: mark old-only source lines as superseded,
    # so the web indexes ONLY the exact latest Report subset.
    if key_field=="Line Key":
        old_only=[(key,rec) for key,rec in old.items() if key not in wanted]
        if len(old_only)>100 or len(old_only)>max(10,len(rows)//50):
            raise ReportSourceError("FEISHU_HISTORICAL_LINE_DRIFT_TOO_LARGE")
        for key,rec in old_only:
            status=plain((rec.get("fields") or {}).get("Source Status"))
            if status=="SUPERSEDED_NOT_IN_CURRENT_REPORT":
                continue
            if status not in ("STALE","DETAIL_REPORT_TIME_UNVERIFIED",
                              "QUOTE_RECORD_ID_UNVERIFIED",
                              "PROCESS_REPORT_FRESHNESS_UNVERIFIED"):
                raise ReportSourceError("FEISHU_ORPHAN_LINE_NOT_SAFE_TO_SUPERSEDE")
            to_update.append({"record_id":rec["record_id"],
                              "fields":{"Source Status":"SUPERSEDED_NOT_IN_CURRENT_REPORT"}})
            superseded+=1
    for mode,batch in ((False,to_create),(True,to_update)):
        for i in range(0,len(batch),200):
            created=write_batch(token,base,batch[i:i+200],update=mode)
            if len(created)!=len(batch[i:i+200]):
                raise ReportSourceError("FEISHU_BATCH_WRITE_COUNT_MISMATCH")
    after=pages(token,base)
    mapped={}
    for rec in after:
        key=plain((rec.get("fields") or {}).get(key_field))
        if key in wanted:
            if key in mapped:raise ReportSourceError("FEISHU_READBACK_DUPLICATED")
            mapped[key]=rec.get("fields") or {}
    if set(mapped)!=set(wanted):
        raise ReportSourceError("FEISHU_READBACK_MISSING_KEYS")
    for key,expected in wanted.items():
        fields=mapped[key]
        if any(plain(fields.get(k))!=plain(v) for k,v in expected.items()):
            raise ReportSourceError("FEISHU_READBACK_FIELD_MISMATCH")
    orphan_rows=[r for r in after if plain((r.get("fields") or {}).get(key_field)) not in wanted]
    if key_field=="Line Key" and any(
        plain((r.get("fields") or {}).get("Source Status"))!="SUPERSEDED_NOT_IN_CURRENT_REPORT"
        for r in orphan_rows
    ):
        raise ReportSourceError("FEISHU_HISTORICAL_SUPERSEDE_READBACK_FAILED")
    return {"source_rows":len(rows),"created":len(to_create),
            "updated":len(to_update)-superseded,"unchanged":unchanged,
            "superseded":superseded,"historical_retained_rows":len(orphan_rows),
            "physical_feishu_rows":len(after),"readback":"PASS"}


def execute(mode):
    if mode not in ("audit","sync"):
        raise ReportSourceError("REPORT_MODE_INVALID")
    indexed=load_source()
    if mode=="audit":
        return {"status":"PASS","mode":"audit","summary":indexed["summary"],
                "target_tables":list(indexed["tables"]),
                "source_readback":"PASS","feishu_writes":0,"crm_writes":0}
    token=auth()
    results={}
    mapping={
        TABLE_PROCESS:"Process Key",
        TABLE_PRODUCT:"Product Template Key",
        TABLE_LINES:"Line Key",
    }
    for table,rows in indexed["tables"].items():
        tid=ensure_table(token,table)
        results[table]=sync_one(token,tid,mapping[table],rows,
            legacy_header_exported_kst=indexed["summary"]["header_exported_kst"])
    return {"status":"PASS","mode":"sync",
            "summary":indexed["summary"],
            "table_results":results,
            "feishu_write_scope":"DEDICATED_REPORT_TABLES_ONLY",
            "crm_writes":0}


def main():
    mode=sys.argv[1] if len(sys.argv)>1 else "audit"
    try:
        print(json.dumps(execute(mode),sort_keys=True,ensure_ascii=False))
    except Exception as exc:
        reason=str(exc) if isinstance(exc,ReportSourceError) and re.fullmatch(r"[A-Z0-9_]{5,100}",str(exc)) else "REPORT_BRIDGE_UNAVAILABLE"
        print(json.dumps({"status":"BLOCK","mode":mode,"code":reason,
             "exception_type":type(exc).__name__,"crm_writes":0}),file=sys.stderr)
        sys.exit(2)


if __name__=="__main__":
    main()
