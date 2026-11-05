#!/usr/bin/env python3
"""Read-only / no-op fill pilot for one verified existing SFDC Opportunity.

Authenticated Chrome CDP 127.0.0.1:9222 only.
No Salesforce Save, no new values, no lookup selection, no secrets in logs.
Writes only redacted audit metadata into a private Windows workstation path.
"""
import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright

SFDC_ROUTE = re.compile(r"/lightning/r/Opportunity/(006[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?)/view/?\Z")
SAFE_STATUSES = {"VERIFIED_BY_LIVE_QUOTATION_REPORT"}


def validate_preflight(bridge, route_path, save_count=0, cancel_count=0):
    """Pure fail-closed authorization of the exact target, never a Save grant."""
    match = SFDC_ROUTE.fullmatch(str(route_path or ""))
    if (not isinstance(bridge, dict) or bridge.get("status") not in SAFE_STATUSES
            or bridge.get("identity_verified") is not True
            or bridge.get("save_allowed") is not False
            or bridge.get("salesforce_save_performed") is not False
            or not match
            or bridge.get("opportunity_record_id") != match.group(1)):
        raise ValueError("Exact verified read-only Opportunity bridge required")
    if save_count or cancel_count:
        raise ValueError("An editor is already open; preserve pre-existing edits")
    return True


def check_lookup_controls(observed):
    """Reject ambiguous/hidden control topology; do not certify chosen record IDs."""
    required = {"Account Name": "Search Accounts...",
                "Main Contact": "Search Contacts..."}
    if not isinstance(observed, dict):
        return False
    return all(
        key in observed
        and observed[key].get("count") == 1
        and observed[key].get("visible") is True
        and observed[key].get("enabled") is True
        and observed[key].get("placeholder") == placeholder
        for key, placeholder in required.items()
    )


def editor_close(page, report):
    if not report.get("opened"):
        return
    cancel = page.get_by_role("button", name="Cancel", exact=True)
    if cancel.count() != 1:
        report["cancel_failed"] = True
        raise RuntimeError("Expected one Cancel button; editor left untouched, Save forbidden")
    cancel.click(timeout=7000)
    page.wait_for_timeout(200)
    report["cancel_clicked"] = True
    if page.get_by_role("button", name="Save", exact=True).count() != 0:
        report["cancel_failed"] = True
        raise RuntimeError("Edit form did not close after Cancel")


def inspect_lookups(page):
    result = {"opened": False, "cancel_clicked": False, "save_clicked": False}
    button = page.get_by_role("button", name="Edit Account Name", exact=True)
    if button.count() != 1:
        raise ValueError("Account editor launch button missing or ambiguous")
    try:
        button.click(timeout=7000)
        result["opened"] = True
        for field in ("Account Name", "Main Contact", "end user account", "end user contact"):
            el = page.get_by_role("combobox", name=field, exact=True)
            result[field] = {
                "count": el.count(),
                "visible": el.count() == 1 and el.is_visible(),
                "enabled": el.count() == 1 and el.is_enabled(),
                "placeholder": el.get_attribute("placeholder") if el.count() == 1 else None,
                "readonly": el.get_attribute("readonly") is not None if el.count() == 1 else None,
            }
        result["primary_lookup_topology_ok"] = check_lookup_controls(result)
        result["lookup_record_id_verified"] = False  # UI controls alone prove no association!
    finally:
        editor_close(page, result)
    return result


def no_change_fill(page):
    result = {"opened": False, "cancel_clicked": False,
              "save_clicked": False, "same_value_fill_executed": False}
    button = page.get_by_role("button", name="Edit Opportunity Name", exact=True)
    if button.count() != 1:
        raise ValueError("Opportunity name editor launch missing or ambiguous")
    try:
        button.click(timeout=7000)
        result["opened"] = True
        field = page.get_by_role("textbox", name="Opportunity Name", exact=True)
        if field.count() != 1 or not field.is_visible() or not field.is_enabled():
            raise RuntimeError("Unique visible enabled name field required")
        original = field.input_value()
        if not original.strip():
            raise RuntimeError("Existing name is empty; refuse to invent a value")
        field.fill(original, timeout=7000)
        result["same_value_fill_executed"] = True
        result["same_value_in_editor"] = field.input_value() == original
        # Never print or save original/customer values.
    finally:
        editor_close(page, result)
    return result


def audit(browser, bridge):
    target_id = bridge.get("opportunity_record_id")
    pages = [p for ctx in browser.contexts for p in ctx.pages
             if urlsplit(p.url).hostname == "novogene.lightning.force.com"
             and SFDC_ROUTE.fullmatch(urlsplit(p.url).path)
             and target_id == SFDC_ROUTE.fullmatch(urlsplit(p.url).path).group(1)]
    if len(pages) != 1:
        raise ValueError("Exactly one matching authenticated Opportunity tab required")
    page = pages[0]
    path = urlsplit(page.url).path
    validate_preflight(
        bridge, path,
        save_count=page.get_by_role("button", name="Save", exact=True).count(),
        cancel_count=page.get_by_role("button", name="Cancel", exact=True).count()
    )
    detail_tabs = page.get_by_role("tab", name="Details", exact=True)
    if detail_tabs.count() != 1:
        raise ValueError("Exactly one Details tab required")
    if detail_tabs.get_attribute("aria-selected") != "true":
        detail_tabs.click(timeout=7000)
        page.wait_for_timeout(250)
    lookups = inspect_lookups(page)
    if not lookups["cancel_clicked"] or not lookups["primary_lookup_topology_ok"]:
        raise RuntimeError("Account/Contact field topology or Cancel check failed")
    fill = no_change_fill(page)
    if not (fill["cancel_clicked"] and fill["same_value_fill_executed"]
            and fill["same_value_in_editor"]):
        raise RuntimeError("No-change fill or Cancel check failed")
    return {
        "version": "sfdc-opportunity-existing-no-save-audit-v1",
        "checked_utc": datetime.now(timezone.utc).isoformat(),
        "exact_record_identity_preflight": True,
        "unique_opportunity_page": True,
        "account_contact_lookup_controls": lookups,
        "opportunity_name_no_change_fill": fill,
        "lookup_selection_performed": False,
        "lookup_record_id_verified": False,
        "salesforce_save_allowed": False,
        "salesforce_save_performed": False,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bridge", default=str(
        Path.home() / ".sfdc_desktop" / "verified_live_quotation_report_bridge.json"))
    parser.add_argument("--output", default=str(
        Path.home() / ".sfdc_desktop" / "existing_opportunity_no_save_audit.json"))
    parser.add_argument("--cdp-url", default="http://127.0.0.1:9222")
    args = parser.parse_args()
    if args.cdp_url != "http://127.0.0.1:9222":
        parser.error("Only loopback CDP is authorized")
    bridge = json.loads(Path(args.bridge).read_text(encoding="utf-8-sig"))
    with sync_playwright() as pw:
        b = pw.chromium.connect_over_cdp(args.cdp_url, timeout=12000)
        result = audit(b, bridge)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("EXISTING OPPORTUNITY IDENTITY: VERIFIED")
    print("ACCOUNT / CONTACT LOOKUP UI:", result["account_contact_lookup_controls"]["primary_lookup_topology_ok"])
    print("NAME SAME-VALUE FILL + CANCEL:", result["opportunity_name_no_change_fill"]["cancel_clicked"])
    print("LOOKUP RECORD IDS VERIFIED: FALSE")
    print("SFDC SAVE PERFORMED: FALSE")
    print("PRIVATE REDACTED AUDIT:", output)


if __name__ == "__main__":
    main()
