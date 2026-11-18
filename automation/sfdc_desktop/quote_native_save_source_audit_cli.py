"""Operator-laptop adapter for authenticated GET-only SFDC Quote source snapshots.

Read private files on the connected laptop, map native child Master IDs,
and create a HOLD/verified-source audit. Never write candidate.json,
evidence.json, journal.json or execute Salesforce Save.

Example (paths must be private, not GitHub):
  python quote_native_save_source_audit_cli.py --queue queue.json
    --product-json native_product.json --process-json native_process.json
    --quote-json native_quote_ui.json --terms approved_terms.json
    --output source_audit.json
"""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
from quote_native_save_source_audit import audit_source_bundle

def val(record,key):
    fields=record.get("fields",{})
    entry=fields.get(key)
    return entry.get("value") if isinstance(entry,dict) else None

def build_from_live_files(queue, product_source, process_source, quote_source):
    if not all(isinstance(x,dict) for x in (queue,product_source,process_source,quote_source)):
        raise ValueError("PRIVATE_SOURCE_INVALID")
    quote_id=queue["canonical"]["reference"]["sourceQuoteId"]
    product_rows=[
        rec for payload in product_source.values() if isinstance(payload,dict)
        and payload.get("http")==200
        for rec in payload.get("records",[])
        if rec.get("apiName")=="Quotation_Products__c"
    ]
    if len(product_rows)!=1:
        raise ValueError("SOURCE_QUOTATION_PRODUCT_RECORD_AMBIGUOUS")
    rec=product_rows[0]
    f=rec.get("fieldValues",{})
    product2=f.get("Product_Name__c",{}).get("value")
    qd=f.get("Name",{}).get("value")
    qprod=rec.get("id")
    process_records=[]
    for x in process_source.get("requests",[]):
        if x.get("http")!=200 or x.get("apiName")!="Quotation_Process__c":
            raise ValueError("NATIVE_QUOTATION_PROCESS_GET_UNVERIFIED")
        fields=x.get("fields",{})
        def field(k):
            entry=fields.get(k,{})
            return entry.get("value") if isinstance(entry,dict) else None
        record={
            "name":field("Process_Name_Report__c"),
            "native_id":x.get("id"),
            "process_master_id":field("Process_Name__c"),
            "native_quotation_product_id":field("Quotation_Product_ID__c"),
            "quantity":field("Sample_Quantity__c"),
            "unit_price_krw":field("Unit_Price__c"),
            "net_krw":field("Total_Price__c"),
            "process_type":field("Quote_Process_Type_Name__c"),
            "pack":field("Pack_No__c"),
            "currency":field("CurrencyIsoCode"),
            "data_size":field("Data_Size__c"),
            "data_unit":fields.get("Data_Unit__c",{}).get("displayValue")
                      or field("Data_Unit__c"),
        }
        process_records.append(record)
    proposed=queue["canonical"]["proposed"]
    return {
        "source_quotation_id":quote_id,
        "source_opportunity_id":queue["canonical"]["reference"]["opportunityId"],
        "new_opportunity_name":proposed["name"],
        "quote_net_krw":str(quote_source.get("net_krw","")).replace(",",""),
        "quote_gross_krw":str(quote_source.get("gross_krw","")).replace(",",""),
        "product":{"source_reference_product_id":qd,
           "native_product_id":product2,"native_quotation_product_id":qprod},
        "processes":process_records,
    }

def main():
    p=argparse.ArgumentParser()
    for name in ("queue","product-json","process-json","quote-json","terms","output"):
        p.add_argument("--"+name,required=True,type=Path)
    args=p.parse_args()
    if args.output.exists():
        raise SystemExit("OUTPUT_ALREADY_EXISTS_REVIEW_PRIOR_AUDIT")
    inputs=[args.queue,args.product_json,args.process_json,args.quote_json,args.terms]
    if any(not x.is_file() or x.is_symlink() or x.stat().st_size>300000 for x in inputs):
        raise SystemExit("PRIVATE_INPUT_FILE_INVALID")
    # A source snapshot older than 30 minutes never counts as current evidence.
    now=datetime.now(timezone.utc).timestamp()
    fresh=all(0 <= now-x.stat().st_mtime <=1800 for x in inputs[1:4])
    queue,product,processes,quote,terms=[
        json.loads(x.read_text(encoding="utf-8-sig")) for x in inputs]
    bundle=build_from_live_files(queue,product,processes,quote)
    report=audit_source_bundle(queue,bundle,terms)
    if not fresh:
        report["reason_codes"]=sorted(set(report.get("reason_codes",[])+["SOURCE_READBACK_STALE"]))
        report["status"]="HOLD_NATIVE_QUOTE_SOURCE"
        report["native_source_verified"]=False
    report["checked_at_utc"]=datetime.now(timezone.utc).isoformat()
    report["source_quote_id"]=bundle["source_quotation_id"]
    report["source_opportunity_id"]=bundle["source_opportunity_id"]
    report["native_product_master_id"]=bundle["product"]["native_product_id"]
    report["native_quote_product_id"]=bundle["product"]["native_quotation_product_id"]
    report["approval_request_id"]=queue["requestId"]
    report["save_permitted"]=False
    report["crm_writes"]=0
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open("x",encoding="utf8") as f:
        json.dump(report,f,ensure_ascii=False,indent=2)
    print(json.dumps({"status":report["status"],"reasons":report["reason_codes"],
      "native_source_process_rows":len(report["source_processes"]),
      "source_snapshot_fresh":fresh,"save_permitted":False,"crm_writes":0},
      ensure_ascii=False))

if __name__=="__main__":main()
