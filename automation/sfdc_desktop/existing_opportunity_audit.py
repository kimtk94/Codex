#!/usr/bin/env python3
"""Audit existing Opportunity detail and Related UI without extracting customer data."""
import argparse
import json
from playwright.sync_api import sync_playwright
from runner import check_url, PROFILE

SECTIONS=["Details","Related","Quotation","Opportunity Contacts","Opportunity Team"]
def inspect(page):
    result={"mode":"existing_opportunity_read_only"}
    result["detail_tab_count"]=page.get_by_role("tab",name="Details",exact=True).count()
    result["related_tab_count"]=page.get_by_role("tab",name="Related",exact=True).count()
    result["section_presence"]={name:page.get_by_text(name,exact=True).count() for name in SECTIONS}
    result["edit_button_count"]=page.get_by_role("button",name="Edit",exact=True).count()
    result["note"]="Only semantic counts; no customer values, URLs, record IDs or HTML collected"
    return result

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--url",required=True)
    args=parser.parse_args()
    check_url(args.url)
    with sync_playwright() as pw:
        ctx=pw.chromium.launch_persistent_context(user_data_dir=str(PROFILE),channel="chrome",headless=False)
        try:
            page=ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto(args.url,wait_until="domcontentloaded")
            input("Open an EXISTING Opportunity detail page in this Chrome window, then press Enter: ")
            candidates=[]
            for p in ctx.pages:
                if p.is_closed():continue
                try:candidates.append(inspect(p))
                except Exception:continue
            if not candidates:raise RuntimeError("No accessible Opportunity page")
            result=max(candidates,key=lambda x:x["detail_tab_count"]+x["related_tab_count"])
            print(json.dumps(result,ensure_ascii=False,indent=2))
        finally:ctx.close()

if __name__=="__main__":main()
