#!/usr/bin/env python3
"""Classify Contact-display HOLD causes without weakening the identity gate.

Read-only Salesforce UI. User names/IDs remain on workstation and are never
printed or committed. Only the first N previously unapproved candidates are
inspected, and existing PASS records are skipped.
"""
import argparse
import json
import re
import unicodedata
from pathlib import Path
from playwright.sync_api import sync_playwright

import live_contact_alias_batch_private as cohort
from probe_scoped_contact_navigation import HOST, detail_tab
from build_private_contact_aliases import korean_name_from_contact_label

ROOT=Path.home()/".sfdc_desktop"


def name_presentation(display, visible_texts, headings):
    """Categorize evidence without inferring identity from a romanized name."""
    if not isinstance(display,str):
        return "HOLD_INVALID_NAME"
    clean=lambda t:" ".join(unicodedata.normalize("NFKC",str(t)).split()).casefold()
    exact=clean(display)
    texts={clean(x) for x in visible_texts}
    head={clean(x) for x in headings}
    if exact in head:
        return "FULL_NAME_HEADING"
    if exact in texts:
        return "FULL_NAME_VISIBLE"
    korean=korean_name_from_contact_label(display)
    if korean and clean(korean) in texts:
        return "ONLY_KOREAN_TOKEN_VISIBLE"
    if korean and any(clean(korean) in x for x in texts):
        return "KOREAN_TOKEN_IN_LONGER_TEXT"
    return "NO_EXPECTED_DISPLAY_VISIBLE"


def diagnostic(page,row):
    url="https://"+HOST+"/lightning/r/Contact/"+row["contact_id"]+"/view"
    page.goto(url,wait_until="domcontentloaded",timeout=35000)
    if not page.url.startswith(url):
        return "HOLD_WRONG_CONTACT_ROUTE"
    detail_tab(page)
    for round_i in range(3):
        if round_i:
            page.wait_for_timeout(1100)
        visible=page.locator("body").evaluate("""el => {
          const out=[],seen=new Set();
          function walk(root) {
            if(!root || seen.has(root))return;
            seen.add(root);
            for(const x of root.querySelectorAll('*')) {
              if(x.shadowRoot)walk(x.shadowRoot);
              if(!x.children.length && x.textContent && x.getClientRects().length) {
                const str=x.textContent.trim();
                if(str && str.length<=160)out.push(str);
              }
            }
          }
          walk(el);
          return out.slice(0,12000);
        }""")
        headings=page.get_by_role("heading").all_text_contents()
        status=name_presentation(row["display_name"],visible,headings)
        if status in ("FULL_NAME_HEADING","FULL_NAME_VISIBLE"):
            return status
    return status


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--cohort-first",type=int,default=20)
    ap.add_argument("--limit",type=int,default=5)
    args=ap.parse_args()
    if not (1<=args.limit<=10 and 1<=args.cohort_first<=48):
        ap.error("restricted diagnostic range")
    existing=ROOT/"private_verified_contact_details_evidence.json"
    verified={r.get("contact_id") for r in json.loads(existing.read_text(encoding="utf-8-sig"))} if existing.exists() else set()
    pending=[r for r in cohort.candidates()[:args.cohort_first] if r["contact_id"] not in verified][:args.limit]
    summary={}
    records=[]
    with sync_playwright() as pw:
        browser=pw.chromium.connect_over_cdp("http://127.0.0.1:9222",timeout=16000)
        if len(browser.contexts)!=1:
            raise SystemExit("HOLD_BROWSER_CONTEXT")
        page=browser.contexts[0].new_page()
        try:
            for row in pending:
                try:
                    status=diagnostic(page,row)
                except Exception as exc:
                    status="HOLD_"+type(exc).__name__
                summary[status]=summary.get(status,0)+1
                records.append({"contact_id":row["contact_id"],"opportunity_id":row["opportunity_id"],
                                "reason":status,"read_only":True})
        finally:
            page.close()
    dest=ROOT/"contact_display_hold_diagnostics_PRIVATE.json"
    dest.write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"hold_reexamined":len(pending),"reasons":summary,
                      "save_clicked":False},sort_keys=True))

if __name__=="__main__":
    main()
