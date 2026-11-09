"""Read-only SFDC Lead / Opportunity / Quotation picker using authenticated local Chrome.

Never writes to Salesforce, saves snapshots, or logs emails/contacts.
List is Salesforce's selected list view; search is performed by its native UI.
Details use record IDs only and return explicitly verified fields.
"""
from __future__ import annotations
import json
import re
import sys
from datetime import date, timedelta

BASE="https://novogene.lightning.force.com"
OBJECTS={"lead":("Lead","00Q"),"opportunity":("Opportunity","006"),"quote":("Quotation__c","a0P")}
def stop(message):raise ValueError(message)
def txt(x):return str(x or "").strip()
def rec_id(x,prefix):
    return isinstance(x,str) and re.fullmatch(prefix+r"[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?",x) is not None
def check(inp):
    if not isinstance(inp,dict) or inp.get("resource") not in OBJECTS or inp.get("mode") not in ("list","detail"):
        stop("INVALID_OPERATION")
    if inp["mode"]=="list":
        if not isinstance(inp.get("query",""),str) or len(inp.get("query",""))>100:stop("INVALID_SEARCH")
    elif not rec_id(inp.get("recordId"),OBJECTS[inp["resource"]][1]):stop("INVALID_RECORD_ID")
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
                    "totalPriceKrw":original_amount,"productName":"",
                    "productCategory":"","processNames":"","samples":None,"dataSize":None})
        related=page.get_by_role("tab",name="Related",exact=True)
        if related.count()==1:
            related.click(timeout=5500)
            page.wait_for_timeout(500)
            prod_links=hyperlinks(page)
            product=find_href(prod_links,"01t") or {}
            if product:
                out["productName"]=product.get("name","")
                out["productId"]=product.get("id","")
            product_detail=find_href(prod_links,"a0N") or {}
            if product_detail:out["quotationProductId"]=product_detail.get("id","")
            out["productCount"]=int(re.search(r"Quotation Products\s*\((\d+)\)",page.locator("body").inner_text()).group(1)) if re.search(r"Quotation Products\s*\((\d+)\)",page.locator("body").inner_text()) else None
        out["productConfigurationStatus"]="PARTIAL_REVIEW_REQUIRED"
    return out

def main():
    try:
        request=check(json.loads(sys.stdin.buffer.read(3000).decode("utf-8")))
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            browser=pw.chromium.connect_over_cdp("http://127.0.0.1:9222",timeout=10000)
            page=browser.contexts[0].new_page()
            try:
                if request["mode"]=="list":out=list_items(page,request["resource"],request.get("query",""))
                else:out=read_item(page,request["resource"],request["recordId"])
            finally:page.close()
    except Exception as exc:
        out={"status":"BLOCK","code":str(exc) if isinstance(exc,ValueError) and re.fullmatch("[A-Z_]{4,60}",str(exc)) else "SFDC_UI_"+type(exc).__name__}
    print(json.dumps(out,ensure_ascii=False,separators=(",",":")))
if __name__=="__main__":main()
