#!/usr/bin/env python3
"""One-login, multi-check Salesforce Lookup audit. Never clicks Save."""
import argparse,json,time
from pathlib import Path
from playwright.sync_api import sync_playwright,Error as PWError
from runner import check_url,PROFILE
from lookup_preflight import prepare_lookup,find_input
from lookup_exact_option_probe import select,selected_state

def audit(ctx,label,name):
    d={"input":"NOT_FOUND","search":"NOT_RUN","selection":"NOT_RUN"}
    loc,status=find_input(ctx,label)
    if loc is None:
        d["input"]=status
    else:
        d["input"]="FOUND"
    d["pre_existing_selected"]=selected_state(ctx,label,name)
    # Existing select() performs search affordance, exact candidate click and pill check.
    d["selection"]=select(ctx,label,name)
    d["post_selection"]=selected_state(ctx,label,name)
    return d

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--url",required=True)
    p.add_argument("--draft",required=True)
    p.add_argument("--cdp-url",default="http://127.0.0.1:9222")
    p.add_argument("--output",default="")
    a=p.parse_args()
    check_url(a.url)
    values=prepare_lookup(json.loads(Path(a.draft).read_text(encoding="utf-8-sig")))
    with sync_playwright() as pw:
        browser=pw.chromium.connect_over_cdp(a.cdp_url) if a.cdp_url else None
        ctx=browser.contexts[0] if browser and browser.contexts else pw.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE),headless=False,channel="chrome")
        attached=bool(browser and browser.contexts)
        try:
            if not attached:
                page=ctx.pages[0] if ctx.pages else ctx.new_page()
                page.goto(a.url,wait_until="domcontentloaded")
            input("Use authenticated Chrome; open New Opportunity, then Enter ONCE: ")
            report={"version":"lookup-batch-audit-v1","fields":{},"save_clicked":False}
            for label in ("Account Name","Main Contact"):
                try:report["fields"][label]=audit(ctx,label,values[label])
                except Exception as e:report["fields"][label]={"error_type":type(e).__name__}
            report["both_verified"]=all(report["fields"].get(label,{}).get("post_selection",{}).get("verified") is True
                for label in ("Account Name","Main Contact"))
            path=Path(a.output) if a.output else Path(a.draft).with_name("lookup_batch_audit.json")
            path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
            print(json.dumps(report,ensure_ascii=False,indent=2))
            print("REPORT:",path)
            input("Inspect selected values in browser; Enter to finish: ")
        finally:
            if not attached:ctx.close()

if __name__=="__main__":main()
