"""Local Playwright SFDC actions. Input JSON from stdin, output sanitized JSON only.

No app secrets are transferred to the browser. Fail closed whenever a DOM field,
account/contact identity or product is ambiguous. A save is never reported as
verified without independently opening the created Salesforce record.
"""
import datetime as dt
import json
import re
import sys
from playwright.sync_api import sync_playwright

BASE="https://novogene.lightning.force.com"
ID=lambda prefix,x:bool(isinstance(x,str) and re.fullmatch(prefix+r"[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?",x))
def block(code,**extra):return {"status":"BLOCK","code":code,**extra}
def single(loc,code):
    if loc.count()!=1:raise RuntimeError(code)
    return loc
def select_by_value(pg,label,value):
    btn=single(pg.locator('button[aria-label="'+label+'"]:visible'),"PICKLIST_NOT_UNIQUE")
    btn.click(timeout=5000)
    op=single(pg.locator('lightning-base-combobox-item[role=option][data-value="'+value+'"]:visible'),"PICKLIST_VALUE_NOT_UNIQUE")
    op.click(timeout=5000)
    if btn.get_attribute("data-value")!=value:raise RuntimeError("PICKLIST_READBACK_FAIL")
def resolve_lookup(pg,label,key,search):
    x=pg.locator('input[aria-label="'+label+'"]:visible')
    x=single(x,"LOOKUP_INPUT_NOT_UNIQUE")
    clear=pg.get_by_role("button",name="Clear "+label+" Selection")
    if clear.count()==1:clear.click(timeout=4500)
    x.fill(search,timeout=5000)
    opt=pg.locator('lightning-base-combobox-item[role=option][data-value="'+key+'"]')
    for _ in range(20):
        if opt.count()==1:break
        pg.wait_for_timeout(250)
    if opt.count()!=1:
        raise RuntimeError(("ACCOUNT_" if label=="Account Name" else "CONTACT_")+"LOOKUP_ID_COUNT_"+str(opt.count()))
    opt=single(opt,"LOOKUP_OPTION_INVALID")
    if "Create New" in opt.inner_text(timeout=2000):raise RuntimeError("CREATE_NEW_OPTION_FORBIDDEN")
    opt.click(timeout=5000)
    if not x.input_value().strip():raise RuntimeError("LOOKUP_SELECT_FAILED")
    pg.wait_for_timeout(600)
def strict_date(x):
    try:dt.date.fromisoformat(x);return True
    except (ValueError,TypeError):return False
def local_validator(x):
    if x.get("action") not in ("lead_convert","opportunity_create","quote_create") or x.get("mode") not in ("check","save"):
        raise ValueError("INVALID_ACTION")
    if x["mode"]=="save" and (x.get("confirmSave") is not True or x.get("noDuplicateConfirmed") is not True):
        raise ValueError("EXPLICIT_CONFIRMATION_REQUIRED")
    if x["action"]=="lead_convert":
        if not ID("00Q",x.get("leadId")) or not all(x.get(k) for k in ("accountName","koreanName","englishName")):
            raise ValueError("LEAD_INPUT_INVALID")
    if x["action"]=="opportunity_create":
        if not (ID("006",x.get("referenceOpportunityId")) and ID("001",x.get("accountId"))
                and ID("003",x.get("contactId")) and strict_date(x.get("closeDate"))):
            raise ValueError("OPPO_IDS_INVALID")
        if not (x.get("opportunityName") and x.get("accountName") and x.get("contactName")
                and x.get("progressDescription") and isinstance(x.get("samples"),int) and x["samples"]>0
                and isinstance(x.get("amountKrw"),int) and x["amountKrw"]>=0):
            raise ValueError("OPPO_VALUES_INVALID")
    if x["action"]=="quote_create":
        if not (ID("006",x.get("opportunityId")) and ID("a0P",x.get("sourceQuoteId"))):
            raise ValueError("QUOTE_IDS_INVALID")
        if not all(x.get(k) for k in ("quoteName","accountName","contactName","productName","productCategory","processNames")):
            raise ValueError("QUOTE_VALUES_INVALID")
        if not isinstance(x.get("samples"),int) or not 1<=x["samples"]<=500 or not isinstance(x.get("dataSize"),(int,float)) or x["dataSize"]<=0:
            raise ValueError("QUOTE_QUANTITY_INVALID")
def lead_convert(page,x):
    page.goto(BASE+"/lightning/r/Lead/"+x["leadId"]+"/view",wait_until="domcontentloaded",timeout=30000)
    convert=page.get_by_text("Convert",exact=True)
    convert=single(convert.first if convert.count()>0 else convert,"LEAD_CONVERT_ACTION_MISSING")
    convert.click(timeout=6000)
    dlg=page.get_by_role("dialog").last
    dlg.get_by_text("Choose Existing",exact=True).first.wait_for(timeout=11000)
    dlg.get_by_text("Choose Existing",exact=True).first.click(timeout=5000)
    account=single(dlg.locator('input[placeholder="Search for matching accounts"]'),"LEAD_ACCOUNT_LOOKUP_MISSING")
    account.fill(x["accountName"],timeout=5000)
    page.wait_for_timeout(900)
    exact=dlg.locator('[role=option]:visible').filter(has_text=x["accountName"])
    if exact.count()!=1:raise RuntimeError("LEAD_ACCOUNT_AMBIGUOUS")
    if "Create New" in exact.first.inner_text():raise RuntimeError("LEAD_ACCOUNT_MUST_EXIST")
    exact.first.click(timeout=5000)
    dlg.get_by_role("button",name="Contact",exact=True).click(timeout=4500)
    for label,value in [("First Name",x["koreanName"]),("Last Name",x["englishName"])]:
        single(dlg.get_by_label(label,exact=True),"LEAD_CONTACT_FIELD_MISSING").fill(value,timeout=5000)
    dlg.get_by_role("button",name="Opportunity",exact=True).click(timeout=4500)
    opt=single(dlg.locator('input[type=checkbox]:not(:disabled)'),"LEAD_NO_OPPO_CHECKBOX_MISSING")
    if not opt.is_checked():opt.locator("xpath=..").click(timeout=4000)
    if not opt.is_checked():raise RuntimeError("LEAD_OPPO_NOT_DISABLED")
    status={"status":"PREFLIGHT_PASS","action":"lead_convert","opportunity_will_be_created":False,
            "new_account_will_be_created":False,"save_clicked":False}
    if x["mode"]=="check":
        single(dlg.get_by_role("button",name="Cancel",exact=True),"CANCEL_NOT_UNIQUE").click(timeout=4500)
        return status
    save=dlg.get_by_role("button",name="Convert",exact=True)
    save=single(save,"FINAL_CONVERT_ACTION_NOT_UNIQUE")
    save.click(timeout=7500)
    status["save_clicked"]=True
    page.wait_for_timeout(2400)
    page.goto(BASE+"/lightning/r/Lead/"+x["leadId"]+"/view",wait_until="domcontentloaded",timeout=28000)
    page.wait_for_timeout(1200)
    body=page.locator("body").inner_text()[:14000]
    converted=page.get_by_text("Convert",exact=True).count()==0 and "Converted" in body
    status["status"]="PASS" if converted else "SAVE_SUBMITTED_READBACK_REQUIRED"
    status["lead_id"]=x["leadId"]
    return status
def opportunity_create(page,x):
    url=BASE+"/lightning/r/Opportunity/"+x["referenceOpportunityId"]+"/clone"
    page.goto(url,wait_until="domcontentloaded",timeout=35000)
    name=page.locator('input[name="Name"]:visible')
    name.wait_for(timeout=20000)
    name=single(name,"OPPO_FORM_NOT_READY")
    original=name.input_value()
    if x["opportunityName"]==original:raise RuntimeError("DUPLICATE_REFERENCE_OPPORTUNITY_NAME")
    name.fill(x["opportunityName"],timeout=5500)
    amt=single(page.locator('input[name="Amount"]:visible'),"OPPO_AMOUNT_MISSING")
    amt.click();amt.press("ControlOrMeta+A");amt.press("Backspace")
    amt.type(str(x["amountKrw"]),delay=15);amt.press("Tab")
    for f,value in [("Sample_Quantity__c",str(x["samples"])),("CloseDate",dt.date.fromisoformat(x["closeDate"]).strftime("%m/%d/%Y"))]:
        single(page.locator('input[name="'+f+'"]:visible'),"OPPO_FIELD_MISSING").fill(value)
    resolve_lookup(page,"Account Name",x["accountId"],x["accountName"])
    resolve_lookup(page,"Main Contact",x["contactId"],x["contactName"])
    progress=single(page.locator('textarea[required]:visible'),"PROGRESS_FIELD_NOT_UNIQUE")
    progress.fill(x["progressDescription"],timeout=7000)
    select_by_value(page,"Stage","Prospective")
    if page.locator('button[aria-label="Forecast Category"]:visible').count()==1:
        select_by_value(page,"Forecast Category","Pipeline")
    if not name.input_value()==x["opportunityName"] or not progress.input_value()==x["progressDescription"]:
        raise RuntimeError("PROGRESS_OR_NAME_READBACK_MISMATCH")
    if not amt.input_value().replace(",","").startswith(str(x["amountKrw"])):
        raise RuntimeError("AMOUNT_READBACK_MISMATCH")
    r={"status":"PREFLIGHT_PASS","action":"opportunity_create","save_clicked":False,
       "progress_replaced":True,"reference_id":x["referenceOpportunityId"]}
    if x["mode"]=="check":
        single(page.get_by_role("button",name="Cancel",exact=True),"OPPO_CANCEL_MISSING").click()
        return r
    save=single(page.get_by_role("button",name="Save",exact=True),"OPPO_SAVE_AMBIGUOUS")
    if not save.is_enabled():raise RuntimeError("OPPO_SAVE_DISABLED")
    save.click(timeout=8000);r["save_clicked"]=True
    page.wait_for_timeout(2700)
    found=re.search(r"/Opportunity/(006[A-Za-z0-9]{15})/view",page.url)
    if not found:
        r["status"]="SAVE_SUBMITTED_READBACK_REQUIRED"
        return r
    record_id=found.group(1);r["record_id"]=record_id
    page.goto(BASE+"/lightning/r/Opportunity/"+record_id+"/view",wait_until="domcontentloaded",timeout=27000)
    page.wait_for_timeout(1600)
    detail=page.get_by_role("tab",name="Details",exact=True)
    if detail.count()==1:detail.click(timeout=4000)
    text=page.locator("body").inner_text(timeout=7000)
    r["status"]="PASS" if x["opportunityName"] in text and x["progressDescription"] in text else "SAVE_SUBMITTED_READBACK_REQUIRED"
    r["url"]=BASE+"/lightning/r/Opportunity/"+record_id+"/view"
    return r

def picklist(page,name,expected):
    cb=single(page.get_by_role("combobox",name=name,exact=True),"QUOTE_PICKLIST_UNIQUE")
    if expected in cb.inner_text():return
    controls=cb.get_attribute("aria-controls")
    cb.click(timeout=4500)
    options=page.locator('[id="'+str(controls)+'"]').locator('[role="option"]')
    target=options.filter(has_text=expected)
    if target.count()!=1:raise RuntimeError("QUOTE_PICKLIST_AMBIGUOUS")
    target.click(timeout=4500)
    if expected not in cb.inner_text(timeout=2500):raise RuntimeError("QUOTE_PICKLIST_NOT_SET")
def quote_lookup(page,label,search):
    cb=single(page.get_by_role("combobox",name=label,exact=True),"QUOTE_LOOKUP_MISSING")
    mag=cb.locator("xpath=../../..").locator('lightning-icon[icon-name="utility:search"]')
    if mag.count()!=1:raise RuntimeError("QUOTE_LOOKUP_MAGNIFIER_MISSING")
    mag.click(force=True,timeout=4500)
    cb.fill(search,timeout=4500)
    page.wait_for_timeout(1100)
    controls=cb.get_attribute("aria-controls")
    options=page.locator('[id="'+str(controls)+'"]').get_by_text(search,exact=True)
    if options.count()!=1:raise RuntimeError("QUOTE_LOOKUP_AMBIGUOUS")
    options.click(timeout=4500)
def verify_catalog(page,x):
    page.goto(BASE+"/lightning/r/Quotation__c/"+x["sourceQuoteId"]+"/view",wait_until="domcontentloaded",timeout=28000)
    page.get_by_role("tab",name="Quotation Detail",exact=True).click(timeout=5500)
    page.get_by_text("Add/Edit",exact=True).click(timeout=5500)
    cat=page.get_by_text(x["productCategory"],exact=True)
    if cat.count()<1:raise RuntimeError("QUOTE_CATEGORY_UNAVAILABLE")
    cat.first.click(timeout=5500)
    prod=page.get_by_text(x["productName"],exact=True)
    if prod.count()!=1:raise RuntimeError("EXISTING_PRODUCT_NOT_VERIFIED")
    # Verify existing product and requested process names without saving source.
    single(prod.locator("xpath=..").locator("button"),"SOURCE_PLUS_NOT_UNIQUE").click(timeout=5000)
    d=page.get_by_role("dialog").last
    single(d.get_by_label("Sample Number"),"SOURCE_SAMPLE_NUMBER_MISSING").fill(str(x["samples"]))
    single(d.get_by_label("Data Size"),"SOURCE_DATA_SIZE_MISSING").fill(str(x["dataSize"]))
    d.get_by_role("button",name="Next",exact=True).click(timeout=5000)
    for _ in range(14):
        page.wait_for_timeout(300)
        d=page.get_by_role("dialog").last
        if "Process List" in d.inner_text(timeout=3200):break
    if "Process List" not in d.inner_text():raise RuntimeError("SOURCE_PROCESS_LIST_MISSING")
    processes=[v.strip() for v in x["processNames"].split(",") if v.strip()]
    if not processes or len(processes)>12 or len(set(processes))!=len(processes):
        raise RuntimeError("SOURCE_PROCESS_SELECTION_INVALID")
    for process in processes:
        single(d.locator("tr").filter(has_text=process),"SOURCE_PROCESS_NOT_UNIQUE")
    # Never click Done/Save on source Quote. Navigation discards this preview.
    return True

def quote_create(page,x):
    verify_catalog(page,x)
    page.goto(BASE+"/lightning/r/Opportunity/"+x["opportunityId"]+"/view",wait_until="domcontentloaded",timeout=29000)
    page.get_by_role("tab",name="Related",exact=True).click(timeout=6000)
    # The second New button belongs to the Quotation related list in verified UI.
    buttons=page.get_by_role("button",name="New",exact=True)
    if buttons.count()<2:raise RuntimeError("QUOTE_NEW_BUTTON_NOT_VERIFIED")
    buttons.nth(1).click(timeout=5500)
    chooser=page.get_by_role("dialog").last
    chooser.get_by_text("Research-AMEA",exact=True).wait_for(timeout=11000)
    chooser.get_by_role("button",name="Next",exact=True).click(timeout=5500)
    parent=single(page.get_by_role("combobox",name="Opportunity Name",exact=True),"QUOTE_PARENT_MISSING")
    parent.wait_for(timeout=13000)
    lbl=single(page.get_by_text("Quotation Name",exact=True),"QUOTE_NAME_LABEL_MISSING")
    target=single(page.locator('textarea[id="'+str(lbl.get_attribute("for"))+'"]'),"QUOTE_NAME_FIELD_MISSING")
    target.fill(x["quoteName"],timeout=5000)
    picklist(page,"Business Entity","Novogene Korea Limited")
    picklist(page,"Currency","KRW")
    picklist(page,"Promotion Type","Regional level")
    picklist(page,"GST/VAT (%)","10(KR VAT)")
    quote_lookup(page,"Account Name",x["accountName"])
    quote_lookup(page,"Contact Name",x["contactName"])
    quote_lookup(page,"Coop TS","Yoo Ji In")
    picklist(page,"Bank Account Information","Korea JPMorgan KRW")
    picklist(page,"Sample Submission Address","Korea Sample Receiving Address")
    r={"action":"quote_create","status":"PREFLIGHT_PASS","save_clicked":False,
       "product_catalog_verified":True,"product_added":False,
       "parent_id":x["opportunityId"]}
    if x["mode"]=="check":return r
    # No Quote header is saved unless live quote product workflow is independently
    # verified for this exact product: avoids orphan headers or mispriced quotations.
    return save_quote_and_products(page,x,r)

def save_quote_and_products(page,x,r):
    quote_save=single(page.get_by_role("button",name="Save",exact=True),"QUOTE_SAVE_NOT_UNIQUE")
    if not quote_save.is_enabled():raise RuntimeError("QUOTE_SAVE_DISABLED")
    quote_save.click(timeout=6000)
    r["save_clicked"]=True
    page.wait_for_timeout(2300)
    match=re.search(r"/Quotation__c/(a0P[A-Za-z0-9]{15})/view",page.url)
    if not match:
        r["status"]="SAVE_SUBMITTED_READBACK_REQUIRED"
        return r
    quote_id=match.group(1)
    r["record_id"]=quote_id
    url=BASE+"/lightning/r/Quotation__c/"+quote_id+"/view"
    r["url"]=url
    try:
        page.goto(url,wait_until="domcontentloaded",timeout=28000)
        page.get_by_role("tab",name="Related",exact=True).click(timeout=5000)
        page.wait_for_timeout(700)
        before=page.locator("body").inner_text(timeout=6000)
        if not re.search(r"Quotation Products\s*\(0\)",before):
            raise RuntimeError("PRODUCTS_ALREADY_ATTACHED")
        page.get_by_role("tab",name="Quotation Detail",exact=True).click(timeout=5000)
        page.get_by_text("Add/Edit",exact=True).click(timeout=5500)
        group=page.get_by_text(x["productCategory"],exact=True)
        if group.count()<1:raise RuntimeError("PRODUCT_CATEGORY_NOT_FOUND")
        group.first.click(timeout=5500)
        product=single(page.get_by_text(x["productName"],exact=True),"PRODUCT_NOT_UNIQUE")
        single(product.locator("xpath=..").locator("button"),"PRODUCT_PLUS_MISSING").click(timeout=5500)
        modal=page.get_by_role("dialog").last
        sn=single(modal.get_by_label("Sample Number"),"SAMPLE_NUMBER_MISSING")
        data=single(modal.get_by_label("Data Size"),"DATA_SIZE_MISSING")
        sn.fill(str(x["samples"]))
        data.fill(str(x["dataSize"]))
        if float(sn.input_value())!=float(x["samples"]) or float(data.input_value())!=float(x["dataSize"]):
            raise RuntimeError("QTY_READBACK_MISMATCH")
        modal.get_by_role("button",name="Next",exact=True).click(timeout=6000)
        for _ in range(16):
            page.wait_for_timeout(320)
            modal=page.get_by_role("dialog").last
            if "Process List" in modal.inner_text(timeout=3000):break
        if "Process List" not in modal.inner_text():raise RuntimeError("PROCESS_LIST_MISSING")
        processes=[p.strip() for p in x["processNames"].split(",") if p.strip()]
        if len(processes)<1 or len(processes)>12 or len(set(processes))!=len(processes):
            raise RuntimeError("PROCESS_SELECTION_INVALID")
        for process in processes:
            row=single(modal.locator("tr").filter(has_text=process),"PROCESS_ROW_NOT_UNIQUE")
            checked=single(row.locator('input[type="checkbox"]'),"PROCESS_CHECKBOX_MISSING")
            if not checked.is_checked():
                single(row.locator("label[for]"),"PROCESS_LABEL_MISSING").click(timeout=4500)
            if not checked.is_checked():raise RuntimeError("PROCESS_NOT_SELECTED")
        modal.get_by_role("button",name="Done",exact=True).click(timeout=6000)
        page.wait_for_timeout(550)
        draft=page.locator("body").inner_text(timeout=5000)
        if x["productName"] not in draft:raise RuntimeError("DRAFT_PRODUCT_MISSING")
        save=single(page.get_by_role("button",name="Save",exact=True),"PRODUCT_SAVE_NOT_UNIQUE")
        if not save.is_enabled():raise RuntimeError("PRODUCT_SAVE_DISABLED")
        save.click(timeout=6000)
        r["product_save_clicked"]=True
        page.wait_for_timeout(1700)
        page.goto(url,wait_until="domcontentloaded",timeout=27000)
        page.get_by_role("tab",name="Related",exact=True).click(timeout=5000)
        page.wait_for_timeout(500)
        body=page.locator("body").inner_text(timeout=6000)
        count=re.search(r"Quotation Products\s*\((\d+)\)",body)
        r["product_added"]=bool(count and int(count.group(1))>0)
        r["status"]="PASS" if r["product_added"] else "PARTIAL_PRODUCT_READBACK_REQUIRED"
    except Exception as exc:
        r["status"]="PARTIAL_QUOTE_CREATED_PRODUCT_HOLD"
        r["product_error_type"]=type(exc).__name__
    return r

def main():
    try:
        x=json.loads(sys.stdin.buffer.read(14000).decode("utf-8"))
        local_validator(x)
        with sync_playwright() as pw:
            browser=pw.chromium.connect_over_cdp("http://127.0.0.1:9222",timeout=9000)
            page=browser.contexts[0].new_page()
            try:
                if x["action"]=="lead_convert":result=lead_convert(page,x)
                elif x["action"]=="opportunity_create":result=opportunity_create(page,x)
                else:result=quote_create(page,x)
            finally:
                page.close()
    except Exception as exc:
        code=str(exc) if isinstance(exc,RuntimeError) and re.fullmatch(r"[A-Z][A-Z0-9_]{4,80}",str(exc)) else "UI_"+type(exc).__name__
        result=block(code,detail="Salesforce 입력값 또는 UI 검증 차단")
    print(json.dumps(result,ensure_ascii=False,separators=(",",":")))
if __name__=="__main__":main()
