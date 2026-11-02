#!/usr/bin/env python3
"""Offline, human-reviewed EXISTING Opportunity change request preflight.

Prepare a private, unsaved fill-only proposal for a specifically verified record.
Never enter values into Salesforce or authorize Save. Real inputs and current values
must be supplied separately by an explicitly reviewed private file.
"""
import argparse
import hashlib
import json
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from audit_existing_opportunity_no_save import validate_preflight
from related_quotation_bridge import same_record, BUSINESS
from capture_existing_lookup_links import ACCOUNT, CONTACT

ALLOWED_FIELDS = frozenset({
    "Opportunity Name", "Amount", "Close Date", "Progress Description"
})
REQUEST_UID = re.compile(r"REQ-[A-Za-z0-9_-]{8,64}\Z")
AMOUNT_PATTERN = re.compile(r"(?:0|[1-9]\d*)(?:\.\d{1,2})?\Z")


def validate_field_value(field, value):
    if field not in ALLOWED_FIELDS:
        raise ValueError("Field not allowlisted")
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError("Value must be a nonempty, explicitly reviewed string")
    if field == "Opportunity Name" and len(value) > 255:
        raise ValueError("Opportunity Name too long")
    if field == "Progress Description" and len(value) > 1500:
        raise ValueError("Progress Description too long")
    if field == "Amount":
        if not AMOUNT_PATTERN.fullmatch(value):
            raise ValueError("Amount must be plain nonnegative decimal (no currency)")
        try:
            amount = Decimal(value)
        except InvalidOperation as exc:
            raise ValueError("Invalid amount") from exc
        if not amount.is_finite() or amount > Decimal("999999999999.99"):
            raise ValueError("Amount outside approved range")
    if field == "Close Date":
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ValueError("Close Date must use YYYY-MM-DD")
        try:
            date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("Invalid calendar date") from exc
    return value


def prepare(request, bridge, lookups, prior_operations=()):
    """Fail closed: exact existing target and same Account/Contact ID are mandatory."""
    if not isinstance(request, dict) or not isinstance(prior_operations, (tuple, list, set)):
        raise ValueError("Invalid request or ledger")
    uid = request.get("request_uid")
    if not isinstance(uid, str) or not REQUEST_UID.fullmatch(uid):
        raise ValueError("Stable non-empty request UID required")
    if uid in prior_operations:
        raise ValueError("Duplicate request UID already seen in ledger")
    if request.get("mode") != "EXISTING_OPPORTUNITY_FILL_ONLY":
        raise ValueError("Only existing-Opportunity fill-only requests supported")
    if request.get("reviewed_current_deal_values") is not True:
        raise ValueError("Explicit review acknowledgement for current deal values required")
    target = str(request.get("target_opportunity_record_id") or "").strip()
    validate_preflight(bridge, "/lightning/r/Opportunity/" + target + "/view")
    if (lookups.get("account_contact_field_links_verified") is not True
            or lookups.get("salesforce_save_allowed") is not False
            or lookups.get("salesforce_save_performed") is not False
            or not same_record(lookups.get("opportunity_record_id"), target)
            or not ACCOUNT.fullmatch(str(lookups.get("account_record_id") or ""))
            or not CONTACT.fullmatch(str(lookups.get("contact_record_id") or ""))):
        raise ValueError("Existing Account/Contact field link evidence missing or inconsistent")
    if (request.get("expected_account_record_id") != lookups["account_record_id"]
            or request.get("expected_contact_record_id") != lookups["contact_record_id"]):
        raise ValueError("Reviewed Account/Contact IDs disagree with verified existing fields")
    verified_business = str(bridge.get("business_opportunity_id") or "")
    if (bridge.get("version") != "live-related-quote-report-bridge-v1"
            or not BUSINESS.fullmatch(verified_business)
            or request.get("business_opportunity_id") != verified_business):
        raise ValueError("Business Opportunity ID does not match verified report")
    changes = request.get("changes")
    originals = request.get("expected_before_values")
    if not isinstance(changes, dict) or not changes:
        raise ValueError("At least one explicitly reviewed changed field required")
    if not isinstance(originals, dict) or set(originals) != set(changes):
        raise ValueError("One reviewed before-value required for every proposed change")
    for field, value in changes.items():
        validate_field_value(field, value)
        if not isinstance(originals[field], str):
            raise ValueError("Expected before-value must be a string")
        if originals[field] == value:
            raise ValueError("No-op edits should use separate no-change audit")
    if request.get("save_allowed") is not False:
        raise ValueError("Salesforce Save must be explicitly prohibited")
    canonical = json.dumps({
        "record_id": target, "request_uid": uid, "expected_before": originals,
        "changes": changes, "account_record_id": lookups["account_record_id"],
        "contact_record_id": lookups["contact_record_id"],
    }, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return {
        "version": "existing-fill-only-review-preflight-v1",
        "status": "PREPARED_FOR_LIVE_BEFORE_VALUE_CHECK",
        "request_uid": uid,
        "target_record_id": target,  # Private local JSON only, not CI artifact.
        "changed_fields": sorted(changes),
        "operation_fingerprint": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "approval_for_salesforce_save": False,
        "live_before_values_verified": False,
        "lookup_selection_performed": False,
        "save_allowed": False,
        "salesforce_save_performed": False,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--request", required=True, help="Private manually reviewed JSON")
    p.add_argument("--bridge", default=str(
        Path.home() / ".sfdc_desktop" / "verified_live_quotation_report_bridge.json"))
    p.add_argument("--lookups", default=str(
        Path.home() / ".sfdc_desktop" / "existing_lookup_record_ids_private.json"))
    p.add_argument("--prior-ledger", default="", help="Optional private JSON UID array")
    p.add_argument("--output", default=str(
        Path.home() / ".sfdc_desktop" / "approved_change_preflight_private.json"))
    a = p.parse_args()
    def read(path):
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    ledger = read(a.prior_ledger) if a.prior_ledger else []
    result = prepare(read(a.request), read(a.bridge), read(a.lookups), ledger)
    out = Path(a.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("REQUEST VALIDATED OFFLINE: YES")
    print("FIELD COUNT:", len(result["changed_fields"]))
    print("LIVE BEFORE VALUES VERIFIED: FALSE")
    print("SALESFORCE SAVE ALLOWED: FALSE")
    print("PRIVATE PREFLIGHT:", out)


if __name__ == "__main__":
    main()
