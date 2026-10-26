#!/usr/bin/env python3
"""Conservative Salesforce Lookup preflight: drafts only, never Save.

Uses Playwright's open Shadow DOM traversal. Requires human MFA and opening New Opportunity.
Exact suggestion equality is required; ambiguity means no selection.
"""
import argparse
import json
from pathlib import Path
from playwright.sync_api import sync_playwright
from runner import check_url, PROFILE

def prepare_lookup(draft):
    required=("Account Name","Main Contact")
    if not all(isinstance(draft.get(k),str) and draft[k].strip() for k in required):
        raise ValueError("Draft needs Account Name and Main Contact")
    if draft.get("save_allowed") is not False or draft.get("lookup_verified") is not False:
        raise ValueError("Expected unsaved, unverified draft safety flags")
    return {k:draft[k].strip() for k in required}

def find_input(page,label):
    # Lightning open shadow roots are traversed automatically by Playwright CSS locators.
    host_tags={"Account Name":"lightning-grouped-combobox","Main Contact":"lightning-grouped-combobox"}
    host=host_tags[label]
    candidates=page.locator(host).filter(has=page.locator("label").filter(has_text=label))
    if candidates.count()!=1:
        return None, "HOST_NONUNIQUE"
    loc=candidates.locator("input")
    if loc.count()!=1 or not loc.is_visible() or not loc.is_enabled():
        return None,"INPUT_NONUNIQUE"
    return loc,"READY"

def run(page, draft):
    values=prepare_lookup(draft)
    result={}
    for label,value in values.items():
        loc,status=find_input(page,label)
        if loc is None:
            result[label]=status
            continue
        loc.fill(value)
        # Typing is not selecting an SFDC relationship. Do not click an unverified option.
        result[label]="TEXT_ENTERED_RELATION_UNVERIFIED"
    return {"lookup":result,"relationship_verified":False,"save_clicked":False}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--url",required=True)
    p.add_argument("--draft",required=True)
    p.add_argument("--output",default="")
    a=p.parse_args()
    check_url(a.url)
    draft=json.loads(Path(a.draft).read_text(encoding="utf-8-sig"))
    prepare_lookup(draft)
    with sync_playwright() as pw:
        ctx=pw.chromium.launch_persistent_context(user_data_dir=str(PROFILE),headless=False,channel="chrome")
        try:
            page=ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto(a.url,wait_until="domcontentloaded")
            input("Complete MFA, open New Opportunity in this Chrome, press Enter: ")
            report=run(page,draft)
            report["note"]="Text-only lookup probe. Salesforce relationship not established; no Save."
            out=Path(a.output) if a.output else Path(a.draft).with_name("lookup_preflight.json")
            out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
            print(json.dumps(report,ensure_ascii=False,indent=2))
            print("Report:",out)
            input("Inspect unsaved form. Press Enter to close: ")
        finally:
            ctx.close()
if __name__=="__main__":
    main()
