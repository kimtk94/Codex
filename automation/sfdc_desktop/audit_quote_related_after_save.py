#!/usr/bin/env python3
"""Current read-only Salesforce Related-list check after a previous Save attempt.

Only reads a private local evidence file to identify the target Opportunity.
No Salesforce writes, no retries, and no customer names/IDs in console output.
A zero Related count never proves a Quote wasn't saved somewhere else.
"""
import argparse
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

NATIVE_OPPO = re.compile(r"006[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?\Z")
QUOTE_COUNT = re.compile(r"\bQuotation\s*\(\s*([0-9]+)\s*\)",re.I)
HOST = "novogene.lightning.force.com"


def classify_related_text(text):
    if not isinstance(text,str):
        return {"status":"HOLD_NO_RELATED_TEXT","related_quote_count":None,"create_allowed":False}
    counts = {int(m.group(1)) for m in QUOTE_COUNT.finditer(text)}
    if len(counts)!=1:
        return {"status":"HOLD_QUOTATION_SECTION_MISSING_OR_AMBIGUOUS",
                "related_quote_count":None,"create_allowed":False}
    count=next(iter(counts))
    if count==0:
        return {"status":"RELATED_ZERO_SAVED_QUOTE_STILL_UNRESOLVED",
                "related_quote_count":0,"create_allowed":False}
    return {"status":"RELATED_QUOTES_PRESENT_VERIFY_INDEPENDENT_IDENTITIES",
            "related_quote_count":count,"create_allowed":False}


def target_from_private_source(source):
    if not isinstance(source,dict) or not NATIVE_OPPO.fullmatch(
            str(source.get("new_opportunity_record_id") or "")):
        raise ValueError("EXACT_CREATED_OPPORTUNITY_ID_REQUIRED")
    if source.get("opportunity_save_clicked") is not True:
        raise ValueError("NO_VERIFIED_SAVE_ATTEMPT_IN_SOURCE")
    return source["new_opportunity_record_id"]


def inspect_live_related(oppo_id):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser=pw.chromium.connect_over_cdp("http://127.0.0.1:9222",timeout=15000)
        if len(browser.contexts)!=1:
            return {"status":"HOLD_UNIQUE_CHROME_CONTEXT_REQUIRED","related_quote_count":None,"create_allowed":False}
        page=browser.contexts[0].new_page()
        try:
            page.goto("https://"+HOST+"/lightning/r/Opportunity/"+oppo_id+"/view",
                      wait_until="domcontentloaded",timeout=35000)
            route=urlsplit(page.url)
            if (route.hostname!=HOST or "/lightning/r/Opportunity/"+oppo_id+"/view" not in route.path):
                return {"status":"HOLD_OPPORTUNITY_ROUTE_CHANGED","related_quote_count":None,"create_allowed":False}
            tab=page.get_by_role("tab",name="Related",exact=True)
            if tab.count()!=1:
                return {"status":"HOLD_RELATED_TAB_NOT_UNIQUE","related_quote_count":None,"create_allowed":False}
            tab.click(timeout=10000)  # read-only navigation, never Save
            result={"status":"HOLD_QUOTATION_SECTION_MISSING_OR_AMBIGUOUS",
                    "related_quote_count":None,"create_allowed":False}
            for _ in range(24):
                page.wait_for_timeout(400)
                result=classify_related_text(page.locator("body").inner_text(timeout=6000))
                if result["related_quote_count"] is not None:
                    break
            return result
        finally:
            page.close()


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--source",default=str(Path.home()/".sfdc_desktop"/
        "created_pmp_250pe_5sample_oppo_quote_PRIVATE.json"))
    p.add_argument("--output",default=str(Path.home()/".sfdc_desktop"/
        "related_quote_current_readonly_PRIVATE.json"))
    args=p.parse_args()
    source=json.loads(Path(args.source).read_text(encoding="utf-8-sig"))
    target=target_from_private_source(source)
    result=inspect_live_related(target)
    result.update({"version":"sfdc-related-quote-current-readonly-v1",
                   "source":"live_authenticated_related_list","read_only":True,
                   "save_clicked":False,"opportunity_id_private":target})
    target_path=Path(args.output)
    target_path.parent.mkdir(parents=True,exist_ok=True)
    target_path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print("RELATED_LIST_STATUS",result["status"])
    print("RELATED_QUOTE_COUNT",result["related_quote_count"])
    print("CREATE_ALLOWED",result["create_allowed"])
    print("SOURCE_AND_OUTPUT_PRIVATE",True)


if __name__=="__main__":
    main()
