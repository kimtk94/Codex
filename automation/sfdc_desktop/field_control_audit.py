#!/usr/bin/env python3
"""Salesforce AMEA form: read-only control mapping diagnostics.

Only captures expected field names, semantic roles and locator counts.
Never reads input values, customer names, HTML, or credentials.
"""
import argparse
import json
from playwright.sync_api import sync_playwright
from runner import check_url, PROFILE
from field_label_audit import EXPECTED

def inspect(page):
    results={}
    for label in EXPECTED:
        by_label=page.get_by_label(label,exact=True)
        by_role=page.get_by_role("textbox",name=label,exact=True)
        by_combo=page.get_by_role("combobox",name=label,exact=True)
        results[label]={"by_label":by_label.count(),
                        "textbox":by_role.count(),
                        "combobox":by_combo.count()}
    return {"version":"field-control-v1","mapping":results,
            "note":"Counts only, no field values. Zero/multiple matches require local manual mapping."}

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
            input("Open New Opportunity in automated Chrome; press Enter: ")
            # Try each page, select the one with most semantic matches.
            findings=[]
            for candidate in ctx.pages:
                if candidate.is_closed():continue
                try:findings.append(inspect(candidate))
                except Exception:continue
            if not findings:
                raise RuntimeError("No accessible tab; confirm authenticated New Opportunity")
            best=max(findings,key=lambda r:sum(x["by_label"] for x in r["mapping"].values()))
            print(json.dumps(best,ensure_ascii=False,indent=2))
        finally:ctx.close()

if __name__=="__main__":
    main()
