#!/usr/bin/env python3
"""Offline contracts for future Salesforce Save approval, ledger and readback.

This module has NO Playwright, Salesforce I/O, or Save action. All results keep
save_allowed=False. A review result never authorizes an automated CRM write.
"""
import re

from related_quotation_bridge import SF_RECORD, BUSINESS, same_record
from capture_existing_lookup_links import ACCOUNT, CONTACT

VALID_STATES = {
    "PREPARED", "PENDING_WRITE", "WRITE_OUTCOME_UNKNOWN",
    "READBACK_REQUIRED", "VERIFIED", "FAILED", "HOLD", "CANCELLED",
}


def validate_ledger(ledger):
    """Fail closed for absent/corrupt history, repeated UID or fingerprint."""
    if not isinstance(ledger, dict) or ledger.get("version") != "sfdc-local-operation-ledger-v1":
        raise ValueError("Versioned private operation ledger required")
    entries = ledger.get("entries")
    if not isinstance(entries, list):
        raise ValueError("Operation ledger must have an entries list")
    seen_uid, seen_hash = set(), set()
    for record in entries:
        if not isinstance(record, dict):
            raise ValueError("Malformed ledger entry")
        uid = str(record.get("request_uid") or "")
        finger = str(record.get("operation_fingerprint") or "")
        if (not uid.startswith("REQ-") or not re.fullmatch(r"[a-f0-9]{64}", finger)
                or record.get("state") not in VALID_STATES
                or uid in seen_uid or finger in seen_hash):
            raise ValueError("Corrupt, duplicated or unknown-state operation ledger")
        seen_uid.add(uid)
        seen_hash.add(finger)
    return entries


def review_save_contract(preflight, live, approval, ledger):
    """Never outputs save_allowed=True, even with valid human approval fields."""
    entries = validate_ledger(ledger)
    hold = lambda status: {
        "version": "sfdc-save-review-contract-v1",
        "status": status, "save_allowed": False,
        "salesforce_save_performed": False,
    }
    if not isinstance(preflight, dict) or not isinstance(live, dict):
        return hold("HOLD_MISSING_PREFLIGHT")
    if (preflight.get("status") != "PREPARED_FOR_LIVE_BEFORE_VALUE_CHECK"
            or preflight.get("save_allowed") is not False
            or live.get("status") != "VERIFIED_LIVE_BEFORE_VALUES"
            or live.get("live_before_values_verified") is not True
            or live.get("fill_allowed") is not False
            or live.get("values_filled") is not False
            or live.get("salesforce_save_allowed") is not False
            or live.get("salesforce_save_performed") is not False
            or preflight.get("operation_fingerprint") != live.get("operation_fingerprint")):
        return hold("HOLD_PREFLIGHT_OR_LIVE_EVIDENCE")
    uid = str(preflight.get("request_uid") or "")
    finger = str(preflight.get("operation_fingerprint") or "")
    record = str(preflight.get("target_record_id") or "")
    if (not uid.startswith("REQ-") or not re.fullmatch(r"[a-f0-9]{64}", finger)
            or not SF_RECORD.fullmatch(record)):
        return hold("HOLD_INVALID_OPERATION_IDENTITY")
    if any(e["request_uid"] == uid or e["operation_fingerprint"] == finger for e in entries):
        return hold("HOLD_DUPLICATE_OR_IN_FLIGHT_OPERATION")
    if (not isinstance(approval, dict)
            or approval.get("approved_action") != "SAVE_EXISTING_OPPORTUNITY"
            or approval.get("request_uid") != uid
            or approval.get("operation_fingerprint") != finger
            or approval.get("approved_for_record") != record
            or approval.get("explicit_current_deal_approval") is not True):
        return hold("HOLD_EXPLICIT_SAVE_APPROVAL_REQUIRED")
    # A separate yet-to-be-authorized execution pathway must still establish
    # duplicate record checks, lock ownership and exact post-fill readback.
    return hold("READY_FOR_SEPARATE_MANUAL_SAVE_REVIEW_NOT_EXECUTION")


def evaluate_post_save_readback(approved, refreshed):
    """Strict post-save evidence comparison. No write here and no IO implied."""
    if not isinstance(approved, dict) or not isinstance(refreshed, dict):
        return "HOLD_READBACK_EVIDENCE_MISSING"
    if (refreshed.get("source") != "Salesforce UI after explicit Save and page reload"
            or refreshed.get("reloaded_after_save") is not True
            or refreshed.get("record_url_reopened") is not True
            or refreshed.get("unique_target_page") is not True):
        return "HOLD_READBACK_NOT_RELOADED"
    for key, regex in (
        ("opportunity_record_id", SF_RECORD),
        ("account_record_id", ACCOUNT),
        ("contact_record_id", CONTACT),
        ("business_opportunity_id", BUSINESS),
    ):
        known, now = approved.get(key), refreshed.get(key)
        if not isinstance(known, str) or not regex.fullmatch(known):
            return "HOLD_READBACK_IDENTITY_INVALID"
        if not isinstance(now, str) or not regex.fullmatch(now):
            return "HOLD_READBACK_IDENTITY_INVALID"
        if key == "business_opportunity_id":
            if known != now:
                return "HOLD_READBACK_IDENTITY_CHANGED"
        elif not same_record(known, now):
            return "HOLD_READBACK_IDENTITY_CHANGED"
    expected = approved.get("changes")
    actual = refreshed.get("changed_field_values")
    if not isinstance(expected, dict) or not expected:
        return "HOLD_READBACK_CHANGED_VALUES_MISSING"
    if not isinstance(actual, dict) or set(actual) != set(expected):
        return "HOLD_READBACK_CHANGED_FIELD_SET_MISMATCH"
    if any(actual[k] != value for k, value in expected.items()):
        return "HOLD_READBACK_CHANGED_VALUES_DIFFER"
    return "READBACK_FIELDS_AND_LINKS_MATCH_REVIEW_REQUIRED"


if __name__ == "__main__":
    print("Pure offline contract. No Salesforce Save API or UI action.")
