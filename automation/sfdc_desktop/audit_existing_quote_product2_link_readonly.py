#!/usr/bin/env python3
"""Read-only native Product2 link audit for an existing saved Quotation Product.

Compare authenticated, fresh Salesforce UI Product2 and parent Quote links to
independently captured local private evidence. This validates an existing
Product2 relationship only: NOT PricebookEntry, current pricing, current
availability, or permission to create a new Quote. Zero Salesforce writes.
"""
import argparse
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright

ROOT=Path.home()/".sfdc_desktop"
HOST="novogene.lightning.force.com"
PATTERNS={
    "Quotation_Products__c":re.compile(r"^/lightning/r/Quotation_Products__c/(a0N[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?)/view$"),
    "Quotation__c":re.compile(r"^/lightning/r/Quotation__c/(a0P[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?)/view$"),
    "Product2":re.compile(r"^/lightning/r/Product2/(01t[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?)/view$"),
}


def unique_record_links(links):
    """Fail closed if the existing Quote Line evidence shows conflicting IDs."""
    if not isinstance(links,list):
        raise ValueError("INVALID_LINK_EVIDENCE")
    seen={key:set() for key in PATTERNS}
    for item in links:
        if not isinstance(item,dict):
            continue
        href=item.get("href")
        if not isinstance(href,str):
            continue
        for kind,pattern in PATTERNS.items():
            match=pattern.fullmatch(href)
            if match:
                seen[kind].add(match.group(1))
    if not all(len(ids)==1 for ids in seen.values()):
        return None
    return {kind:next(iter(ids)) for kind,ids in seen.items()}


def same_record(left,right):
    return (isinstance(left,str) and isinstance(right,str)
            and len(left) in (15,18) and len(right) in (15,18)
            and left[:15]==right[:15])


def compare_snapshot_links(saved, current):
    baseline=unique_record_links(saved)
    updated=unique_record_links(current)
    return bool(baseline and updated and all(
        same_record(baseline[key],updated[key]) for key in PATTERNS))


def collect_links(page):
    links=[]
    for frame in page.frames:
        try:
            links.extend(frame.locator("a[href^='/lightning/r/']").evaluate_all(
                """els=>els.map(e=>({href:e.getAttribute('href')}))"""))
        except Exception:
            continue
    return links


def audit_existing_line(rounds=3):
    baseline=json.loads((ROOT/"quote_source_line_inspect_20261103_PRIVATE.json").read_text(encoding="utf-8-sig"))
    links=baseline.get("links")
    source=unique_record_links(links)
    if not source or baseline.get("save_clicked") is not False:
        raise ValueError("HOLD_PRIVATE_BASELINE_INVALID")
    quote_product_id=baseline.get("quote_product_id")
    if not same_record(quote_product_id,source["Quotation_Products__c"]):
        raise ValueError("HOLD_QUOTE_LINE_ID_CONFLICT")

    results=[]
    with sync_playwright() as pw:
        browser=pw.chromium.connect_over_cdp("http://127.0.0.1:9222",timeout=16000)
        if len(browser.contexts)!=1:
            raise ValueError("HOLD_AUTHENTICATED_CONTEXT_AMBIGUOUS")
        for index in range(1,rounds+1):
            page=browser.contexts[0].new_page()
            state="HOLD"
            try:
                target="https://"+HOST+"/lightning/r/Quotation_Products__c/"+quote_product_id+"/view"
                page.goto(target,wait_until="domcontentloaded",timeout=30000)
                if urlsplit(page.url).hostname!=HOST or quote_product_id not in page.url:
                    state="HOLD_RECORD_ROUTE_WRONG"
                else:
                    current=[]
                    for retry in range(24):
                        page.wait_for_timeout(450)
                        current=collect_links(page)
                        if unique_record_links(current):
                            break
                    same=compare_snapshot_links(links,current)
                    state="EXISTING_QUOTE_LINE_NATIVE_PRODUCT_LINK_MATCH" if same else "HOLD_PRODUCT2_OR_QUOTE_LINK_AMBIGUOUS"
            except Exception as exc:
                state="HOLD_"+type(exc).__name__
            finally:
                page.close()
            results.append(state)
            print("EXISTING_PRODUCT2_READBACK",index,"/",rounds,"STATUS",state,flush=True)
    verified=all(x=="EXISTING_QUOTE_LINE_NATIVE_PRODUCT_LINK_MATCH" for x in results)
    return {"existing_quotation_product_record_confirmed":verified,
            "native_existing_product2_link_confirmed":verified,
            "existing_parent_quote_link_confirmed":verified,
            "rounds_completed":len(results),
            "round_statuses":results,
            "current_pricebook_entry_verified":False,
            "current_quote_price_verified":False,
            "new_product_creation_allowed":False,
            "salesforce_save_allowed":False,
            "salesforce_writes":0}


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--rounds",type=int,default=3)
    args=p.parse_args()
    if not 1<=args.rounds<=3:
        raise SystemExit("HOLD_ROUND_LIMIT")
    result=audit_existing_line(args.rounds)
    path=ROOT/"existing_product2_native_link_audit_PRIVATE.json"
    path.write_text(json.dumps(result,indent=2),encoding="utf-8")
    print("PRODUCT2_NATIVE_READBACK",json.dumps(result,sort_keys=True),flush=True)


if __name__=="__main__":
    main()
