#!/usr/bin/env python3
"""Build a PRIVATE review template from an authenticated existing Opportunity.

Captures the current Name, Amount and Close Date for the owner's reference.
Does not authorize any changes, does not choose lookups, and never clicks Save.
The created JSON stays under ~/.sfdc_desktop/ and must not be committed.
"""
import argparse
import json
import secrets
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright

from audit_existing_opportunity_no_save import SFDC_ROUTE, validate_preflight, editor_close
from audit_existing_numeric_date_nochange import locate_field, check_lookup_ids
from capture_existing_lookup_links import DOM_SCRIPT

FIELDS = {
    "Opportunity Name": "Edit Opportunity Name",
    "Amount": "Edit Amount",
    "Close Date": "Edit Close Date",
}


def blank_request(target, business_id, lookup_ids, originals, request_uid):
    if not target or not business_id or not isinstance(originals, dict):
        raise ValueError("Exact verified target and current values required")
    if set(originals) != set(FIELDS) or not all(isinstance(x, str) and x.strip() for x in originals.values()):
        raise ValueError("All three current editable values must be present")
    return {
        "request_uid": request_uid,
        "mode": "EXISTING_OPPORTUNITY_FILL_ONLY",
        "reviewed_current_deal_values": False,
        "target_opportunity_record_id": target,
        "business_opportunity_id": business_id,
        "expected_account_record_id": lookup_ids["account_record_id"],
        "expected_contact_record_id": lookup_ids["contact_record_id"],
        "observed_current_values_reference_only": originals,
        "expected_before_values": {},
        "changes": {},
        "save_allowed": False,
        "_instructions": (
            "Private reference only. Copy ONLY fields to change from observed_current_values_reference_only "
            "into expected_before_values, put their reviewed new values into changes, and set "
            "reviewed_current_deal_values=true only after explicit human review. "
            "Do not change Account or Contact links. No Salesforce Save is permitted."
        )
    }


def current_value(page, field):
    if field not in FIELDS:
        raise ValueError("Unsupported field")
    result = {"opened": False, "cancel_clicked": False}
    try:
        button = page.get_by_role("button", name=FIELDS[field], exact=True)
        if button.count() != 1:
            raise ValueError("Edit control missing for field")
        button.click(timeout=6500)
        result["opened"] = True
        # Lightning may render the value input before the Cancel action. Wait
        # for a fully opened editor so the finally block can always dismiss it.
        page.get_by_role("button", name="Cancel", exact=True).wait_for(
            state="visible", timeout=7000)
        if field == "Opportunity Name":
            loc = page.get_by_role("textbox", name="Opportunity Name", exact=True)
            if loc.count() != 1 or not loc.is_visible() or not loc.is_enabled():
                raise ValueError("Name input is not exact/unique")
        else:
            loc = locate_field(page, field)
        value = loc.input_value()
        if not value.strip():
            raise ValueError("Empty current value; refuse to seed template")
    finally:
        editor_close(page, result)
    return value


def build_from_browser(browser, bridge, lookup):
    target = bridge.get("opportunity_record_id")
    found = []
    for context in browser.contexts:
        for page in context.pages:
            u = urlsplit(page.url)
            match = SFDC_ROUTE.fullmatch(u.path)
            if u.hostname == "novogene.lightning.force.com" and match and match.group(1) == target:
                found.append(page)
    if len(found) != 1:
        raise ValueError("Exactly one verified Opportunity tab required")
    page = found[0]
    validate_preflight(
        bridge, urlsplit(page.url).path,
        save_count=page.get_by_role("button", name="Save", exact=True).count(),
        cancel_count=page.get_by_role("button", name="Cancel", exact=True).count())
    tab = page.get_by_role("tab", name="Details", exact=True)
    if tab.count() != 1:
        raise ValueError("Unique Details tab required")
    if tab.get_attribute("aria-selected") != "true":
        tab.click(timeout=6000)
        page.wait_for_timeout(250)
    check_lookup_ids(lookup, page.evaluate(DOM_SCRIPT), target)
    originals = {}
    for name in FIELDS:
        originals[name] = current_value(page, name)
    return blank_request(
        target, bridge.get("business_opportunity_id"),
        lookup, originals, "REQ-" + secrets.token_hex(10))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--bridge", default=str(Path.home() / ".sfdc_desktop"
                                           / "verified_live_quotation_report_bridge.json"))
    p.add_argument("--lookups", default=str(Path.home() / ".sfdc_desktop"
                                            / "existing_lookup_record_ids_private.json"))
    p.add_argument("--output", default=str(Path.home() / ".sfdc_desktop"
                                           / "existing_change_review_TEMPLATE_PRIVATE.json"))
    p.add_argument("--cdp-url", default="http://127.0.0.1:9222")
    a = p.parse_args()
    if a.cdp_url != "http://127.0.0.1:9222":
        p.error("Only authorized localhost CDP permitted")
    target = Path(a.output)
    if target.exists():
        p.error("Refusing to overwrite existing reviewed/manual file")
    bridge = json.loads(Path(a.bridge).read_text("utf-8-sig"))
    lookups = json.loads(Path(a.lookups).read_text("utf-8-sig"))
    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(a.cdp_url, timeout=10000)
        request = build_from_browser(browser, bridge, lookups)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("x", encoding="utf-8") as f:
        json.dump(request, f, ensure_ascii=False, indent=2)
    print("PRIVATE TEMPLATE CREATED:", target)
    print("CURRENT FIELD REFERENCES CAPTURED:", len(request["observed_current_values_reference_only"]))
    print("CHANGED FIELD COUNT: 0")
    print("REVIEWED CURRENT VALUES: FALSE")
    print("SALESFORCE SAVE: NEVER")


if __name__ == "__main__":
    main()
