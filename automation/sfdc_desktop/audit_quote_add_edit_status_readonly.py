#!/usr/bin/env python3
"""Sample pre-existing Quote status groups for Add/Edit availability, read only.

Does NOT click Add/Edit, Save, Create, Pack or price buttons. This distinguishes
Quote-specific disabled states from global restrictions. Identifiers remain in
the private workstation report; console emits status counts only.
"""
import json
import re
from collections import Counter,defaultdict
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT=Path.home()/".sfdc_desktop"
HOST="novogene.lightning.force.com"
QUOTE=re.compile(r"a0P[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?")
STATUSES=("Draft","Need to submit","Ready to send")


def choose_status_samples(items, per_status=2):
    if not isinstance(items,list) or per_status not in (1,2,3):
        raise ValueError("INVALID_QUOTE_MANIFEST")
    output=[]
    chosen={state:0 for state in STATUSES}
    seen=set()
    for item in items:
        if not isinstance(item,dict):
            continue
        status=item.get("quote_status")
        ident=item.get("quote_id")
        if (status not in chosen or chosen[status]>=per_status or
            not isinstance(ident,str) or not QUOTE.fullmatch(ident) or
            ident in seen or item.get("save_clicked") is not False):
            continue
        chosen[status]+=1
        seen.add(ident)
        output.append({"quote_id":ident,"status":status})
    return output


def observe(page,record):
    url="https://"+HOST+"/lightning/r/Quotation__c/"+record["quote_id"]+"/view"
    page.goto(url,wait_until="domcontentloaded",timeout=34000)
    if record["quote_id"] not in page.url:
        return "HOLD_ROUTE_DIFFERENT"
    tab=page.get_by_role("tab",name="Quotation Detail",exact=True)
    tab.wait_for(state="visible",timeout=18000)
    if tab.count()!=1:
        return "HOLD_TAB_AMBIGUOUS"
    tab.click(timeout=6500)
    btn=page.get_by_role("button",name="Add/Edit",exact=True)
    btn.wait_for(state="visible",timeout=12000)
    if btn.count()!=1:
        return "HOLD_ADD_EDIT_AMBIGUOUS"
    return "BUTTON_ENABLED" if btn.is_enabled() else "BUTTON_DISABLED"


def main():
    manifest=json.loads((ROOT/"oppo_quote_single_product_learning_manifest_PRIVATE.json").read_text(encoding="utf-8-sig"))
    cases=choose_status_samples(manifest,per_status=2)
    if len(cases)<3:
        raise SystemExit("HOLD_NOT_ENOUGH_EXISTING_QUOTES")
    rows=[]
    with sync_playwright() as pw:
        browser=pw.chromium.connect_over_cdp("http://127.0.0.1:9222",timeout=16000)
        if len(browser.contexts)!=1:raise SystemExit("HOLD_BROWSER_CONTEXT_AMBIGUOUS")
        for case in cases:
            page=browser.contexts[0].new_page()
            try:
                state=observe(page,case)
            except Exception as exc:
                state="HOLD_"+type(exc).__name__
            finally:page.close()
            rows.append({**case,"readback":state,"save_clicked":False})
            print("QUOTE_ACTION_AVAILABILITY",case["status"],state,flush=True)
    out=ROOT/"quote_status_add_edit_availability_PRIVATE.json"
    out.write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding="utf-8")
    counts=Counter((r["status"],r["readback"]) for r in rows)
    print("QUOTE_ACTION_AVAILABILITY_SUMMARY",
          json.dumps({"samples":len(rows),"counts":[
              {"quote_status":s,"readback":state,"count":n}
              for (s,state),n in sorted(counts.items())],
              "save_clicked":False,"crm_writes":0},sort_keys=True))


if __name__=="__main__":
    main()
