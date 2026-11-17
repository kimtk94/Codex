"""Read-only SFDC UI checks in up to 3 independent tabs / ONE CDP connection.
No shared Playwright page, clicking Save, editing inputs, or CRM mutations.
"""
import asyncio,json,re,sys,time
from playwright.async_api import async_playwright

BASE="https://sfdc.novogene.com"
QUOTE=re.compile(r"^a0P[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?$")
MAX_WORKERS=3

def validate(input_data):
    if not isinstance(input_data,dict) or input_data.get("mode")!="QUOTE_UI_BATCH":
        raise ValueError("BATCH_MODE_INVALID")
    ids=input_data.get("recordIds")
    if not isinstance(ids,list) or not 1<=len(ids)<=3 or any(
        not isinstance(x,str) or not QUOTE.fullmatch(x) for x in ids
    ) or len(set(ids))!=len(ids):
        raise ValueError("BATCH_IDS_INVALID")
    return ids

async def inspect(ctx,record_id,index):
    page=await ctx.new_page()
    began=time.monotonic()
    try:
        await page.goto(BASE+"/lightning/r/Quotation__c/"+record_id+"/view",
                        wait_until="domcontentloaded",timeout=26000)
        tab=page.get_by_role("tab",name="Details",exact=True)
        await tab.wait_for(state="visible",timeout=15000)
        await tab.click(timeout=8000)
        text=await page.locator("body").inner_text(timeout=9000)
        has_details=("Quotation Name" in text or "Quotation ID" in text)
        source_links=await page.locator('a[href*="/lightning/r/006"]').count()
        return {"recordId":record_id,"index":index,
                "status":"PASS" if has_details else "HOLD",
                "linkedOpportunityVisible":source_links>0,
                "code":"UI_READ_VERIFIED" if has_details else "QUOTE_DETAILS_UNVERIFIED",
                "elapsedMs":round(1000*(time.monotonic()-began))}
    except Exception as exc:
        return {"recordId":record_id,"index":index,"status":"HOLD",
                "linkedOpportunityVisible":False,
                "code":"UI_"+type(exc).__name__[:45],
                "elapsedMs":round(1000*(time.monotonic()-began))}
    finally:
        await page.close()

async def run(inp):
    ids=validate(inp)
    start=time.monotonic()
    async with async_playwright() as playwright:
        browser=await playwright.chromium.connect_over_cdp(
            "http://127.0.0.1:9222",timeout=26000)
        if not browser.contexts:
            raise ValueError("SFDC_BROWSER_CONTEXT_MISSING")
        ctx=browser.contexts[0]
        limit=asyncio.Semaphore(MAX_WORKERS)
        async def one(i,record):
            async with limit:
                return await inspect(ctx,record,i)
        results=await asyncio.gather(*(one(i+1,r) for i,r in enumerate(ids)))
    return {"status":"PASS" if all(x["status"]=="PASS" for x in results) else "HOLD",
            "results":results,"maxParallelTabs":MAX_WORKERS,
            "cdpConnections":1,"durationMs":round((time.monotonic()-start)*1000),
            "salesforceWrite":False,"savePermitted":False}

def main():
    try:
        inp=json.loads(sys.stdin.read(1500))
        output=asyncio.run(run(inp))
    except Exception as exc:
        code=str(exc) if isinstance(exc,ValueError) and re.fullmatch(r"[A-Z0-9_]{3,90}",str(exc)) else "UI_BATCH_UNAVAILABLE"
        output={"status":"HOLD","code":code,"results":[],
                "salesforceWrite":False,"savePermitted":False}
    sys.stdout.write(json.dumps(output,ensure_ascii=False)+"\n")

if __name__=="__main__":
    main()
