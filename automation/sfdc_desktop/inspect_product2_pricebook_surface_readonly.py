#!/usr/bin/env python3
"""Read-only Product2 pricebook surface inventory for an existing Quote line.

All native record IDs and customer details remain private. Console exposes
only field availability and PricebookEntry link counts, never price values.
"""
import json
import re
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright

from audit_existing_quote_product2_link_readonly import HOST,ROOT,unique_record_links

PRICEBOOK_LINK=re.compile(r"^/lightning/r/(?:PricebookEntry/)?(01u[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?)/view$")
TITLES=(
 "Price Book Entries","Pricebook Entries","Price Books","Pricebooks",
 "Pricebook","Standard Price","List Price","Unit Price","Product Code",
 "Product Family","Product Name","Active","Product Description"
)


def inspect_tab(page, name):
    for frame in page.frames:
        try:
            tabs=frame.get_by_role("tab",name=name,exact=True)
            if tabs.count()==1 and tabs.is_visible():
                tabs.click(timeout=6500)
                break
        except Exception:
            continue
    page.wait_for_timeout(1800)
    texts=[]
    native=[]
    for frame in page.frames:
        try:
            texts.append(frame.locator("body").inner_text(timeout=4500))
            native.extend(frame.locator("a[href^='/lightning/r/']").evaluate_all(
                "es=>es.map(e=>e.getAttribute('href')).filter(Boolean)"))
        except Exception:
            continue
    content="\n".join(texts)
    pricebook_ids=set()
    for href in native:
        match=PRICEBOOK_LINK.fullmatch(href)
        if match:
            pricebook_ids.add(match.group(1)[:15])
    return {"tab":name,"body_read":bool(content),
            "labels_present":{label:label.casefold() in content.casefold() for label in TITLES},
            "native_pricebook_entry_link_count":len(pricebook_ids)}


def run():
    baseline=json.loads((ROOT/"quote_source_line_inspect_20261103_PRIVATE.json").read_text(encoding="utf-8-sig"))
    native=unique_record_links(baseline.get("links"))
    if native is None:
        raise SystemExit("HOLD_PRODUCT2_BASELINE_AMBIGUOUS")
    product_id=native["Product2"]
    with sync_playwright() as pw:
        browser=pw.chromium.connect_over_cdp("http://127.0.0.1:9222",timeout=16000)
        if len(browser.contexts)!=1: raise SystemExit("HOLD_CHROME_CONTEXT_COUNT")
        page=browser.contexts[0].new_page()
        try:
            target="https://"+HOST+"/lightning/r/Product2/"+product_id+"/view"
            page.goto(target,wait_until="domcontentloaded",timeout=30000)
            if urlsplit(page.url).hostname!=HOST or product_id not in page.url:
                raise SystemExit("HOLD_PRODUCT2_ROUTE_MISMATCH")
            page.wait_for_timeout(1800)
            tab_names=[]
            for f in page.frames:
                try:tab_names+=f.get_by_role("tab").all_text_contents()
                except Exception:continue
            observations=[]
            for name in ("Related","Details"):
                observations.append(inspect_tab(page,name))
            result={"read_only":True,"salesforce_writes":0,
                    "product2_native_route_confirmed":True,
                    "tab_names":[x.strip() for x in tab_names if len(x)<60][:12],
                    "observations":observations,
                    "pricebook_entry_independently_verified":False,
                    "current_price_verified":False,"save_allowed":False}
            private_file=ROOT/"existing_product2_pricebook_surface_PRIVATE.json"
            private_file.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
            print("PRODUCT2_PRICEBOOK_SURFACE",json.dumps(result,sort_keys=True))
        finally:
            page.close()

if __name__=="__main__":
    run()
