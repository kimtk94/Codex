#!/usr/bin/env python3
"""Capture Salesforce Opportunity -> Related -> Quotation__c identity read-only.

Runs ONLY on the owner's authenticated Windows desktop via Chrome CDP.
Does not access Salesforce APIs, edit any field, click Save, or export browser secrets.
Output contains private internal IDs: keep on workstation, never commit to Git.
"""
import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urljoin

from playwright.sync_api import sync_playwright

from existing_opportunity_snapshot import SNAPSHOT_JS
from related_quotation_bridge import SF_RECORD, QUOTE_RECORD, QID, same_record

PARENT_ROUTE = re.compile(r"/lightning/r/Opportunity/(006[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?)/view(?:/|$)")
QUOTE_DETAIL_ROUTE = re.compile(r"/lightning/r/Quotation__c/(a0P[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?)/view(?:/|$)")
RELATED_HREF = re.compile(r"/lightning/r/(a0P[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?)/view(?:/|$)")


def field_values(page, label):
    found = []
    for frame in page.frames:
        data = frame.evaluate(SNAPSHOT_JS)
        for item in data.get("fields", []):
            if str(item.get("label") or "").strip() == label:
                value = str(item.get("value") or "").strip()
                if value:
                    found.append(value)
    return sorted(set(found))


def capture(browser):
    candidates = []
    for context in browser.contexts:
        for page in context.pages:
            match = PARENT_ROUTE.fullmatch(urlsplit(page.url).path)
            if match and not page.is_closed():
                candidates.append((page, match.group(1)))
    if len(candidates) != 1:
        raise ValueError("Exactly one existing Opportunity record tab required")
    opportunity, parent_id = candidates[0]
    if not SF_RECORD.fullmatch(parent_id):
        raise ValueError("Invalid Opportunity record ID")

    related_tabs = []
    for frame in opportunity.frames:
        locator = frame.get_by_role("tab", name="Related", exact=True)
        if locator.count() == 1:
            related_tabs.append(locator)
    if len(related_tabs) != 1:
        raise ValueError("Unique Related tab not found")
    if related_tabs[0].get_attribute("aria-selected") != "true":
        related_tabs[0].click(timeout=6000)  # Navigation only
    opportunity.wait_for_timeout(600)

    related_records = []
    for frame in opportunity.frames:
        candidates = frame.get_by_text(re.compile(r"^QID-\d{4}-\d{2}-\d{2}-\d+$"), exact=True)
        for i in range(candidates.count()):
            candidate = candidates.nth(i)
            if not candidate.is_visible():
                continue
            qid = candidate.inner_text().strip()
            if not QID.fullmatch(qid):
                continue
            link = candidate.locator("xpath=ancestor::a[1]")
            if link.count() != 1:
                continue
            href = link.get_attribute("href") or ""
            match = RELATED_HREF.fullmatch(href)
            if match:
                related_records.append((qid, match.group(1), href))
    if len(related_records) != 1:
        raise ValueError("Exactly one QID-associated Quotation record link required")
    qid, related_quote_id, href = related_records[0]

    quote_pages = []
    for context in browser.contexts:
        for page in context.pages:
            match = QUOTE_DETAIL_ROUTE.fullmatch(urlsplit(page.url).path)
            if match and same_record(match.group(1), related_quote_id):
                quote_pages.append(page)
    if len(quote_pages) > 1:
        raise ValueError("Ambiguous quote tabs")
    if not quote_pages:
        target = urljoin(opportunity.url, href)
        if urlsplit(target).hostname != urlsplit(opportunity.url).hostname:
            raise ValueError("Quotation navigation must remain on Salesforce host")
        page = opportunity.context.new_page()
        page.goto(target, wait_until="domcontentloaded", timeout=25000)
        page.wait_for_url(re.compile(r".*/lightning/r/Quotation__c/a0P[A-Za-z0-9]{15}/view.*"),
                          timeout=15000)
        quote_pages = [page]
    quote = quote_pages[0]
    quote_path = urlsplit(quote.url).path
    quote_match = QUOTE_DETAIL_ROUTE.fullmatch(quote_path)
    if not quote_match or not same_record(related_quote_id, quote_match.group(1)):
        raise ValueError("Related link and Quotation details route do not match")
    amea = field_values(quote, "Quotation ID")
    if len(amea) != 1 or not re.fullmatch(r"AMEA\d+", amea[0]):
        raise ValueError("Exactly one labeled AMEA Quotation ID required")
    return {
        "source": "Salesforce Opportunity Related + Quotation visible UI",
        "salesforce_modified": False,
        "opportunity_record_id": parent_id,
        "related_quote_record_id": related_quote_id,
        "quotation_record_id": quote_match.group(1),
        "related_qid": qid,
        "quotation_amea_number": amea[0],
        "related_quote_record_count": 1,
        "captured_utc": datetime.now(timezone.utc).isoformat(),
        "save_allowed": False,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--cdp-url", default="http://127.0.0.1:9222")
    p.add_argument("--output", default=str(Path.home() / ".sfdc_desktop" / "related_quote_evidence.json"))
    args = p.parse_args()
    if args.cdp_url != "http://127.0.0.1:9222":
        p.error("Only localhost CDP is authorized")
    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(args.cdp_url, timeout=12000)
        record = capture(browser)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    print("OPPORTUNITY RELATED QUOTATION: ONE EXACT RECORD")
    print("QUOTE DETAILS ID / RELATED LINK: MATCH")
    print("QUOTATION AMEA ID: EXACT LABELED FIELD")
    print("SALESFORCE MODIFIED: FALSE")
    print("BUSINESS OPPORTUNITY ID: NOT YET VERIFIED")
    print("PRIVATE OUTPUT:", out)


if __name__ == "__main__":
    main()
