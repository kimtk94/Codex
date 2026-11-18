"""Authorized operator-PC SFDC UI rehearsal (no Save, no customer values).
Uses existing Chrome CDP session. Two independent temporary tabs are opened,
required Opportunity and Research-AMEA Quotation form fields are inspected,
then closed. No CRM REST writes, no form filling, no screenshots/upload.
GitHub Actions does not run this on a public runner.
"""
import asyncio,json
from playwright.async_api import async_playwright

HOST="https://novogene.lightning.force.com"
JS=r"""() => {
  const roots=[],seen=new Set();
  function visit(root){
    if(!root||seen.has(root))return;
    seen.add(root);roots.push(root);
    for(const e of root.querySelectorAll('*'))if(e.shadowRoot)visit(e.shadowRoot);
  }
  visit(document);
  const labels=[];
  for(const root of roots){
    for(const el of root.querySelectorAll('label,legend,.slds-form-element__label')){
      const name=(el.textContent||"").replace(/\s+/g," ").trim().replace(/^\*/,"").trim();
      if(name&&name.length<100)labels.push(name);
    }
  }
  return {labels:[...new Set(labels)],shadowRootCount:roots.length};
}"""

def check_labels(names,required):
    low=[x.casefold() for x in names]
    return {key:any(key.casefold() in label for label in low) for key in required}

async def inspect_opportunity(ctx):
    result={"kind":"Opportunity","status":"HOLD","required":{},"record_type":"CURRENT_NATIVE_UI"}
    page=await ctx.new_page()
    try:
        await page.goto(HOST+"/lightning/o/Opportunity/list",
            wait_until="domcontentloaded",timeout=30000)
        btn=page.get_by_role("button",name="New",exact=True)
        if await btn.count()!=1:
            result["reason"]="UNIQUE_NEW_OPPORTUNITY_NOT_FOUND";return result
        await btn.click(timeout=15000)
        await page.get_by_text("Opportunity Name",exact=False).first.wait_for(timeout=25000)
        fields=await page.evaluate(JS)
        names=fields["labels"]
        needed=["Opportunity Name","Account Name","Main Contact","Amount",
            "Opportunity Currency","Close Date","Service Line","Stage",
            "Forecast Category","Progress Description"]
        result["required"]=check_labels(names,needed)
        result["shadowRootCount"]=fields["shadowRootCount"]
        result["status"]="PASS" if all(result["required"].values()) else "HOLD"
        result["reason"]="NATIVE_FIELDS_PRESENT" if result["status"]=="PASS" else "MISSING_REQUIRED_OPPORTUNITY_CONTROLS"
    except Exception as err:
        result["reason"]="FORM_ERROR_"+type(err).__name__
    finally:
        await page.close()
    return result

async def inspect_quotation(ctx):
    result={"kind":"Quotation","status":"HOLD","required":{},"record_type":"Research-AMEA"}
    page=await ctx.new_page()
    try:
        await page.goto(HOST+"/lightning/o/Quotation__c/list",
            wait_until="domcontentloaded",timeout=30000)
        btn=page.get_by_role("button",name="New",exact=True)
        if await btn.count()!=1:
            result["reason"]="UNIQUE_NEW_QUOTATION_NOT_FOUND";return result
        await btn.click(timeout=15000)
        research=page.get_by_text("Research-AMEA",exact=True)
        if await research.count()!=1:
            result["reason"]="RESEARCH_AMEA_RECORD_TYPE_UNVERIFIED";return result
        await research.click(timeout=13000)
        nxt=page.get_by_role("button",name="Next",exact=True)
        if await nxt.count()!=1:
            result["reason"]="RECORD_TYPE_NEXT_NOT_UNIQUE";return result
        await nxt.click(timeout=15000)
        await page.get_by_role("heading",name="New Quotation: Research-AMEA").wait_for(timeout=75000)
        fields=await page.evaluate(JS)
        names=fields["labels"]
        needed=["Quotation Name","Opportunity","Quotation Status"]
        result["required"]=check_labels(names,needed)
        result["shadowRootCount"]=fields["shadowRootCount"]
        save=page.get_by_role("button",name="Save",exact=True)
        result["save_button_present"]=await save.count()==1
        result["status"]="PASS" if all(result["required"].values()) and result["save_button_present"] else "HOLD"
        result["reason"]="RESEARCH_AMEA_FIELDS_PRESENT" if result["status"]=="PASS" else "NATIVE_QUOTE_FIELDS_NEED_MAPPING"
    except Exception as err:
        result["reason"]="FORM_ERROR_"+type(err).__name__
    finally:
        await page.close()
    return result

async def main():
    forms=[]
    try:
        async with async_playwright() as pw:
            browser=await pw.chromium.connect_over_cdp("http://127.0.0.1:9222",timeout=16000)
            if not browser.contexts:raise RuntimeError("AUTHENTICATED_CHROME_REQUIRED")
            ctx=browser.contexts[0]
            forms=await asyncio.gather(inspect_opportunity(ctx),inspect_quotation(ctx))
            await browser.close()
    except Exception as exc:
        forms=[{"kind":"Opportunity","status":"HOLD","reason":type(exc).__name__},
               {"kind":"Quotation","status":"HOLD","reason":type(exc).__name__}]
    print(json.dumps({
        "status":"PASS_FORM_INSPECTION" if len(forms)==2 and all(x["status"]=="PASS" for x in forms) else "HOLD_FORM_INSPECTION",
        "forms":forms,
        "crmWrites":0,"salesforce_write":False,"save_clicked":False,
        "per_record_approval_required":True
    },ensure_ascii=False))

if __name__=="__main__":
    asyncio.run(main())
