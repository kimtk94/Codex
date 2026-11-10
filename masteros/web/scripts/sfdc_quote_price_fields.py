"""Audited SFDC single-product Quote price contract.

No SFDC writes. Each output is derived from original per-process rates, not
the misleading Quote total / samples average (Cloud rounds in 100 Gb blocks).
"""
import math
import json

PRICE_INPUT_FIELDS=["Requested Product Unit KRW","Requested Cloud Unit KRW"]
PRICE_RESULT_FIELDS=["Source Product Name","Sample Unit KRW","Product Unit KRW",
    "Product Qty","Product Net KRW","Cloud Unit KRW","Cloud Qty","Cloud Net KRW",
    "Quote Net KRW","VAT KRW","Quote Gross KRW","Price Basis","Price Status",
    "Product Price Detail","Product Price Items JSON"]
NUMBER_FIELDS=frozenset([
    "Requested Product Unit KRW","Requested Cloud Unit KRW",
    "Sample Unit KRW","Product Unit KRW","Product Qty","Product Net KRW",
    "Cloud Unit KRW","Cloud Qty","Cloud Net KRW","Quote Net KRW",
    "VAT KRW","Quote Gross KRW"])

class PriceError(ValueError):
    pass

def number(value,allow_blank=False):
    if value is None or value=="":
        if allow_blank:return None
        raise PriceError("PRICE_RATE_MISSING")
    if isinstance(value,bool):raise PriceError("PRICE_RATE_INVALID")
    try:
        converted=int(value)
    except (TypeError,ValueError,OverflowError) as exc:
        raise PriceError("PRICE_RATE_INVALID") from exc
    if str(value).strip()!=str(converted) or converted<0 or converted>1000000000:
        raise PriceError("PRICE_RATE_INVALID")
    return converted

def evaluate(quote,samples,gb_per_sample,product_override="",cloud_override=""):
    if not isinstance(quote,dict) or quote.get("pricingStatus")!="VERIFIED_PROCESS_LINES" or quote.get("sourceVatRateVerified10Pct") is not True:
        raise PriceError("SOURCE_PRICE_UNVERIFIED")
    if not isinstance(samples,int) or isinstance(samples,bool) or not 1<=samples<=500:
        raise PriceError("NEW_SAMPLES_INVALID")
    if not isinstance(gb_per_sample,(int,float)) or isinstance(gb_per_sample,bool) or not math.isfinite(gb_per_sample) or gb_per_sample<=0:
        raise PriceError("DATA_SIZE_INVALID")
    source_samples=quote.get("samples")
    size=quote.get("dataSize")
    if not isinstance(source_samples,int) or not 1<=source_samples<=500 or not isinstance(size,(int,float)) or size!=gb_per_sample:
        raise PriceError("DATA_SIZE_RATE_UNVERIFIED")
    if quote.get("productCount")!=1 or not quote.get("productName") or quote.get("cloudLinePresent") is not True:
        raise PriceError("SOURCE_SINGLE_PRODUCT_UNVERIFIED")
    raw=quote.get("processPriceLines")
    if not isinstance(raw,list) or not 1<=len(raw)<=25:
        raise PriceError("SOURCE_PROCESS_LINES_MISSING")
    noncloud=[];clouds=[]
    for entry in raw:
        if not isinstance(entry,dict):raise PriceError("PROCESS_LINE_INVALID")
        price=number(entry.get("unitPriceKrw"))
        qty=number(entry.get("sourceQty"))
        amount=number(entry.get("sourceNetKrw"))
        if qty<=0 or amount!=price*qty:
            raise PriceError("PROCESS_LINE_ARITHMETIC_MISMATCH")
        if entry.get("isCloud") is True:clouds.append(entry)
        elif entry.get("isCloud") is False:noncloud.append(entry)
        else:raise PriceError("PROCESS_TYPE_UNCLASSIFIED")
    if not noncloud or len(clouds)!=1:
        raise PriceError("MULTI_CLOUD_OR_MISSING_PRODUCT")
    expected_cloud=math.ceil(source_samples*gb_per_sample/100)
    if any(x["sourceQty"]!=source_samples for x in noncloud) or clouds[0]["sourceQty"]!=expected_cloud:
        raise PriceError("SOURCE_PROCESS_QTY_MISMATCH")
    source_product_rate=sum(x["unitPriceKrw"] for x in noncloud)
    source_cloud_rate=clouds[0]["unitPriceKrw"]
    source_net=source_samples*source_product_rate+expected_cloud*source_cloud_rate
    if (source_product_rate!=quote.get("sampleUnitNetKrw") or
        source_cloud_rate!=quote.get("cloudUnitNetKrw") or
        expected_cloud!=quote.get("sourceCloudUnits") or
        source_net!=quote.get("totalPriceKrw")):
        raise PriceError("SOURCE_QUOTE_RECONCILIATION_FAILED")
    unit=number(product_override,allow_blank=True)
    cloud_unit=number(cloud_override,allow_blank=True)
    is_override=(unit is not None and unit!=source_product_rate) or (cloud_unit is not None and cloud_unit!=source_cloud_rate)
    if unit is None:unit=source_product_rate
    if cloud_unit is None:cloud_unit=source_cloud_rate
    cloud_qty=math.ceil(samples*gb_per_sample/100)
    prod_net=samples*unit
    cloud_net=cloud_qty*cloud_unit
    net=prod_net+cloud_net
    if net>1000000000000 or net%10:
        raise PriceError("VAT_ROUNDING_REVIEW_REQUIRED")
    detail=[]
    for x in noncloud:
        detail.append(str(x.get("processName") or x.get("processType") or "Product process")+
            ": source rate "+str(x["unitPriceKrw"])+"/sample")
    detail.append(str(clouds[0].get("processName") or "AliCloud")+
                  ": source rate "+str(source_cloud_rate)+"/100Gb")
    if is_override:
        detail.append("USER_PRICE_OVERRIDE_REQUIRES_APPROVAL")
    return {
        "Source Product Name":str(quote["productName"])[:230],
        "Sample Unit KRW":unit,
        "Product Unit KRW":unit,
        "Product Qty":samples,
        "Product Net KRW":prod_net,
        "Cloud Unit KRW":cloud_unit,
        "Cloud Qty":cloud_qty,
        "Cloud Net KRW":cloud_net,
        "Quote Net KRW":net,
        "VAT KRW":net//10,
        "Quote Gross KRW":net*11//10,
        "Price Basis":"SOURCE_QUOTE_PROCESS_RATES"+("_OVERRIDDEN" if is_override else ""),
        "Price Status":"MANUAL_OVERRIDE_REVIEW_REQUIRED" if is_override else "SOURCE_VERIFIED_PROJECTION",
        "Product Price Detail":"; ".join(detail)[:1500],
        "Product Price Items JSON":json.dumps([{"product":str(quote["productName"]),
            "unit_krw":unit,"qty":samples,"net_krw":prod_net}],ensure_ascii=False,separators=(",",":")),
    }


def evaluate_multi(quote,samples,gb_per_sample,product_override="",cloud_override=""):
    """CHECK-only projected pricing for independently verified multi-product lines.

    Contract: sourceProductLines represent each original Quote Product with its
    own verified process lines and matching net. A *single* quote-level Cloud
    line is calculated from the total Gb/sample, not per product. The current
    Salesforce reader does not yet emit this verified contract: never accept
    scraped/partially inferred product lines as verified.
    """
    if not isinstance(quote,dict) or quote.get("pricingStatus")!="VERIFIED_MULTI_PRODUCT_LINES" or quote.get("sourceVatRateVerified10Pct") is not True:
        raise PriceError("SOURCE_MULTI_PRODUCT_LINES_NOT_VERIFIED")
    if not isinstance(samples,int) or isinstance(samples,bool) or not 1<=samples<=500:
        raise PriceError("NEW_SAMPLES_INVALID")
    if isinstance(gb_per_sample,bool) or not isinstance(gb_per_sample,(int,float)) or not math.isfinite(gb_per_sample) or gb_per_sample<=0:
        raise PriceError("DATA_SIZE_INVALID")
    source_samples=quote.get("samples")
    source_size=quote.get("dataSize")
    if not isinstance(source_samples,int) or isinstance(source_samples,bool) or not 1<=source_samples<=500 or not isinstance(source_size,(int,float)) or isinstance(source_size,bool) or not math.isfinite(source_size) or not math.isclose(source_size,gb_per_sample,rel_tol=0,abs_tol=1e-9):
        raise PriceError("DATA_SIZE_RATE_UNVERIFIED")
    if product_override not in ("",None):
        raise PriceError("MULTI_PRODUCT_AGGREGATE_OVERRIDE_FORBIDDEN")
    products=quote.get("sourceProductLines")
    if not isinstance(products,list) or not 2<=len(products)<=12 or quote.get("productCount")!=len(products):
        raise PriceError("SOURCE_PRODUCT_COUNT_MISMATCH")
    keys=set()
    product_rates=[]
    total_gb=0.0
    for entry in products:
        if not isinstance(entry,dict):
            raise PriceError("SOURCE_PRODUCT_LINE_INVALID")
        key=entry.get("productKey")
        name=entry.get("productName")
        if not isinstance(key,str) or not key.strip() or len(key)>100 or key in keys or not isinstance(name,str) or not name.strip() or len(name)>230:
            raise PriceError("SOURCE_PRODUCT_IDENTITY_AMBIGUOUS")
        keys.add(key)
        qty=number(entry.get("sourceQty"))
        if qty!=source_samples:
            raise PriceError("MULTI_PRODUCT_DIFFERENT_QUANTITY_UNSUPPORTED")
        gb=entry.get("dataGbPerSample")
        if isinstance(gb,bool) or not isinstance(gb,(int,float)) or not math.isfinite(gb) or gb<0:
            raise PriceError("PRODUCT_DATA_SIZE_UNVERIFIED")
        total_gb+=gb
        lines=entry.get("processPriceLines")
        if not isinstance(lines,list) or not 1<=len(lines)<=25:
            raise PriceError("SOURCE_PRODUCT_PROCESSES_MISSING")
        unit=0
        for line in lines:
            if not isinstance(line,dict) or line.get("isCloud") is not False or not isinstance(line.get("processName"),str) or not line["processName"].strip():
                raise PriceError("SOURCE_PRODUCT_PROCESS_UNCLASSIFIED")
            rate=number(line.get("unitPriceKrw"))
            process_qty=number(line.get("sourceQty"))
            line_net=number(line.get("sourceNetKrw"))
            if process_qty!=source_samples or line_net!=rate*process_qty:
                raise PriceError("PROCESS_LINE_ARITHMETIC_MISMATCH")
            unit+=rate
        original_net=number(entry.get("sourceNetKrw"))
        if original_net!=unit*source_samples or unit<=0:
            raise PriceError("SOURCE_PRODUCT_NET_MISMATCH")
        product_rates.append((name,unit))
    if not math.isclose(total_gb,gb_per_sample,rel_tol=0,abs_tol=1e-9):
        raise PriceError("PRODUCT_DATA_SIZE_SUM_MISMATCH")
    cloud=quote.get("cloudProcessLine")
    if not isinstance(cloud,dict) or cloud.get("isCloud") is not True:
        raise PriceError("SOURCE_SHARED_CLOUD_UNVERIFIED")
    cloud_rate=number(cloud.get("unitPriceKrw"))
    original_cloud_qty=number(cloud.get("sourceQty"))
    original_cloud_net=number(cloud.get("sourceNetKrw"))
    expected_cloud=math.ceil(source_samples*gb_per_sample/100)
    if (original_cloud_qty!=expected_cloud or original_cloud_net!=cloud_rate*expected_cloud
            or original_cloud_qty!=quote.get("sourceCloudUnits")
            or cloud_rate!=quote.get("cloudUnitNetKrw")):
        raise PriceError("SOURCE_SHARED_CLOUD_MISMATCH")
    source_net=source_samples*sum(rate for _,rate in product_rates)+original_cloud_net
    if number(quote.get("totalPriceKrw"))!=source_net:
        raise PriceError("SOURCE_QUOTE_RECONCILIATION_FAILED")
    if number(quote.get("grandTotalKrw"))*10!=source_net*11:
        raise PriceError("SOURCE_VAT_RECONCILIATION_FAILED")
    requested_cloud_rate=number(cloud_override,allow_blank=True)
    is_override=requested_cloud_rate is not None and requested_cloud_rate!=cloud_rate
    if requested_cloud_rate is None:
        requested_cloud_rate=cloud_rate
    details=[{"product":name,"unit_krw":unit,"qty":samples,"net_krw":unit*samples}
             for name,unit in product_rates]
    product_net=sum(item["net_krw"] for item in details)
    cloud_qty=math.ceil(samples*gb_per_sample/100)
    cloud_net=requested_cloud_rate*cloud_qty
    net=product_net+cloud_net
    if net>1000000000000 or net%10:
        raise PriceError("VAT_ROUNDING_REVIEW_REQUIRED")
    description="; ".join(f'{item["product"]}: {item["qty"]} x {item["unit_krw"]} = {item["net_krw"]} KRW' for item in details)
    if is_override:
        description+="; USER_CLOUD_OVERRIDE_REQUIRES_APPROVAL"
    return {
        "Source Product Name":"; ".join(item["product"] for item in details)[:230],
        # A single average rate would conceal multiple distinct Product prices.
        "Sample Unit KRW":"","Product Unit KRW":"",
        "Product Qty":sum(item["qty"] for item in details),
        "Product Net KRW":product_net,
        "Cloud Unit KRW":requested_cloud_rate,"Cloud Qty":cloud_qty,
        "Cloud Net KRW":cloud_net,"Quote Net KRW":net,
        "VAT KRW":net//10,"Quote Gross KRW":net*11//10,
        "Price Basis":"SOURCE_VERIFIED_MULTI_PRODUCT_LINES"+("_OVERRIDDEN" if is_override else ""),
        "Price Status":"MANUAL_OVERRIDE_REVIEW_REQUIRED" if is_override else "SOURCE_VERIFIED_MULTI_PRODUCT_PROJECTION",
        "Product Price Detail":description[:1500],
        "Product Price Items JSON":json.dumps(details,ensure_ascii=False,separators=(",",":")),
    }
