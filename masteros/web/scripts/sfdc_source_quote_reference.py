"""Fail-closed, read-only evidence gate for a *pre-existing* SFDC Quote.

The source Quote's existing Product and Pack are authoritative. Never click
the source Product (+) to add a duplicate while checking new-Quote headers.
This does NOT verify new Quote product writer, Save or final Cloud readback.
"""
import math

def _processes(value):
    if not isinstance(value,str):
        raise ValueError("SOURCE_PROCESS_SELECTION_INVALID")
    parts=[p.strip() for p in value.split(",") if p.strip()]
    if not 1<=len(parts)<=12 or len(set(parts))!=len(parts):
        raise ValueError("SOURCE_PROCESS_SELECTION_INVALID")
    return set(parts)

def verify_source_reference(source,request):
    if not isinstance(source,dict) or not isinstance(request,dict):
        raise ValueError("SOURCE_QUOTE_REFERENCE_UNAVAILABLE")
    if (source.get("status")!="PASS" or source.get("read_only") is not True
            or source.get("source")!="LIVE_SALESFORCE"):
        raise ValueError("SOURCE_QUOTE_REFERENCE_UNAVAILABLE")
    if (source.get("id")!=request.get("sourceQuoteId")
            or source.get("opportunityId")!=request.get("opportunityId")):
        raise ValueError("SOURCE_QUOTE_REFERENCE_PARENT_MISMATCH")
    if (source.get("productCount")!=1 or
            source.get("pricingStatus")!="VERIFIED_PROCESS_LINES" or
            source.get("sourcePackVerified") is not True or
            source.get("sourceVatRateVerified10Pct") is not True or
            source.get("cloudLinePresent") is not True):
        raise ValueError("SOURCE_QUOTE_REFERENCE_PRICE_PACK_UNVERIFIED")
    if (source.get("productName")!=request.get("productName") or
            source.get("productCategory")!=request.get("productCategory")):
        raise ValueError("SOURCE_QUOTE_REFERENCE_PRODUCT_MISMATCH")
    if _processes(source.get("processNames"))!=_processes(request.get("processNames")):
        raise ValueError("SOURCE_QUOTE_REFERENCE_PROCESS_MISMATCH")
    data=source.get("dataSize")
    requested=request.get("dataSize")
    if (isinstance(data,bool) or not isinstance(data,(int,float)) or
            not math.isfinite(data) or data<=0 or
            isinstance(requested,bool) or not isinstance(requested,(int,float)) or
            not math.isfinite(requested) or data!=requested):
        raise ValueError("SOURCE_QUOTE_REFERENCE_GB_MISMATCH")
    samples=source.get("samples")
    total=source.get("totalPriceKrw")
    rows=source.get("processPriceLines")
    if (type(samples) is not int or samples<1 or type(total) is not int
            or total<=0 or not isinstance(rows,list) or not 2<=len(rows)<=25):
        raise ValueError("SOURCE_QUOTE_REFERENCE_PROCESS_EVIDENCE_MISSING")
    cloud=0
    amount=0
    for line in rows:
        if not isinstance(line,dict) or type(line.get("sourceQty")) is not int or line["sourceQty"]<1:
            raise ValueError("SOURCE_QUOTE_REFERENCE_PROCESS_EVIDENCE_MISSING")
        rate=line.get("unitPriceKrw")
        if type(rate) is not int or rate<0:
            raise ValueError("SOURCE_QUOTE_REFERENCE_PROCESS_EVIDENCE_MISSING")
        amount+=rate*line["sourceQty"]
        if line.get("isCloud") is True:
            cloud+=1
            if line["sourceQty"]!=math.ceil(samples*data/100):
                raise ValueError("SOURCE_QUOTE_REFERENCE_CLOUD_QTY_MISMATCH")
        elif (line.get("isCloud") is not False or
              line["sourceQty"]!=samples or not line.get("packNo")):
            raise ValueError("SOURCE_QUOTE_REFERENCE_PROCESS_EVIDENCE_MISSING")
    if cloud!=1 or amount!=total:
        raise ValueError("SOURCE_QUOTE_REFERENCE_NET_MISMATCH")
    return {"source_reference_verified":True,
            "source_product_count":1,
            "source_process_count":len(rows),
            "new_quote_writer_verified":False,
            "save_permitted":False}
