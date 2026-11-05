#!/usr/bin/env python3
"""Capture a currently QID-filtered Salesforce report using authenticated localhost CDP.

Use report 'Automation | Quotation' (or another approved Quotation report) after
selecting an exact SFDC Quotation ID filter and using Run, *not* Save & Run.
The report can have multiple product rows for one quote. Salesforce data stays
on the owner's workstation. Never upload raw report/evidence to GitHub or logs.
"""
import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright

from live_quotation_report_bridge import verify
from related_quotation_bridge import QID, QUOTE_RECORD, same_record

REPORT_ROUTE = re.compile(r"/lightning/r/Report/(00O[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?)/view(?:/|$)")
QUOTE_HREF = re.compile(r"/lightning/r/(?:Quotation__c/)?(a0P[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?)/view(?:[/?]|$)")
BUSINESS_TEXT = re.compile(r"Opp-\d{4}-\d{2}-\d{2}-\d+")
TOTAL = re.compile(r"Total Records\s+([\d,]+)", re.IGNORECASE)


def capture(browser, related, requested_report_id):
    qid = str(related.get("related_qid") or "")
    target_quote = str(related.get("quotation_record_id") or "")
    if not QID.fullmatch(qid) or not QUOTE_RECORD.fullmatch(target_quote):
        raise ValueError("Private Quotation related evidence is invalid")
    candidates = []
    for context in browser.contexts:
        for page in context.pages:
            path = urlsplit(page.url).path
            match = REPORT_ROUTE.fullmatch(path)
            if (match and match.group(1) == requested_report_id
                    and urlsplit(page.url).hostname == "novogene.lightning.force.com"):
                candidates.append((page, match.group(1)))
    if len(candidates) != 1:
        raise ValueError("Open exactly one matching Salesforce Report Viewer tab")
    page, report_id = candidates[0]
    frames = [f for f in page.frames if "/reports/lightningReportApp.app" in f.url]
    if len(frames) != 1:
        raise ValueError("Exactly one Salesforce Report Viewer frame required")
    frame = frames[0]

    def active_filters():
        return [s.strip() for s in frame.get_by_role("button").all_text_contents()
                if "Edit Filter" in s]

    labels = active_filters()
    if not any("SFDC Quotation ID" in s for s in labels):
        filter_toggle = frame.get_by_role("button", name="Filters", exact=True)
        if filter_toggle.count() == 1:
            filter_toggle.click()
            page.wait_for_timeout(300)
            labels = active_filters()
    normalized = [" ".join(v.split()) for v in labels]
    expected = "Edit FilterSFDC Quotation IDequals " + qid
    if expected not in normalized:
        raise ValueError("An exact equality report filter for this QID is required")

    totals = []
    for text in frame.get_by_role("alert").all_text_contents():
        m = TOTAL.search(text)
        if m:
            totals.append(int(m.group(1).replace(",", "")))
    if len(totals) != 1:
        raise ValueError("Exactly one authoritative report Total Records indicator required")
    total = totals[0]
    if total <= 0 or total > 2000:
        raise ValueError("Report 2,000-row display limit or empty report; cannot verify all rows")

    found_rows = []
    for row in frame.get_by_role("row").all():
        text = row.inner_text(timeout=3000)
        ids = re.findall(r"QID-\d{4}-\d{2}-\d{2}-\d+", text)
        if qid not in ids:
            continue
        if set(ids) != {qid}:
            raise ValueError("Other QIDs present in matched report row")
        business_ids = sorted(set(BUSINESS_TEXT.findall(text)))
        if len(business_ids) != 1:
            raise ValueError("Exactly one business Opportunity ID per row required")
        hrefs = row.locator("a").evaluate_all(
            "(elements)=>elements.map(a=>a.getAttribute('href')||'')")
        links = []
        for href in hrefs:
            match = QUOTE_HREF.search(href)
            if match:
                links.append(match.group(1))
        if len(links) != 1 or not same_record(links[0], target_quote):
            raise ValueError("Exact Quotation__c link missing or ambiguous")
        found_rows.append({
            "qid": qid,
            "quotation_record_id": links[0],
            "business_opportunity_id": business_ids[0],
        })
    if len(found_rows) != total:
        raise ValueError("Displayed matching row count differs from full report Total Records")
    return {
        "source": "Salesforce Report Viewer UI",
        "salesforce_modified": False,
        "report_id": report_id,
        "filter_operator": "equals",
        "exact_qid_filter": qid,
        "total_records": total,
        "rows": found_rows,
        "captured_utc": datetime.now(timezone.utc).isoformat(),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--related-evidence", required=True)
    parser.add_argument("--report-id", required=True)
    parser.add_argument("--cdp-url", default="http://127.0.0.1:9222")
    parser.add_argument("--output", default="")
    parser.add_argument("--bridge-output", default="")
    args = parser.parse_args()
    if args.cdp_url != "http://127.0.0.1:9222":
        parser.error("Only local authorized CDP on port 9222 is permitted")
    related = json.loads(Path(args.related_evidence).read_text(encoding="utf-8-sig"))
    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(args.cdp_url, timeout=12000)
        snapshot = capture(browser, related, args.report_id)
    result = verify(related, snapshot)
    path = Path(args.output) if args.output else Path.home() / ".sfdc_desktop" / "live_quote_report_evidence.json"
    other = Path(args.bridge_output) if args.bridge_output else path.with_name("verified_live_quotation_report_bridge.json")
    for target, data in ((path, snapshot), (other, result)):
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print("LIVE REPORT BRIDGE:", result["status"])
    print("VERIFIED PRODUCT ROWS:", result["verified_product_rows"])
    print("SALESFORCE SAVE ALLOWED:", result["save_allowed"])
    print("PRIVATE ARTIFACT:", other)


if __name__ == "__main__":
    main()
