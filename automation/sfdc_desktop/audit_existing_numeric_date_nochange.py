#!/usr/bin/env python3
"""Verified existing Salesforce Opportunity: same-value Amount/Close Date fill + Cancel.

No Save, no new values, no edit to lookups. Existing Account/Contact field IDs
must match the immediately re-read live UI before any no-op interaction.
Only run against an owner's manually authenticated localhost Chrome session.
"""
import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright

from audit_existing_opportunity_no_save import SFDC_ROUTE, validate_preflight, editor_close
from capture_existing_lookup_links import DOM_SCRIPT, validate_links
from related_quotation_bridge import same_record

NOOP_FIELDS = {
    "Amount": ("spinbutton", "Edit Amount"),
    "Close Date": ("textbox", "Edit Close Date"),
}
FIELD_LABEL = re.compile(r"^\*?\s*(Amount|Close Date)\s*$")


def normalize_field_label(label):
    """Strip exactly the optional Salesforce required marker, never fuzzy-match."""
    normalized = re.sub(r"\s+", " ", str(label or "")).strip()
    m = FIELD_LABEL.fullmatch(normalized)
    return m.group(1) if m else None


def locate_field(page, label):
    """Use label from direct editor field container, not global ordinal indices."""
    if label not in NOOP_FIELDS:
        raise ValueError("Only non-lookup Amount and Close Date no-op fields allowed")
    role, _ = NOOP_FIELDS[label]
    found = []
    for el in page.get_by_role(role).all():
        if not el.is_visible() or not el.is_enabled():
            continue
        detected = el.evaluate("""e => {
          const box = e.parentElement && e.parentElement.parentElement;
          if (!box) return [];
          return [...box.querySelectorAll('label,.slds-form-element__label')]
            .map(l => (l.innerText || l.textContent || '').trim());
        }""")
        if len([v for v in detected if normalize_field_label(v) == label]) == 1:
            found.append(el)
    if len(found) != 1:
        raise ValueError("Exactly one field-labeled input required: " + label)
    return found[0]


def check_lookup_ids(expected, observed, record_id):
    """Compare local private link evidence to fresh DOM field links."""
    if (expected.get("account_contact_field_links_verified") is not True
            or expected.get("salesforce_save_performed") is not False
            or not same_record(expected.get("opportunity_record_id"), record_id)):
        raise ValueError("Existing Account/Contact evidence not verified for record")
    direct = validate_links(observed)
    for field in ("account_record_id", "contact_record_id"):
        if not same_record(direct[field], expected.get(field)):
            raise ValueError("Existing lookup record ID changed or disagrees")
    return True


def noop_field(page, label):
    if label not in NOOP_FIELDS:
        raise ValueError("Field not allowlisted")
    _, action = NOOP_FIELDS[label]
    report = {"field": label, "opened": False, "same_value_reentered": False,
              "same_value_confirmed": False, "cancel_clicked": False,
              "salesforce_save_performed": False}
    btn = page.get_by_role("button", name=action, exact=True)
    if btn.count() != 1:
        raise ValueError("Exactly one inline edit button required: " + label)
    try:
        btn.click(timeout=6500)
        report["opened"] = True
        field = locate_field(page, label)
        old = field.input_value()
        if not old.strip():
            raise ValueError("Current value missing; do not invent data")
        # No-op: user data is read from the currently displayed edit control.
        field.fill(old, timeout=6500)
        report["same_value_reentered"] = True
        report["same_value_confirmed"] = field.input_value() == old
        if not report["same_value_confirmed"]:
            raise RuntimeError("No-op fill changed the value")
    finally:
        editor_close(page, report)
    return report


def audit(browser, bridge, lookup_evidence):
    expected = bridge.get("opportunity_record_id", "")
    pages = []
    for context in browser.contexts:
        for page in context.pages:
            u = urlsplit(page.url)
            m = SFDC_ROUTE.fullmatch(u.path)
            if (u.hostname == "novogene.lightning.force.com"
                    and m and same_record(m.group(1), expected)):
                pages.append(page)
    if len(pages) != 1:
        raise ValueError("One verified existing Opportunity tab required")
    page = pages[0]
    validate_preflight(
        bridge, urlsplit(page.url).path,
        save_count=page.get_by_role("button", name="Save", exact=True).count(),
        cancel_count=page.get_by_role("button", name="Cancel", exact=True).count(),
    )
    tab = page.get_by_role("tab", name="Details", exact=True)
    if tab.count() != 1:
        raise ValueError("Unique Details tab required")
    if tab.get_attribute("aria-selected") != "true":
        tab.click(timeout=6500)
        page.wait_for_timeout(220)
    check_lookup_ids(lookup_evidence, page.evaluate(DOM_SCRIPT), expected)

    audits = []
    for label in NOOP_FIELDS:
        if (page.get_by_role("button", name="Save", exact=True).count()
                or page.get_by_role("button", name="Cancel", exact=True).count()):
            raise RuntimeError("A previous editor was not cleanly closed")
        audits.append(noop_field(page, label))
        if not (audits[-1]["cancel_clicked"] and audits[-1]["same_value_confirmed"]):
            raise RuntimeError("No-op fill/cancel failed for " + label)

    stage = page.get_by_role("button", name="Edit Stage", exact=True)
    return {
        "version": "existing-opportunity-nochange-numeric-date-v1",
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "exact_opportunity_id_verified": True,
        "existing_account_contact_record_ids_rechecked": True,
        "fields": audits,
        "stage_edit_button_count": stage.count(),
        "actual_changed_values": False,
        "lookup_selection_performed": False,
        "salesforce_save_allowed": False,
        "salesforce_save_performed": False,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bridge", default=str(
        Path.home() / ".sfdc_desktop" / "verified_live_quotation_report_bridge.json"))
    ap.add_argument("--lookup-evidence", default=str(
        Path.home() / ".sfdc_desktop" / "existing_lookup_record_ids_private.json"))
    ap.add_argument("--output", default=str(
        Path.home() / ".sfdc_desktop" / "nochange_numeric_date_audit.json"))
    ap.add_argument("--cdp-url", default="http://127.0.0.1:9222")
    args = ap.parse_args()
    if args.cdp_url != "http://127.0.0.1:9222":
        ap.error("Only local CDP endpoint authorized")
    bridge = json.loads(Path(args.bridge).read_text(encoding="utf-8-sig"))
    lookups = json.loads(Path(args.lookup_evidence).read_text(encoding="utf-8-sig"))
    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(args.cdp_url, timeout=12000)
        result = audit(browser, bridge, lookups)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("EXACT TARGET AND LOOKUP IDS: VERIFIED")
    print("NO-CHANGE FIELDS TESTED:", len(result["fields"]))
    print("CANCELLED ALL:", all(f["cancel_clicked"] for f in result["fields"]))
    print("SALESFORCE SAVE PERFORMED: FALSE")
    print("PRIVATE RESULT:", out)


if __name__ == "__main__":
    main()
