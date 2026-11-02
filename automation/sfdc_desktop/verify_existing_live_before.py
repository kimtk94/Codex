#!/usr/bin/env python3
"""Fail-closed read-before-write verification for a reviewed existing Opportunity.

This command NEVER fills changed values or clicks Salesforce Save.
- Unreviewed/blank private template => HOLD without touching Salesforce.
- Reviewed request => offline identity/UID gate, then fresh UI field/link reads.
- Values must match reviewed expected_before_values EXACTLY; display format
  differences hold rather than attempting risky locale/currency guesses.
- Every opened inline editor is closed by Cancel even after an exception.
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright

from audit_existing_opportunity_no_save import SFDC_ROUTE, validate_preflight
from audit_existing_numeric_date_nochange import check_lookup_ids
from capture_existing_lookup_links import DOM_SCRIPT
from make_existing_change_template import current_value, FIELDS
from prepare_existing_change_review import prepare
from save_readback_contract import validate_ledger

# Progress Description intentionally held until a unique editor control is audited.
LIVE_CHECK_FIELDS = frozenset(FIELDS)
HOLD_REVIEW = "HOLD_REVIEW_REQUIRED"


def inspect_request(request):
    """Unreviewed template is HOLD, never implicit approval."""
    if not isinstance(request, dict):
        raise ValueError("Private request must be an object")
    if (request.get("reviewed_current_deal_values") is not True
            or not isinstance(request.get("changes"), dict)
            or not request["changes"]):
        return HOLD_REVIEW
    if not set(request["changes"]).issubset(LIVE_CHECK_FIELDS):
        return "HOLD_UNSUPPORTED_FIELD_LIVE_READ"
    return "READY_FOR_PREFLIGHT"


def evaluate_before(preflight, request, observed):
    """Pure compare-and-swap gate. Same values alone do not authorize filling."""
    if not isinstance(preflight, dict) or preflight.get("save_allowed") is not False:
        raise ValueError("Verified no-Save preflight required")
    if not isinstance(observed, dict):
        raise ValueError("Actual live before values must be an object")
    expected = request["expected_before_values"]
    changed = request["changes"]
    if set(observed) != set(expected) or set(changed) != set(expected):
        return "HOLD_LIVE_FIELD_SET_MISMATCH"
    if any(not isinstance(observed[k], str) or observed[k] != expected[k] for k in expected):
        return "HOLD_LIVE_BEFORE_VALUE_CHANGED"
    return "VERIFIED_LIVE_BEFORE_VALUES"


def capture_live_fields(browser, preflight, bridge, lookup):
    """Never capture values through an unrelated tab or by ordinal input indices."""
    target = str(preflight.get("target_record_id") or "")
    matches = []
    for context in browser.contexts:
        for page in context.pages:
            u = urlsplit(page.url)
            route = SFDC_ROUTE.fullmatch(u.path)
            if (u.hostname == "novogene.lightning.force.com"
                    and route and route.group(1) == target):
                matches.append(page)
    if len(matches) != 1:
        raise ValueError("Exactly one verified Opportunity tab required")
    page = matches[0]
    validate_preflight(
        bridge, urlsplit(page.url).path,
        save_count=page.get_by_role("button", name="Save", exact=True).count(),
        cancel_count=page.get_by_role("button", name="Cancel", exact=True).count(),
    )
    details = page.get_by_role("tab", name="Details", exact=True)
    if details.count() != 1:
        raise ValueError("Details tab missing/ambiguous")
    if details.get_attribute("aria-selected") != "true":
        details.click(timeout=6000)
        page.wait_for_timeout(250)
    check_lookup_ids(lookup, page.evaluate(DOM_SCRIPT), target)

    observed = {}
    for field in preflight["changed_fields"]:
        if field not in LIVE_CHECK_FIELDS:
            raise ValueError("Unsupported field for live before-value verification")
        if (page.get_by_role("button", name="Save", exact=True).count()
                or page.get_by_role("button", name="Cancel", exact=True).count()):
            raise RuntimeError("Pre-existing or leaked editor detected")
        observed[field] = current_value(page, field)  # always Cancel in finally
    return observed


def enforce_clean_ledger(request, bridge, lookup, ledger_data):
    """Fail closed for missing/versionless ledger AND same operation under a new UID."""
    rows = validate_ledger(ledger_data)
    preflight = prepare(request, bridge, lookup, [r["request_uid"] for r in rows])
    if any(row["operation_fingerprint"] == preflight["operation_fingerprint"] for row in rows):
        raise ValueError("Already recorded matching operation fingerprint")
    return preflight, [r["request_uid"] for r in rows]


def run(request, bridge, lookup, ledger, browser=None):
    """No Salesforce touches unless a user-reviewed request passes offline gate."""
    decision = inspect_request(request)
    if decision != "READY_FOR_PREFLIGHT":
        return {"version": "existing-live-before-gate-v1", "status": decision,
                "live_before_values_verified": False, "fill_allowed": False,
                "salesforce_save_allowed": False, "salesforce_save_performed": False}
    preflight = prepare(request, bridge, lookup, ledger)
    if browser is None:
        return {"version": "existing-live-before-gate-v1",
                "status": "HOLD_LIVE_READ_NOT_EXECUTED",
                "operation_fingerprint": preflight["operation_fingerprint"],
                "live_before_values_verified": False, "fill_allowed": False,
                "salesforce_save_allowed": False, "salesforce_save_performed": False}
    observed = capture_live_fields(browser, preflight, bridge, lookup)
    status = evaluate_before(preflight, request, observed)
    return {
        "version": "existing-live-before-gate-v1",
        "status": status,
        "checked_utc": datetime.now(timezone.utc).isoformat(),
        "operation_fingerprint": preflight["operation_fingerprint"],
        "checked_field_names": sorted(observed),
        "live_before_values_verified": status == "VERIFIED_LIVE_BEFORE_VALUES",
        "fill_allowed": False,  # A separate explicit fill-only command/approval is required.
        "values_filled": False,
        "salesforce_save_allowed": False,
        "salesforce_save_performed": False,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", default=str(Path.home() / ".sfdc_desktop" /
                                                "existing_change_review_TEMPLATE_PRIVATE.json"))
    parser.add_argument("--bridge", default=str(Path.home() / ".sfdc_desktop" /
                                               "verified_live_quotation_report_bridge.json"))
    parser.add_argument("--lookups", default=str(Path.home() / ".sfdc_desktop" /
                                                "existing_lookup_record_ids_private.json"))
    parser.add_argument("--ledger", default=str(Path.home() / ".sfdc_desktop" /
                                               "operation_ledger_private.json"),
                        help="Required versioned private operation ledger; no writes")
    parser.add_argument("--output", default=str(Path.home() / ".sfdc_desktop" /
                                               "live_before_verification_private.json"))
    parser.add_argument("--cdp-url", default="http://127.0.0.1:9222")
    args = parser.parse_args()
    if args.cdp_url != "http://127.0.0.1:9222":
        parser.error("Only localhost Chrome CDP is authorized")
    def read(path):
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    req = read(args.request)
    gate = inspect_request(req)
    if gate != "READY_FOR_PREFLIGHT":
        result = run(req, {}, {}, ())
    else:
        bridge, lookup = read(args.bridge), read(args.lookups)
        # Do not treat missing ledger as an empty history. Require it on disk.
        preflight, previous_uids = enforce_clean_ledger(
            req, bridge, lookup, read(args.ledger))
        with sync_playwright() as pw:
            browser = pw.chromium.connect_over_cdp(args.cdp_url, timeout=12000)
            result = run(req, bridge, lookup, previous_uids, browser)
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("LIVE BEFORE-READ STATUS:", result["status"])
    print("LIVE BEFORE VALUES VERIFIED:", result["live_before_values_verified"])
    print("FILL ALLOWED:", result["fill_allowed"])
    print("SALESFORCE SAVE PERFORMED: FALSE")
    print("PRIVATE OUTPUT:", path)


if __name__ == "__main__":
    main()
