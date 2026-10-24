#!/usr/bin/env python3
"""Local-only existing Opportunity record identity preflight.

No Salesforce API, mutation, HTML, screenshots or field values. Record ID is
validated in-memory and never logged; only boolean presence/type is reported.
"""
import argparse
import json
import re
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright
from runner import check_url, PROFILE

ID = re.compile(r"^[A-Za-z0-9]{15}(?:[A-Za-z0-9]{3})?$")

def summarize_url(url):
    check_url(url)
    path = urlparse(url).path
    match = re.search(r"/lightning/r/Opportunity/([A-Za-z0-9]{15}(?:[A-Za-z0-9]{3})?)/view(?:/|$)", path)
    return {"is_opportunity_record_page":bool(match),
            "record_id_in_url":bool(match and ID.fullmatch(match.group(1))),
            "record_id_length":len(match.group(1)) if match else 0}

def inspect_context(ctx):
    rows=[]
    for page in ctx.pages:
        if page.is_closed():continue
        try:
            check_url(page.url)
            rows.append(summarize_url(page.url))
        except (ValueError, Exception):
            continue
    return {"audit_version":"opportunity-identity-v1","tabs_checked":len(rows),
            "opportunity_record_tabs":sum(r["is_opportunity_record_page"] for r in rows),
            "records_with_url_id":sum(r["record_id_in_url"] for r in rows),
            "details":rows,"note":"No identifiers or URLs printed; a record ID in URL is not Create/Edit authorization."}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--url",required=True)
    a=p.parse_args()
    check_url(a.url)
    with sync_playwright() as pw:
        ctx=pw.chromium.launch_persistent_context(user_data_dir=str(PROFILE),channel="chrome",headless=False)
        try:
            page=ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto(a.url,wait_until="domcontentloaded")
            input("Open an existing Opportunity's Details in THIS Chrome; then press Enter: ")
            print(json.dumps(inspect_context(ctx),ensure_ascii=False,indent=2))
        finally:ctx.close()

if __name__=="__main__":main()
