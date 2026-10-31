#!/usr/bin/env python3
"""Read-only Salesforce Opportunity routing audit v3: Playwright locators, no JS eval.

Reports counts only. Does not read record values, IDs, page HTML or screenshots.
"""
import argparse
import json
import re
import time
from collections import Counter
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright, Error as PlaywrightError
from runner import check_url, PROFILE

VERSION="opportunity-identity-v3"
ID_RE=re.compile(r"^[A-Za-z0-9]{15}(?:[A-Za-z0-9]{3})?$")
ROUTE_RE=re.compile(r"/lightning/r/Opportunity/([^/?#]+)/view(?:/|$)")

def classify_url(url):
    check_url(url)
    path=urlparse(url).path
    match=ROUTE_RE.search(path)
    return {"route_opportunity":bool(match),
            "route_record_id":bool(match and ID_RE.fullmatch(match.group(1))),
            "workspace_or_list_route":path.startswith("/lightning/") and not match}

def error_category(exc):
    message=str(exc).lower()
    if "detached" in message:return "FRAME_DETACHED"
    if "execution context was destroyed" in message or "navigation" in message:return "NAVIGATION"
    if "timeout" in message:return "TIMEOUT"
    return "OTHER"

def inspect_context(ctx):
    counts=Counter()
    errors=Counter()
    for page in ctx.pages:
        if page.is_closed():continue
        try:
            route=classify_url(page.url)
        except ValueError:
            continue
        counts["pages"]+=1
        for key,val in route.items():
            if val:counts[key]+=1
        for frame in page.frames:
            counts["frames_total"]+=1
            for attempt in range(4):
                try:
                    # Playwright locators pierce open Shadow DOM by default.
                    links=frame.locator('a[href*="/lightning/r/Opportunity/"]')
                    tabs=frame.locator('[role="tab"][aria-selected="true"]')
                    counts["opportunity_link_candidates"]+=links.count()
                    counts["active_tab_indicators"]+=tabs.count()
                    counts["frames_inspected"]+=1
                    break
                except PlaywrightError as exc:
                    kind=error_category(exc)
                    if kind in ("FRAME_DETACHED","NAVIGATION") and attempt<3:
                        time.sleep(0.4)
                        continue
                    errors[kind]+=1
                    break
    return {"version":VERSION,"pages":counts["pages"],
      "frames_total":counts["frames_total"],"frames_inspected":counts["frames_inspected"],
      "frame_failures":dict(errors),"route_record_id":bool(counts["route_record_id"]),
      "route_opportunity":bool(counts["route_opportunity"]),
      "workspace_or_list_route":bool(counts["workspace_or_list_route"]),
      "opportunity_link_candidates":counts["opportunity_link_candidates"],
      "active_tab_indicators":counts["active_tab_indicators"],
      "note":"Candidate links can belong to other records; record identity unverified."}

def main():
    p=argparse.ArgumentParser();p.add_argument("--url",required=True);a=p.parse_args()
    check_url(a.url)
    print("SFDC_ID_AUDIT_VERSION="+VERSION,flush=True)
    with sync_playwright() as pw:
        ctx=pw.chromium.launch_persistent_context(user_data_dir=str(PROFILE),channel="chrome",headless=False)
        try:
            page=ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto(a.url,wait_until="domcontentloaded")
            input("Open existing Opportunity Details in THIS Chrome; press Enter: ")
            print(json.dumps(inspect_context(ctx),ensure_ascii=False,indent=2))
        finally:ctx.close()

if __name__=="__main__":main()
