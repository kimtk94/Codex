"""Laptop-only authenticated SFDC Process / Product reference audit (GET only).

Run: python masteros/web/scripts/sfdc_held_quote_process_reference_audit.py
Requires:
  %LOCALAPPDATA%/SFDC_KRW_Price/2026_krw_3holds_native_original_process_private.json
  %LOCALAPPDATA%/SFDC_KRW_Price/2026_krw_complete_source_hold_queue_private.json
  authenticated Salesforce Chrome/Edge CDP (default localhost:9222).

No network calls to GitHub, no CRM writes, no automatic price promotion.
Source record IDs and prices are never printed or written into the repo.
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "automation" / "sfdc_desktop"))
from quote_native_process_guard import audit_native_process_bundle
from quote_native_reference_resolution import (
    resolve_native_data_unit, resolve_product_service,
    resolve_reference_status, resolve_report_process_id,
    resolve_2026_native_krw_product_signature,
)

PRIVATE = Path(os.environ.get("LOCALAPPDATA", "")) / "SFDC_KRW_Price"
SNAPSHOT = PRIVATE / "2026_krw_3holds_native_original_process_private.json"
MANIFEST = PRIVATE / "2026_krw_complete_source_hold_queue_private.json"
OUTPUT = PRIVATE / "2026_krw_3holds_native_reference_readback_PRIVATE.json"
SFDC_ORIGIN = "https://novogene.lightning.force.com"


def _read(path):
    if not path.is_file() or path.is_symlink():
        raise ValueError("LOCAL_PRIVATE_SOURCE_UNAVAILABLE")
    return json.loads(path.read_text(encoding="utf-8"))


def _read_live(page, cases):
    """Single JS session: GET-only, with bounded concurrency and no navigation."""
    targets = [
        {
            "quoteId": case["sourceQuoteId"],
            "processIds": [
                row["id"] for product in case["products"]
                for row in product["processRows"]
            ],
            "productIds": [product["productId"] for product in case["products"]],
        }
        for case in cases
    ]
    return page.evaluate("""async (targets) => {
      const api='/services/data/v65.0/ui-api/';
      async function get(path) {
        const response=await fetch(api+path, {
          method:'GET',credentials:'include',headers:{Accept:'application/json'}
        });
        if(!response.ok)throw Error('SOURCE_API_HTTP_'+response.status);
        return response.json();
      }
      const qmeta=await get('object-info/Quotation_Process__c');
      const units=qmeta.fields?.Data_Unit__c?.picklistValues||[];
      const ids=[...new Set(targets.flatMap(t=>[
        t.quoteId,...t.productIds,...t.processIds
      ]))];
      const records={};
      for(let i=0;i<ids.length;i+=4) {
        const chunk=ids.slice(i,i+4);
        const fetched=await Promise.all(chunk.map(async id=>{
          const record=await get('records/'+id+'?layoutTypes=Full&modes=View');
          return [id,record];
        }));
        for(const [id,record] of fetched)records[id]=record;
      }
      const refs=[...new Set(Object.values(records).flatMap(r=>[
        r.fields?.Process_Name__c?.value,
        r.fields?.Product_Name__c?.value
      ]).filter(x=>typeof x==='string'&&x.length===18||typeof x==='string'&&x.length===15))];
      const masters={};
      for(let i=0;i<refs.length;i+=4){
        const chunk=refs.slice(i,i+4);
        const fetched=await Promise.all(chunk.map(async id=>{
          try{return [id,await get('records/'+id+'?layoutTypes=Full&modes=View')];}
          catch{return [id,null];}
        }));
        for(const [id,record] of fetched)masters[id]=record;
      }
      function value(record,field){return record?.fields?.[field]?.value??null;}
      function masterFields(record){
        const keys=['Name','Process_ID__c','Process_Name__c',
          'Original_Process_ID__c','Process_External_ID__c'];
        return Object.fromEntries(keys.map(k=>[k,value(record,k)]));
      }
      const out=[];
      for(const t of targets){
        const quote=records[t.quoteId];
        const prods=t.productIds.map(id=>({
          id,name:value(records[id],'Name'),net:value(records[id],'Total_Price__c'),
          serviceRef:value(records[id],'Product_Name__c')
        }));
        const processes=t.processIds.map(id=>{
          const r=records[id],processRef=value(r,'Process_Name__c');
          return {id,productId:value(r,'Quotation_Product_ID__c'),
            name:value(r,'Process_Name_Report__c'),
            quantity:value(r,'Sample_Quantity__c'),
            dataSize:value(r,'Data_Size__c'),
            dataUnit:value(r,'Data_Unit__c'),
            displayDataUnit:r?.fields?.Data_Unit__c?.displayValue??null,
            unitPrice:value(r,'Unit_Price__c'),
            totalPrice:value(r,'Total_Price__c'),
            packNo:value(r,'Pack_No__c'),
            active:value(r,'Quotation_Active__c'),
            processRef,processMaster:masterFields(masters[processRef])};
        });
        out.push({quoteId:t.quoteId,
          quoteStatus:value(quote,'Quotation_Status__c'),
          currency:value(quote,'Currency__c'),
          gst:value(quote,'GST__c'),
          quoteNet:value(quote,'Exclude_Tax_After_Discount__c'),
          feeTotal:value(quote,'totalcustom__c'),
          grandTotal:value(quote,'Grand_Total2__c'),
          products:prods.map(p=>({
            ...p,serviceMaster:masterFields(masters[p.serviceRef])
          })),
          processes
        });
      }
      return {unitPicklist:units.map(v=>({value:v.value,label:v.label})),
        data:out};
    }""", targets)


def run():
    audit = {
        "source": "AUTHENTICATED_SFDC_UI_API_GET_ONLY",
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "salesforce_write": False,
        "price_index_modified": False,
        "cases": [],
    }
    try:
        old = _read(SNAPSHOT)
        original = _read(MANIFEST)
        private_index = _read(PRIVATE / "2026_krw_process_prices_verified_local.json")
        if not isinstance(private_index.get("records"), list):
            raise ValueError("PRIVATE_REFERENCE_INDEX_UNAVAILABLE")
        cases = old.get("cases")
        holds = original.get("single_product_held", []) + original.get(
            "multi_product_held", []
        )
        if not isinstance(cases, list) or len(cases) != 3:
            raise ValueError("EXPECTED_THREE_HELD_QUOTES")
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(
                os.environ.get("SFDC_CDP_URL", "http://127.0.0.1:9222"),
                timeout=12000,
            )
            try:
                page = next(
                    (tab for ctx in browser.contexts for tab in ctx.pages
                     if tab.url.startswith(SFDC_ORIGIN)), None
                )
                if page is None:
                    raise ValueError("AUTHENTICATED_SFDC_TAB_UNAVAILABLE")
                native = _read_live(page, cases)
            finally:
                browser.close()
        if len(native.get("data", [])) != len(cases):
            raise ValueError("LIVE_SOURCE_CASE_COUNT_MISMATCH")
        for old_case, live in zip(cases, native["data"]):
            if old_case["sourceQuoteId"] != live["quoteId"]:
                raise ValueError("NATIVE_PARENT_QUOTE_ID_MISMATCH")
            source_hold = next(
                (h for h in holds if h.get("record_id") == live["quoteId"]), None
            )
            if not source_hold:
                raise ValueError("HISTORICAL_REPORT_MANIFEST_UNAVAILABLE")
            manifest = {
                "created_date": source_hold["created_date"],
                "quote_id": source_hold["quote_id"],
                "approvalConfirmed": bool(source_hold.get("approval_evidence")),
                "approvalTimeConfirmed": bool(source_hold.get("approval_time_kst")),
                "expected_process_lines": source_hold["expected_process_lines"],
            }
            expected_ids = [
                x["process_id"] for x in manifest["expected_process_lines"]
            ]
            expected = manifest["expected_process_lines"]
            products = []
            resolved_rows = []
            missing_unit = 0
            missing_process_master = 0
            services = []
            for product in live["products"]:
                service = resolve_product_service(product["serviceMaster"])
                if service:
                    services.append(service)
                else:
                    services.append("")
                process_rows = []
                for process in live["processes"]:
                    if str(process["productId"] or "")[:15] != product["id"][:15]:
                        continue
                    report_id = resolve_report_process_id(
                        process["processMaster"], expected_ids,
                    )
                    unit = resolve_native_data_unit(
                        process["dataUnit"], process["displayDataUnit"],
                        native["unitPicklist"],
                    )
                    if report_id is None:
                        missing_process_master += 1
                    if unit is None:
                        missing_unit += 1
                    row = {
                        "productId": process["productId"],
                        "resolvedReportProcessId": report_id,
                        "processName": process["name"],
                        "quantity": process["quantity"],
                        "dataSize": process["dataSize"],
                        "dataUnit": unit,
                        "unitPrice": process["unitPrice"],
                        "totalPrice": process["totalPrice"],
                        "packNo": process["packNo"],
                        "nativeActive": process["active"],
                    }
                    process_rows.append(row)
                    resolved_rows.append({
                        "quotation_product_id": product["name"],
                        "process_id": report_id,
                    })
                products.append({
                    "recordId": product["id"],
                    "name": product["name"],
                    "sourceServiceName": service,
                    "net": product["net"],
                    "processRows": process_rows,
                })
            signatures = [
                resolve_2026_native_krw_product_signature(service, private_index["records"])
                for service in services
            ]
            resolution = resolve_reference_status(
                resolved_process_rows=resolved_rows,
                expected_rows=expected,
                verified_service_labels=services,
                expected_product_count=len(products),
            )
            if resolution["status"].startswith("SOURCE_REFERENCES_RESOLVED") and any(
                signature is None for signature in signatures
            ):
                resolution = {**resolution, "status": "HOLD_PRODUCT_SIGNATURE_UNRESOLVED"}
            source = {
                "source": "AUTHENTICATED_SFDC_UI_API_GET_ONLY",
                "salesforce_write": False,
                "quoteStatus": live["quoteStatus"],
                "currency": live["currency"],
                "gst": live["gst"],
                "quoteNet": live["quoteNet"],
                "feeTotal": live["feeTotal"],
                "grandTotal": live["grandTotal"],
                "products": products,
            }
            outcome = (
                audit_native_process_bundle(source, manifest)
                if resolution["status"].startswith("SOURCE_REFERENCES_RESOLVED")
                else {
                    "status": resolution["status"],
                    "historical_index_auto_promote": False,
                    "new_quote_price_approved": False,
                }
            )
            audit["cases"].append({
                "case_number": old_case["case_number"],
                "sourceQuoteId": live["quoteId"],
                "native": source,
                "manifest": manifest,
                "resolution": resolution,
                "source_product_signatures": signatures,
                "outcome": outcome,
                "missing_process_master": missing_process_master,
                "missing_data_unit": missing_unit,
            })
            print(
                "CASE=" + str(old_case["case_number"]) +
                " ROWS=" + str(len(resolved_rows)) +
                " PROCESS_MASTER_MISSING=" + str(missing_process_master) +
                " DATA_UNIT_MAPPING_MISSING=" + str(missing_unit) +
                " PRODUCT_SIGNATURES_UNRESOLVED=" + str(sum(x is None for x in signatures)) +
                " REFERENCE_STATUS=" + resolution["status"] +
                " PRICE_STATUS=" + outcome["status"]
            )
        audit["status"] = (
            "ALL_REFERENCES_VERIFIED_REVIEW_ONLY"
            if all(
                case["outcome"]["status"] ==
                "NATIVE_PROCESS_AND_REPORT_REFERENCES_VERIFIED"
                for case in audit["cases"]
            )
            else "HOLD_UNRESOLVED_SOURCE_REFERENCES"
        )
    except Exception as exc:
        # Only print a stable local error code. Never log raw CRM exception text.
        audit["status"] = "SOURCE_UNAVAILABLE"
        audit["error_type"] = type(exc).__name__
        print("SOURCE_READBACK_STATUS=SOURCE_UNAVAILABLE")
    PRIVATE.mkdir(parents=True, exist_ok=True)
    temp = OUTPUT.with_suffix(".tmp")
    temp.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf8")
    temp.replace(OUTPUT)
    print("RESULT_STATUS=" + audit["status"])
    print("SOURCE_CASES=" + str(len(audit["cases"])))
    print("SFDC_WRITES=0 PRICE_INDEX_UPDATES=0")


if __name__ == "__main__":
    run()
