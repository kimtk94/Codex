#!/usr/bin/env python3
"""Existing Salesforce Opportunity approved fill-only rehearsal, always Cancel.

Intentionally has NO Save click. A reviewed request plus a distinct approval for
a *temporary no-Save rehearsal* is required even to fill an unsaved edit form.
Each field is compare-and-swapped inside the same editor session, then Cancel.
The browser is not contacted for unreviewed/unsupported/duplicate requests.
Sensitive inputs/IDs remain in private Windows JSON; logs contain statuses only.
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright

from audit_existing_opportunity_no_save import SFDC_ROUTE, validate_preflight, editor_close
from audit_existing_numeric_date_nochange import locate_field, check_lookup_ids
from capture_existing_lookup_links import DOM_SCRIPT
from make_existing_change_template import FIELDS
from prepare_existing_change_review import prepare
from save_readback_contract import validate_ledger
from verify_existing_live_before import inspect_request, enforce_clean_ledger

# First pilot supports text Name, numeric Amount, and date only.
# Other editable fields (Stage, currency, Account/Contact, Progress Description)
# have not passed exact control and record-ID tests.
SUPPORTED_FIELDS = frozenset(FIELDS)
STATUS_HOLD = "HOLD_REVIEW_OR_PILOT_APPROVAL_REQUIRED"


def gate(request, bridge=None, lookup=None, ledger=None):
    """Read-only preflight. No connection to Salesforce and no values logged."""
    if inspect_request(request) != "READY_FOR_PREFLIGHT":
        return STATUS_HOLD, None
    if request.get("fill_only_pilot_approved") is not True:
        return STATUS_HOLD, None
    if (not set(request["changes"]).issubset(SUPPORTED_FIELDS)
            or request.get("save_allowed") is not False):
        return "HOLD_UNSUPPORTED_FIELD", None
    if request.get("approved_fill_only_request_uid") != request.get("request_uid"):
        return "HOLD_FILL_ONLY_REQUEST_ID_MISMATCH", None
    preflight, _ = enforce_clean_ledger(request, bridge, lookup, ledger)
    return "READY_FOR_CANCEL_ONLY_REHEARSAL", preflight


def locate_exact_editor_field(page, field):
    if field == "Opportunity Name":
        locator = page.get_by_role("textbox", name="Opportunity Name", exact=True)
        if locator.count() != 1 or not locator.is_visible() or not locator.is_enabled():
            raise ValueError("Opportunity Name field not uniquely editable")
        return locator
    if field in ("Amount", "Close Date"):
        return locate_field(page, field)
    raise ValueError("Unsupported editor field")


def rehearsal_field(page, field, old, new):
    """One atomic edit-session check, fill and Cancel. Never click Save."""
    if field not in SUPPORTED_FIELDS:
        raise ValueError("Field not explicitly allowlisted")
    result = {"field": field, "opened": False, "before_equal": False,
              "after_equal": False, "cancel_clicked": False, "save_clicked": False}
    if (page.get_by_role("button", name="Save", exact=True).count()
            or page.get_by_role("button", name="Cancel", exact=True).count()):
        raise ValueError("Existing editor must not be disturbed")
    button = page.get_by_role("button", name=FIELDS[field], exact=True)
    if button.count() != 1:
        raise ValueError("Unique Edit button not found")
    try:
        button.click(timeout=6500)
        result["opened"] = True
        input_field = locate_exact_editor_field(page, field)
        before = input_field.input_value()
        result["before_equal"] = before == old
        if not result["before_equal"]:
            result["status"] = "HOLD_STALE_BEFORE_VALUE"
            return result
        input_field.fill(new, timeout=6500)
        result["after_equal"] = input_field.input_value() == new
        result["status"] = ("CANCEL_ONLY_REHEARSAL_FIELD_MATCH" if result["after_equal"]
                            else "HOLD_FIELD_AFTER_FILL_DIFFERS")
        return result
    finally:
        if result["opened"]:
            editor_close(page, result)


def replay(browser, request, bridge, lookup, ledger):
    """Fail closed: each edit is cancelled, later fields stop after any HOLD."""
    decision, preflight = gate(request, bridge, lookup, ledger)
    if decision != "READY_FOR_CANCEL_ONLY_REHEARSAL":
        return {"version": "sfdc-cancel-only-change-rehearsal-v1", "status": decision,
                "fields_rehearsed": 0, "fill_only_approved": False,
                "save_allowed": False, "salesforce_save_performed": False}

    target = preflight["target_record_id"]
    matches = []
    for context in browser.contexts:
        for page in context.pages:
            u = urlsplit(page.url)
            found = SFDC_ROUTE.fullmatch(u.path)
            if (u.hostname == "novogene.lightning.force.com"
                    and found and found.group(1) == target):
                matches.append(page)
    if len(matches) != 1:
        raise ValueError("Exactly one authorized existing Opportunity tab required")
    page = matches[0]
    validate_preflight(
        bridge, urlsplit(page.url).path,
        save_count=page.get_by_role("button", name="Save", exact=True).count(),
        cancel_count=page.get_by_role("button", name="Cancel", exact=True).count())
    details = page.get_by_role("tab", name="Details", exact=True)
    if details.count() != 1:
        raise ValueError("Unique Details tab required")
    if details.get_attribute("aria-selected") != "true":
        details.click(timeout=6500)
        page.wait_for_timeout(250)
    check_lookup_ids(lookup, page.evaluate(DOM_SCRIPT), target)
    per_field = []
    for field in sorted(request["changes"]):
        item = rehearsal_field(page, field, request["expected_before_values"][field],
                               request["changes"][field])
        per_field.append(item)
        if (item.get("status") != "CANCEL_ONLY_REHEARSAL_FIELD_MATCH"
                or not item["cancel_clicked"]):
            break
        # Never reuse stale lookups or leave an editor open between fields.
        check_lookup_ids(lookup, page.evaluate(DOM_SCRIPT), target)
        if (page.get_by_role("button", name="Save", exact=True).count()
                or page.get_by_role("button", name="Cancel", exact=True).count()):
            raise RuntimeError("Editor still open after Cancel")
    success = (len(per_field) == len(request["changes"])
               and all(x["status"] == "CANCEL_ONLY_REHEARSAL_FIELD_MATCH"
                       and x["cancel_clicked"] for x in per_field))
    return {
        "version": "sfdc-cancel-only-change-rehearsal-v1",
        "status": "REHEARSAL_CANCELLED_ALL_FIELDS" if success else "HOLD_FIELD_REHEARSAL",
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "operation_fingerprint": preflight["operation_fingerprint"],
        "changed_field_names": sorted(request["changes"]),
        "fields_rehearsed": len(per_field),
        "per_field_result": per_field,  # Only statuses; no original/new values.
        "lookup_selection_performed": False,
        "actual_salesforce_changes_committed": False,
        "save_allowed": False, "salesforce_save_performed": False,
    }


def main():
    p = argparse.ArgumentParser()
    base = Path.home() / ".sfdc_desktop"
    p.add_argument("--request", default=str(base / "existing_change_review_TEMPLATE_PRIVATE.json"))
    p.add_argument("--bridge", default=str(base / "verified_live_quotation_report_bridge.json"))
    p.add_argument("--lookups", default=str(base / "existing_lookup_record_ids_private.json"))
    p.add_argument("--ledger", default=str(base / "operation_ledger_private.json"))
    p.add_argument("--output", default=str(base / "cancel_only_rehearsal_private.json"))
    p.add_argument("--cdp-url", default="http://127.0.0.1:9222")
    args = p.parse_args()
    if args.cdp_url != "http://127.0.0.1:9222":
        p.error("Only loopback CDP permitted")
    request = json.loads(Path(args.request).read_text(encoding="utf-8-sig"))
    # IMPORTANT: Check review before reading any identity secrets, ledger or Chrome.
    if (inspect_request(request) != "READY_FOR_PREFLIGHT"
            or request.get("fill_only_pilot_approved") is not True):
        result = replay(None, request, None, None, None)
    else:
        def load(path):
            return json.loads(Path(path).read_text(encoding="utf-8-sig"))
        bridge = load(args.bridge)
        lookups = load(args.lookups)
        ledger = load(args.ledger)  # Missing ledger = fail closed, never assume empty.
        gate(request, bridge, lookups, ledger)  # Offline evidence validation before CDP.
        with sync_playwright() as pw:
            browser = pw.chromium.connect_over_cdp(args.cdp_url, timeout=12000)
            result = replay(browser, request, bridge, lookups, ledger)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("CANCEL-ONLY REHEARSAL STATUS:", result["status"])
    print("FIELDS REHEARSED:", result["fields_rehearsed"])
    print("SALESFORCE SAVE PERFORMED: FALSE")
    print("PRIVATE RESULT:", output)


if __name__ == "__main__":
    main()
