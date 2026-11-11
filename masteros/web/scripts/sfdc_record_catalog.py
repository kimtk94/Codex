"""Read-only SFDC Lead / Opportunity / Quotation picker using authenticated local Chrome.

Never writes to Salesforce, saves snapshots, or logs emails/contacts.
List is Salesforce's selected list view; search is performed by its native UI.
Details use record IDs only and return explicitly verified fields.
"""
from __future__ import annotations
import json
import re
import os
import sys
from datetime import date, timedelta

BASE="https://novogene.lightning.force.com"
OBJECTS={"lead":("Lead","00Q"),"opportunity":("Opportunity","006"),"quote":("Quotation__c","a0P")}
def stop(message):raise ValueError(message)
def txt(x):return str(x or "").strip()
def rec_id(x,prefix):
    return isinstance(x,str) and re.fullmatch(prefix+r"[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?",x) is not None
def check(inp):
    if not isinstance(inp,dict) or inp.get("resource") not in OBJECTS or inp.get("mode") not in ("list","detail","bundle"):
        stop("INVALID_OPERATION")
    if inp["mode"]=="list":
        if not isinstance(inp.get("query",""),str) or len(inp.get("query",""))>100:stop("INVALID_SEARCH")
    elif inp["mode"]=="bundle":
        if inp["resource"]!="opportunity" or not rec_id(inp.get("recordId"),"006"):
            stop("INVALID_BUNDLE_RECORD")
    elif not rec_id(inp.get("recordId"),OBJECTS[inp["resource"]][1]):stop("INVALID_RECORD_ID")
    if "forceLive" in inp and not isinstance(inp["forceLive"],bool):
        stop("LIVE_FLAG_INVALID")
    if inp.get("forceLive") is True and inp["mode"]!="detail":
        stop("LIVE_MODE_DETAIL_REQUIRED")
    return inp
def fields(page):
    result={}
    for item in page.locator('[field-label]').all():
        key=txt(item.get_attribute('field-label'))
        value=txt(item.inner_text())
        lines=[x.strip() for x in value.splitlines() if x.strip()]
        if lines and lines[0]==key:lines=lines[1:]
        lines=[v for v in lines if v not in ("Edit "+key, "Preview", "Change Owner")]
        if key and lines:result[key]=" ".join(lines[:5])[:240]
    return result
def hyperlinks(page):
    return page.locator('a[href*="/lightning/r/"]').evaluate_all("""es=>es.map(e=>({
        text:(e.innerText||'').trim().slice(0,200),href:e.getAttribute('href')||''
    }))""")
def find_href(links,prefix):
    for item in links:
        m=re.search(r"/lightning/r/(?:[A-Za-z_]+/)?("+prefix+r"[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?)/view",item["href"])
        if m:return {"id":m.group(1),"name":item["text"]}
    return None
def val_after(body,label):
    lines=[l.strip() for l in body.splitlines() if l.strip()]
    for i,s in enumerate(lines):
        if s==label and i+1<len(lines):
            cand=lines[i+1]
            if cand not in ["Edit "+label,"Preview","Edit","Tabs"] and not cand.startswith("Edit "):return cand[:230]
    return ""
def parse_us_date(raw):
    try:
        m=re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})",raw)
        if not m:return ""
        return date(int(m[3]),int(m[1]),int(m[2])).isoformat()
    except (ValueError,TypeError):return ""
def parse_money(raw):
    m=re.search(r"([\d,]+)(?:\.\d+)?",raw)
    return int(m.group(1).replace(",","")) if m else 0

def list_items(page,resource,query):
    name,_=OBJECTS[resource]
    page.goto(BASE+"/lightning/o/"+name+"/list",wait_until="domcontentloaded",timeout=28000)
    search=page.locator('input[placeholder="Search this list..."]')
    search.wait_for(state="visible",timeout=12000)
    if query:
        search.fill(query,timeout=5000)
        search.press("Enter",timeout=5000)
        page.wait_for_timeout(1000)
    rows=page.locator("table tbody tr")
    for _ in range(22):
        if rows.count()>0:break
        page.wait_for_timeout(250)
    data=[]
    for row in rows.all()[:30]:
        items=row.locator("td").all_inner_texts()
        links=row.locator("a").evaluate_all("""es=>es.map(x=>({name:x.innerText.trim(),href:x.getAttribute('href')||''}))""")
        rid=find_href([{"text":v["name"],"href":v["href"]} for v in links],OBJECTS[resource][1])
        if not rid:continue
        out={"id":rid["id"],"name":rid["name"]}
        if resource=="lead":
            out.update({"institution":txt(items[3]) if len(items)>3 else "",
                        "status":txt(items[7]) if len(items)>7 else ""})
        elif resource=="opportunity":
            out.update({"institution":txt(items[1]) if len(items)>1 else "",
                        "contact":txt(items[2]) if len(items)>2 else "",
                        "status":txt(items[3]) if len(items)>3 else "",
                        "amount":txt(items[4]) if len(items)>4 else ""})
        else:
            out.update({"name":txt(items[1]) if len(items)>1 else rid["name"],
                        "quotationNumber":txt(items[2]) if len(items)>2 else "",
                        "status":txt(items[3]) if len(items)>3 else "",
                        "contact":txt(items[4]) if len(items)>4 else ""})
        data.append(out)
    # Salesforce list view may be scoped to Recently Viewed, do not promise all company records.
    return {"status":"PASS","resource":resource,"scope":"SALESFORCE_CURRENT_LIST_VIEW",
            "query":query,"records":data,"count":len(data),"max_results":30,
            "read_only":True}


def category_for_product(product_name):
    """Resolve only an exact product-category match from the local private catalog."""
    from pathlib import Path
    cached = Path.home()/".sfdc_desktop"/"quote_product_catalog_all_p1_PRIVATE.json"
    if not cached.is_file() or not product_name:
        return ""
    try:
        categories=json.loads(cached.read_text(encoding="utf-8")).get("categories",[])
        matches=[c["category"] for c in categories
                 if product_name in c.get("visible_lines_after",[]) and c.get("found") is True]
        return matches[0] if len(matches)==1 else ""
    except (ValueError,KeyError,TypeError):
        return ""

def source_quote_product(page,quote_id,product_id,net_price):
    """Read source line. Single-line invoice net has priority over Sales Price."""
    result={"pricingStatus":"REVIEW_REQUIRED","productConfigurationStatus":"PARTIAL_REVIEW_REQUIRED"}
    if not product_id:
        return result
    page.goto(BASE+"/lightning/r/Quotation_Products__c/"+product_id+"/view",
              wait_until="domcontentloaded",timeout=28000)
    detail=page.get_by_role("tab",name="Details",exact=True)
    detail.wait_for(state="visible",timeout=10000)
    detail.click(timeout=5500)
    page.wait_for_timeout(300)
    f=fields(page)
    source_line_price=parse_money(f.get("Total Price",""))
    raw_qty=f.get("Sample Quantity","")
    try:sample_count=int(float(raw_qty.replace(",","")))
    except (ValueError,TypeError):sample_count=0
    product_name=f.get("Product Name","")
    process_names=f.get("Quotation Process Name","")
    requirement=f.get("Data Requirement","")
    data_size=None
    m=re.search(r"(\d+(?:\.\d+)?)\s*(?:G|Gb)\s+of\s+raw\s+data\s+per\s+sample",requirement,re.I)
    if m:data_size=float(m.group(1))
    unique_price=(
        net_price>0 and source_line_price==net_price and sample_count>0
        and (source_line_price % sample_count)==0
        and bool(product_name and process_names)
    )
    result.update({
        "productName":product_name,
        "productCategory":category_for_product(product_name),
        "processNames":process_names,
        "samples":sample_count if sample_count else None,
        "dataSize":data_size,
        "sourceDataRequirement":requirement,
        "sourceLineNetKrw":source_line_price,
        "unitPriceNetKrw":source_line_price//sample_count if unique_price else None,
        "pricingStatus":"VERIFIED_SINGLE_LINE" if unique_price else "REVIEW_REQUIRED",
        "productConfigurationStatus":"LINE_FIELDS_READ" if unique_price else "PARTIAL_REVIEW_REQUIRED",
        "pricingMethod":"SOURCE_QUOTE_NET_DIVIDED_BY_SAMPLE_COUNT",
        "priceIsEstimateForChangedQuantity":True,
    })
    return result

def read_multi_product_evidence(page, quote_id, product_ids):
    """Read each Quote Product record, but DO NOT infer process-level prices.

    A product detail Total Price may include shared process/Cloud costs.
    Until the Quote's original process-price matrix has an explicit and unique
    mapping to every child Product, the result is EVIDENCE_ONLY.
    """
    if not isinstance(product_ids,list) or not 2<=len(product_ids)<=12 or len(set(product_ids))!=len(product_ids):
        raise ValueError("SOURCE_PRODUCT_LINKS_NOT_UNIQUE")
    details=[]
    for pid in product_ids:
        if not rec_id(pid,"a0N"):
            raise ValueError("SOURCE_PRODUCT_LINK_INVALID")
        child=source_quote_product(page,quote_id,pid,0)
        parent=find_href(hyperlinks(page),"a0P") or {}
        if parent.get("id") != quote_id:
            raise ValueError("SOURCE_PRODUCT_PARENT_UNVERIFIED")
        if not (child.get("productName") and isinstance(child.get("samples"),int)
                and child.get("samples")>0
                and isinstance(child.get("dataSize"),(int,float))
                and child.get("dataSize")>0
                and isinstance(child.get("sourceLineNetKrw"),int)
                and child.get("sourceLineNetKrw")>0):
            raise ValueError("SOURCE_PRODUCT_FIELDS_INCOMPLETE")
        details.append({
            "productKey":pid,
            "productName":child["productName"],
            "sourceQty":child["samples"],
            "dataGbPerSample":child["dataSize"],
            "observedProductTotalKrw":child["sourceLineNetKrw"],
            "sourceProcessNames":child.get("processNames",""),
            "evidenceStatus":"PRODUCT_DETAIL_ONLY_NO_PROCESS_PRICE_MAPPING",
        })
    return details


def parse_process_price_rows(rows,source_samples,gb_per_sample,expected_net):
    """Validate per-process sample fees and 100-Gb Cloud blocks against Quote net."""
    from math import ceil
    if not isinstance(rows,list) or not 1<=len(rows)-1<=25:
        raise ValueError("PROCESS_TABLE_MISSING")
    head=[str(v).strip() for v in rows[0]]
    expected=["Pack No.","Process Name","Process Type","Sample Number",
              "Data Size","Data Unit","Unit Price","Total Price"]
    if head[1:]!=expected:
        raise ValueError("PROCESS_SCHEMA_UNEXPECTED")
    parsed=[]
    for cells in rows[1:]:
        if not isinstance(cells,list) or len(cells)!=9:
            raise ValueError("PROCESS_ROW_INVALID")
        try:
            qty=int(str(cells[4]).replace(",",""))
            rate=int(str(cells[7]).replace(",",""))
            total=int(str(cells[8]).replace(",",""))
            size=float(str(cells[5]).replace(",",""))
        except (ValueError,TypeError) as exc:
            raise ValueError("PROCESS_NUMERIC_INVALID") from exc
        if qty<=0 or rate<0 or qty*rate!=total or size<=0:
            raise ValueError("PROCESS_ARITHMETIC_INVALID")
        cloud=bool(re.search(r"(?i)(?:ali\s*)?cloud",str(cells[3])+" "+str(cells[2])))
        if cloud:
            if qty!=ceil(source_samples*gb_per_sample/100):
                raise ValueError("SOURCE_CLOUD_QTY_INCORRECT")
        elif qty!=source_samples:
            raise ValueError("NONCLOUD_NON_SAMPLE_QUANTITY")
        parsed.append({"processType":str(cells[2]).strip(),
          "processName":str(cells[3]).strip(),"packNo":str(cells[1]).strip()[:80],"sourceQty":qty,
          "dataSize":size,"dataUnit":str(cells[6]).strip(),
          "unitPriceKrw":rate,"sourceNetKrw":total,"isCloud":cloud})
    if sum(x["sourceNetKrw"] for x in parsed)!=expected_net:
        raise ValueError("PROCESS_NET_SUM_MISMATCH")
    clouds=[r for r in parsed if r["isCloud"]]
    if len(clouds)>1:
        raise ValueError("MULTIPLE_CLOUD_PROCESSES_UNSUPPORTED")
    sample_unit=sum(x["unitPriceKrw"] for x in parsed if not x["isCloud"])
    cloud_unit=sum(x["unitPriceKrw"] for x in clouds)
    if sample_unit==0 and cloud_unit==0:
        raise ValueError("NO_PRICED_PROCESS")
    return {"pricingStatus":"VERIFIED_PROCESS_LINES",
      "processPriceLines":parsed,"sampleUnitNetKrw":sample_unit,
      "cloudUnitNetKrw":cloud_unit,
      "sourceCloudUnits":ceil(source_samples*gb_per_sample/100),
      "cloudLinePresent":bool(clouds),
      "sourceProcessNetKrw":expected_net,
      "pricingMethod":"SUM_PROCESS_QTY_TIMES_UNIT_PRICE"}

def quote_price_breakdown(page,quote_id,source_samples,gb_per_sample,expected_net):
    """Get process rows from Quote Detail, NOT Add/Edit (which modifies the source)."""
    page.goto(BASE+"/lightning/r/Quotation__c/"+quote_id+"/view",
              wait_until="domcontentloaded",timeout=28000)
    page.get_by_role("tab",name="Quotation Detail",exact=True).click(timeout=5500)
    table=page.locator("table").filter(has_text="Process Name").filter(has_text="Unit Price")
    table.first.wait_for(state="visible",timeout=14000)
    if table.count()!=1:
        raise ValueError("PROCESS_TABLE_NOT_UNIQUE")
    rows=table.locator("tr").evaluate_all(
        """es=>es.map(tr=>[...tr.querySelectorAll(':scope>th,:scope>td')]
        .map(c=>c.innerText.trim().replace(/\\s+/g,' ')))""")
    return parse_process_price_rows(rows,source_samples,gb_per_sample,expected_net)


def linked_oppo_quote_bundle(page,oppo_id):
    """Resolve Quote by exact parent ID; never select a different customer's quote."""
    opp=read_item(page,"opportunity",oppo_id)
    quote_list=list_items(page,"quote",opp["name"])
    matched=[]
    for candidate in quote_list.get("records",[])[:6]:
        if not rec_id(candidate.get("id"),"a0P"):
            continue
        try:
            quote=read_item(page,"quote",candidate["id"])
            if quote.get("opportunityId")==oppo_id:
                matched.append(quote)
        except Exception:
            continue
    return {"status":"PASS","resource":"opportunity","mode":"bundle",
        "opportunity":opp,"linkedQuotes":matched,
        "quoteCount":len(matched),"selectionStatus":
            "EXACT_ONE" if len(matched)==1 else
            "NO_MATCH" if not matched else "MULTIPLE_SELECT_REQUIRED",
        "read_only":True}


def read_item(page,resource,record_id):
    name,_=OBJECTS[resource]
    page.goto(BASE+"/lightning/r/"+name+"/"+record_id+"/view",wait_until="domcontentloaded",timeout=28000)
    details=page.get_by_role("tab",name="Details",exact=True)
    details.wait_for(state="visible",timeout=13000)
    details.click(timeout=5500)
    page.wait_for_timeout(400)
    f=fields(page)
    body=page.locator("body").inner_text()
    links=hyperlinks(page)
    out={"status":"PASS","resource":resource,"id":record_id,"source":"LIVE_SALESFORCE",
         "read_only":True}
    if resource=="lead":
        label=f.get("Name") or page.title().split(" | ")[0]
        out.update({"name":label, "accountName":f.get("Company",""),
                   "koreanName":re.sub(r"\s+","",label) if re.search("[가-힣]",label) else "",
                   "englishName":f.get("English Name",""),
                   "leadStatus":f.get("Lead Status") or f.get("Status",""),
                   "email":f.get("Email",""),"company":f.get("Company","")})
    elif resource=="opportunity":
        account=find_href(links,"001") or {}
        contact=find_href(links,"003") or {}
        opp_name=f.get("Opportunity Name") or page.title().split(" | ")[0]
        amount=parse_money(f.get("Amount") or val_after(body,"Amount"))
        amount=f.get("Amount") or val_after(body,"Amount")
        sample_text=f.get("Sample Quantity") or val_after(body,"Sample Quantity")
        sample=re.search(r"\d+",sample_text)
        if not sample:
            sample=re.search(r"-(\d{1,3})(?=-[A-Za-z])",opp_name)
        data_size=re.search(r"(?<!\d)(\d+(?:\.\d+)?)\s*(Gb|GB|Mreads|M reads)\b",opp_name,re.I)
        out.update({"name":opp_name,"accountId":account.get("id",""),
                    "accountName":account.get("name",""),"contactId":contact.get("id",""),
                    "contactName":contact.get("name",""),"amountKrw":parse_money(amount),
                    "closeDate":parse_us_date(f.get("Close Date") or val_after(body,"Close Date")),
                    "samples":int(sample.group(1) if sample.lastindex else sample.group()) if sample else None,
                    "samplesSource":"OPPO_NAME_ESTIMATE" if not sample_text and sample else "SFDC_FIELD" if sample else "UNVERIFIED",
                    "service":f.get("Service Line") or val_after(body,"Service Line"),
                    "dataSize":float(data_size.group(1)) if data_size else None,
                    "unit":"Gb" if data_size and "gb" in data_size.group(2).lower() else "Mreads" if data_size else "",
                    "progressDescriptionSource":f.get("Progress Description",""),
                    "dataSizeSource":"OPPO_NAME_ESTIMATE" if data_size else "UNVERIFIED",
                    "referenceOpportunityId":record_id})
    else:
        account=find_href(links,"001") or {}
        contact=find_href(links,"003") or {}
        opportunity=find_href(links,"006") or {}
        quote_name=f.get("Quotation Name") or val_after(body,"Quotation Name")
        original_amount=parse_money(f.get("Total Price") or val_after(body,"Total Price"))
        out.update({"name":quote_name,"sourceQuoteId":record_id,
                    "opportunityId":opportunity.get("id",""),
                    "opportunityName":opportunity.get("name",""),
                    "accountId":account.get("id",""),"accountName":account.get("name",""),
                    "contactId":contact.get("id",""),"contactName":contact.get("name",""),
                    "quotationNumber":f.get("Quotation ID") or val_after(body,"Quotation ID"),
                    "totalPriceKrw":original_amount,"grandTotalKrw":parse_money(f.get("Grand Total") or val_after(body,"Grand Total")),"productName":"",
                    "productCategory":"","processNames":"","samples":None,"dataSize":None})
        related=page.get_by_role("tab",name="Related",exact=True)
        if related.count()==1:
            related.click(timeout=5500)
            for _ in range(16):
                if page.locator('a[href*="/lightning/r/a0N"]').count()>0:break
                page.wait_for_timeout(300)
            prod_links=hyperlinks(page)
            product=find_href(prod_links,"01t") or {}
            if product:
                out["productName"]=product.get("name","")
                out["productId"]=product.get("id","")
            product_detail=find_href(prod_links,"a0N") or {}
            if product_detail:out["quotationProductId"]=product_detail.get("id","")
            out["productCount"]=int(re.search(r"Quotation Products\s*\((\d+)\)",page.locator("body").inner_text()).group(1)) if re.search(r"Quotation Products\s*\((\d+)\)",page.locator("body").inner_text()) else None
            if isinstance(out.get("productCount"),int) and out["productCount"]>1:
                ids=[]
                for item in prod_links:
                    found=re.search(r"/lightning/r/(?:[A-Za-z_]+/)?(a0N[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?)/view",item.get("href",""))
                    if found and found.group(1) not in ids:ids.append(found.group(1))
                out["pricingStatus"]="MULTI_PRODUCT_PROCESS_BREAKDOWN_UNVERIFIED"
                out["multiSourceDetailStatus"]="PRODUCT_LINKS_UNVERIFIED"
                if len(ids)==out["productCount"]:
                    try:
                        out["sourceProductEvidence"]=read_multi_product_evidence(page,record_id,ids)
                        out["multiSourceDetailStatus"]="PRODUCT_DETAILS_READ_ONLY_NO_PROCESS_PRICE_MAPPING"
                    except Exception as exc:
                        out["multiSourceDetailStatus"]=str(exc) if isinstance(exc,ValueError) and re.fullmatch(r"[A-Z0-9_]{5,90}",str(exc)) else "SOURCE_PRODUCT_UI_UNAVAILABLE"
        out["productConfigurationStatus"]="PARTIAL_REVIEW_REQUIRED"
        if out.get("productCount")==1 and out.get("quotationProductId"):
            product_fields=source_quote_product(
                page,record_id,out["quotationProductId"],original_amount)
            out.update(product_fields)
            if out.get("unitPriceNetKrw") and out.get("grandTotalKrw"):
                out["sourceVatRateVerified10Pct"]=(
                    out["grandTotalKrw"]*10==original_amount*11)
            if out.get("samples") and out.get("dataSize") and out.get("sourceVatRateVerified10Pct"):
                try:
                    out.update(quote_price_breakdown(
                        page,record_id,out["samples"],out["dataSize"],original_amount))
                except Exception as exc:
                    out["pricingStatus"]="PROCESS_BREAKDOWN_UNVERIFIED"
                    out["processBreakdownErrorType"]=type(exc).__name__
    return out

def main():
    try:
        request=check(json.loads(sys.stdin.buffer.read(3000).decode("utf-8")))
        from sfdc_pair_cache import key_for, lookup, save, live_meta
        identity=key_for(request)
        cached=lookup(request) if identity and os.getenv("SFDC_PAIR_CACHE_ENABLED","1")=="1" and not request.get("forceLive") else None
        if cached is not None:
            out=cached
        else:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as pw:
                browser=pw.chromium.connect_over_cdp("http://127.0.0.1:9222",timeout=10000)
                page=browser.contexts[0].new_page()
                try:
                    if request["mode"]=="list":out=list_items(page,request["resource"],request.get("query",""))
                    elif request["mode"]=="bundle":out=linked_oppo_quote_bundle(page,request["recordId"])
                    else:out=read_item(page,request["resource"],request["recordId"])
                finally:page.close()
            if identity and out.get("status")=="PASS":
                # Write only once after a successful authenticated UI fetch. Cache
                # failures must never turn a good live read into a source failure.
                try:
                    if os.getenv("SFDC_PAIR_CACHE_ENABLED","1")=="1":
                        save(request,out)
                    out["cache"]=live_meta(identity[1])
                except (OSError,ValueError):
                    pass
    except Exception as exc:
        out={"status":"BLOCK","code":str(exc) if isinstance(exc,ValueError) and re.fullmatch("[A-Z_]{4,60}",str(exc)) else "SFDC_UI_"+type(exc).__name__}
    print(json.dumps(out,ensure_ascii=False,separators=(",",":")))
if __name__=="__main__":main()
