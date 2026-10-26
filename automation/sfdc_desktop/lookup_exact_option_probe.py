#!/usr/bin/env python3
"""Select exact Salesforce Lookup suggestions in UI; never click Save.

Fails closed on ambiguous suggestions and missing verified selected-pill.
No CRM record is created or modified.
"""
import argparse,json,re,time
from pathlib import Path
from playwright.sync_api import sync_playwright, Error as PWError
from runner import check_url, PROFILE
from lookup_preflight import prepare_lookup, find_input

def norm(s): return re.sub(r"\s+"," ",str(s or "")).strip().casefold()

def candidates(page,expected):
    # Salesforce lightning-base-combobox renders role=option and occasionally
    # plain listbox rows; collect only displayed, exact-name suggestions.
    results=[]
    for selector in ('[role="listbox"] [role="option"]',
                     'lightning-base-combobox-item',
                     '[role="option"]'):
        try:
            for loc in page.locator(selector).all():
                if not loc.is_visible(): continue
                text=loc.inner_text(timeout=750).strip()
                first=next((line.strip() for line in text.splitlines() if line.strip()),"")
                if norm(first)==norm(expected):
                    if not any(loc.evaluate("(el, other) => el === other", r["element"]) for r in []):
                        results.append((loc,text))
        except PWError: continue
    # Deduplicate nested selector matches via DOM element identity, not text.
    unique=[]
    for loc,txt in results:
        try:
            handle=loc.element_handle(timeout=500)
            if not any(handle.evaluate("(a,b) => a===b",old) for old,_ in unique):
                unique.append((handle,txt))
        except PWError: pass
    return unique

def select(context,label,name):
    inp,status=find_input(context,label)
    if inp is None: return {"status":status}
    try:
        inp.fill(name,timeout=2500)
        time.sleep(0.7)
        page=next((p for p in context.pages if not p.is_closed() and p.locator('[role="listbox"]').count()),None)
        if page is None:return {"status":"NO_SUGGESTION_LIST"}
        options=candidates(page,name)
        if len(options)!=1:return {"status":"NO_EXACT_UNIQUE_SUGGESTION","count":len(options)}
        option,_=options[0]
        option.click(timeout=2500)
        time.sleep(0.25)
        # A selected chip/removable token, not just typed search text, is evidence.
        # Do not assert verified if no explicit selected token can be identified.
        return {"status":"OPTION_CLICKED_CHIP_NOT_VERIFIED"}
    except PWError:return {"status":"LOOKUP_UI_CHANGED"}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--url",required=True)
    p.add_argument("--draft",required=True)
    p.add_argument("--output",default="")
    a=p.parse_args()
    check_url(a.url)
    values=prepare_lookup(json.loads(Path(a.draft).read_text(encoding="utf-8-sig")))
    with sync_playwright() as pw:
        ctx=pw.chromium.launch_persistent_context(user_data_dir=str(PROFILE),headless=False,channel="chrome")
        try:
            page=ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto(a.url,wait_until="domcontentloaded")
            input("Complete MFA, open New Opportunity, press Enter: ")
            # Select Account first; afterwards Contact suggestions may be scoped by Account.
            state={}
            for label in ("Account Name","Main Contact"):
                state[label]=select(ctx,label,values[label])
                if state[label]["status"]!="OPTION_CLICKED_CHIP_NOT_VERIFIED":
                    break
            out=Path(a.output) if a.output else Path(a.draft).with_name("lookup_selection_report.json")
            report={"lookup":state,"lookup_verified":False,"save_clicked":False,
                    "note":"Exact option click is not confirmation of CRM relationship. Inspect selected pills."}
            out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
            print(json.dumps(report,ensure_ascii=False,indent=2))
            print("REPORT:",out)
            input("Inspect selected Lookup chips. Press Enter to close: ")
        finally:ctx.close()
if __name__=="__main__":main()
