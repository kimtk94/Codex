"""Authenticated, localhost-only Salesforce Quotation Fee source readback.

Operates against an already signed-in Chrome/Edge CDP tab. Uses native
Salesforce UI API GET only; never navigates, edits, writes, or saves SFDC.
Only returns a small allowlisted fee breakdown; no customer identifiers.
"""
from decimal import Decimal, InvalidOperation
import json
import os
import re
import sys

QUOTE_ID = re.compile(r"^a0P[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?$")
PRODUCT_ID = re.compile(r"^[A-Za-z0-9]{15}(?:[A-Za-z0-9]{3})?$")
FEE_TYPES = {"SP Sample Shipping Fee", "Sample Return Fee"}
BASE = "https://novogene.lightning.force.com"
API = "/services/data/v65.0/ui-api/"


def money(value):
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError("FEE_INVALID_MONEY")
    dec = Decimal(str(value))
    if not dec.is_finite() or dec != dec.to_integral_value() or dec < 0 or dec > 10**12:
        raise ValueError("FEE_INVALID_MONEY")
    return int(dec)


def read_source(quote_id):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(
            os.environ.get("SFDC_CDP_URL", "http://127.0.0.1:9222"), timeout=10000)
        page = next((pg for ctx in browser.contexts for pg in ctx.pages
                     if pg.url.startswith(BASE)), None)
        if page is None:
            raise ValueError("NO_AUTHENTICATED_SFDC_TAB")
        try:
            # Inputs must be pre-validated. Read data in the existing tab
            # session; browser console is never used and requests are GET-only.
            output = page.evaluate("""async ({id,api}) => {
              const get=async(path)=>{
                const response=await fetch(api+path,{method:"GET",
                  credentials:"include",headers:{Accept:"application/json"}});
                if(!response.ok)throw Error("SFDC_UI_READ_"+response.status);
                return await response.json();
              };
              const q=await get("records/"+id+"?layoutTypes=Full&modes=View");
              const pInfo=await get("related-list-info/Quotation__c/New_Quote_Line_Item__r");
              const fInfo=await get("related-list-info/Quotation__c/Quotation_Fee__r");
              if(pInfo?.objectApiNames?.[0]!=="Quotation_Products__c"||
                 fInfo?.objectApiNames?.[0]!=="Quotation_Fee__c")
                throw Error("SFDC_RELATED_LIST_SCHEMA_CHANGED");
              const pFields="Quotation_Products__c.Name";
              const fFields=["Fee__c","Fee_to_Calculate__c","Fee_Type__c",
                "Quotation_Currency__c","Quotation_Products__c","productName__c"]
                .map(x=>"Quotation_Fee__c."+x).join(",");
              const products=await get("related-list-records/"+id+
                "/New_Quote_Line_Item__r?fields="+encodeURIComponent(pFields)+"&pageSize=100");
              const fees=await get("related-list-records/"+id+
                "/Quotation_Fee__r?fields="+encodeURIComponent(fFields)+"&pageSize=100");
              return {
                nativeQuoteId:q.id||id,
                quoteApiName:q.apiName,
                currency:q.fields?.Currency__c?.value,
                vat:q.fields?.GST__c?.value,
                net:q.fields?.Exclude_Tax_After_Discount__c?.value,
                custom:q.fields?.totalcustom__c?.value,
                grand:q.fields?.Grand_Total2__c?.value,
                productCount:products.count,
                productIds:(products.records||[]).map(x=>x.id),
                feeCount:fees.count,
                fees:(fees.records||[]).map(x=>({
                  feeType:x.fields?.Fee_Type__c?.value,
                  fee:x.fields?.Fee__c?.value,
                  feeToCalculate:x.fields?.Fee_to_Calculate__c?.value,
                  currency:x.fields?.Quotation_Currency__c?.value,
                  productId:x.fields?.Quotation_Products__c?.value,
                  productName:x.fields?.productName__c?.value
                }))
              };
            }""", {"id": quote_id, "api": API})
            return output
        finally:
            browser.close()


def validate(quote_id, data):
    if not isinstance(data, dict) or data.get("nativeQuoteId", "")[:15] != quote_id[:15]:
        raise ValueError("SOURCE_QUOTE_ID_MISMATCH")
    if data.get("quoteApiName") not in ("Quotation__c", None):
        raise ValueError("WRONG_SOURCE_OBJECT")
    if data.get("currency") != "KRW" or data.get("vat") != "10,KR-VAT":
        raise ValueError("FEE_NON_KRW_OR_VAT_UNVERIFIED")
    net, custom, grand = (money(data[k]) for k in ("net", "custom", "grand"))
    if (Decimal(net + custom) * Decimal("1.1")) != Decimal(grand):
        raise ValueError("FEE_QUOTE_TOTAL_MISMATCH")
    ids = data.get("productIds")
    if (not isinstance(ids, list) or not ids or len(ids) > 100
        or data.get("productCount") != len(ids)
        or any(not isinstance(x, str) or not PRODUCT_ID.fullmatch(x) for x in ids)):
        raise ValueError("FEE_PRODUCT_SOURCE_INCOMPLETE")
    product_set = {x[:15] for x in ids}
    if len(product_set) != len(ids):
        raise ValueError("FEE_PRODUCT_SOURCE_DUPLICATED")
    rows = data.get("fees")
    if (not isinstance(rows, list) or len(rows) > 100 or data.get("feeCount") != len(rows)):
        raise ValueError("FEE_RELATED_RECORDS_INCOMPLETE")
    fees, total = [], 0
    for x in rows:
        if not isinstance(x, dict) or x.get("feeType") not in FEE_TYPES or x.get("currency") != "KRW":
            raise ValueError("FEE_TYPE_OR_CURRENCY_INVALID")
        ref = x.get("productId")
        if not isinstance(ref, str) or not PRODUCT_ID.fullmatch(ref) or ref[:15] not in product_set:
            raise ValueError("FEE_QUOTE_PRODUCT_LINK_MISMATCH")
        fee = money(x.get("fee"))
        if fee <= 0 or money(x.get("feeToCalculate")) != fee:
            raise ValueError("FEE_LINE_PRICE_INVALID")
        label = x.get("productName")
        if not isinstance(label, str) or not 1 <= len(label) <= 200:
            raise ValueError("FEE_PRODUCT_LABEL_INVALID")
        total += fee
        fees.append({"feeType":x["feeType"], "feeKrw":fee, "productName":label,
                     "sourceQuoteProductId":ref[:15], "currency":"KRW"})
    if total != custom:
        raise ValueError("FEE_SUM_TOTALCUSTOM_MISMATCH")
    return {"status":"PASS", "source":"LIVE_SALESFORCE_READ_ONLY", "local_only":True,
            "salesforce_write":False,"save_permitted":False,
            "nativeQuoteId":quote_id,
            "feeCount":len(fees),"totalFeeKrw":total,
            "feeLines":fees,"processPriceApproved":False}


def main():
    try:
        request = json.loads(sys.stdin.read(512))
        if (not isinstance(request, dict) or set(request) != {"sourceQuoteId"}
            or not QUOTE_ID.fullmatch(request["sourceQuoteId"])):
            raise ValueError("FEE_READ_INPUT_INVALID")
        result = validate(request["sourceQuoteId"], read_source(request["sourceQuoteId"]))
    except (ValueError, KeyError, TypeError, InvalidOperation) as exc:
        result = {"status":"HOLD","code":str(exc)[:90], "salesforce_write":False,
                  "save_permitted":False}
    except Exception:
        result = {"status":"HOLD","code":"FEE_SFDC_SOURCE_UNAVAILABLE",
                  "salesforce_write":False,"save_permitted":False}
    print(json.dumps(result,ensure_ascii=False,separators=(",",":")))


if __name__=="__main__":
    main()
