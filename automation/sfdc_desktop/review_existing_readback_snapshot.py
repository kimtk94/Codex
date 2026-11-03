#!/usr/bin/env python3
"""Offline review of a fresh Salesforce Opportunity snapshot after external Save.

NO Salesforce browser / API access, no Save. The input snapshot is locally
captured read-only UI data, NOT cryptographic proof that any Save occurred.
Requires a separately reviewed request, explicit Save authorization, and a
versioned ledger entry recording that an external Save was reported/uncertain.
Can only return CONTENT_MATCH_REVIEW_REQUIRED, never VERIFIED or save_allowed.
"""
import argparse
import json
from datetime import datetime
from pathlib import Path

from capture_existing_opportunity_snapshot import validate_snapshot
from make_existing_change_template import FIELDS
from prepare_existing_change_review import prepare
from related_quotation_bridge import same_record
from save_readback_contract import validate_ledger

ELIGIBLE_STATES = frozenset({"READBACK_REQUIRED", "WRITE_OUTCOME_UNKNOWN"})


def _hold(status):
    return {
        "version": "sfdc-existing-readback-review-v1",
        "status": status,
        "readback_fields_match": False,
        "save_confirmed": False,
        "human_review_required": True,
        "save_allowed": False,
        "salesforce_save_performed_by_review": False,
    }


def _aware_time(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo and parsed.utcoffset() is not None else None


def compare(request, bridge, links, ledger, approval, snapshot):
    """Pure strict comparison. No review result ever certifies Save completion."""
    if (not isinstance(request, dict) or request.get("reviewed_current_deal_values") is not True
            or not isinstance(request.get("changes"), dict) or not request["changes"]):
        return _hold("HOLD_CHANGE_REVIEW_MISSING")
    if not set(request["changes"]).issubset(FIELDS):
        return _hold("HOLD_UNSUPPORTED_SALESFORCE_FIELDS")
    # validate_ledger and prepare throw on corrupt/missing source rather than infer data.
    rows = validate_ledger(ledger)
    preflight = prepare(request, bridge, links)
    uid = preflight["request_uid"]
    finger = preflight["operation_fingerprint"]
    intent = preflight["change_intent_fingerprint"]

    matching = [e for e in rows if e["request_uid"] == uid]
    if len(matching) != 1:
        return _hold("HOLD_NO_PRIOR_RECORDED_OPERATION")
    row = matching[0]
    if (row["operation_fingerprint"] != finger
            or row["change_intent_fingerprint"] != intent):
        return _hold("HOLD_LEDGER_IDENTITY_MISMATCH")
    if row["state"] not in ELIGIBLE_STATES:
        return _hold("HOLD_NO_EXTERNAL_SAVE_EVENT")
    if (not isinstance(approval, dict)
            or approval.get("approved_action") != "SAVE_EXISTING_OPPORTUNITY"
            or approval.get("request_uid") != uid
            or approval.get("operation_fingerprint") != finger
            or approval.get("approved_for_record") != preflight["target_record_id"]
            or approval.get("explicit_current_deal_approval") is not True):
        return _hold("HOLD_EXPLICIT_SAVE_APPROVAL_MISSING")
    if not isinstance(snapshot, dict) or not snapshot:
        return _hold("HOLD_FRESH_UI_SNAPSHOT_MISSING")
    validate_snapshot(snapshot)
    # Snapshot has no Save attestation by construction; it is only a content check.
    observed_at = _aware_time(snapshot.get("captured_at_utc"))
    save_recorded_at = _aware_time(row.get("updated_utc"))
    if observed_at is None or save_recorded_at is None or observed_at <= save_recorded_at:
        return _hold("HOLD_SNAPSHOT_PRECEDES_RECORDED_EXTERNAL_ACTION")
    if (not same_record(snapshot["opportunity_record_id"], preflight["target_record_id"])
            or snapshot["business_id_from_prior_report"] != request["business_opportunity_id"]
            or not same_record(snapshot["account_record_id"], request["expected_account_record_id"])
            or not same_record(snapshot["contact_record_id"], request["expected_contact_record_id"])):
        return _hold("HOLD_RELOADED_RECORD_OR_LOOKUP_ID_MISMATCH")
    # Compare only reviewed changed fields. Unreviewed incidental fields are not
    # automatically inherited into or submitted as deal updates.
    current = snapshot["current_field_values"]
    for field, proposed in request["changes"].items():
        if current[field] != proposed:
            return _hold("HOLD_RELOADED_CHANGE_VALUE_DIFFERENT")
    return {
        "version": "sfdc-existing-readback-review-v1",
        "status": "READBACK_CONTENT_MATCH_REVIEW_REQUIRED",
        "matched_field_names": sorted(request["changes"]),
        "matched_field_count": len(request["changes"]),
        "record_and_link_ids_match": True,
        "readback_fields_match": True,
        "save_confirmed": False,  # No claim of completed Salesforce transaction.
        "human_review_required": True,
        "save_allowed": False,
        "salesforce_save_performed_by_review": False,
    }


def main():
    p = argparse.ArgumentParser()
    root = Path.home() / ".sfdc_desktop"
    p.add_argument("--request", default=str(root / "existing_change_review_TEMPLATE_PRIVATE.json"))
    p.add_argument("--bridge", default=str(root / "verified_live_quotation_report_bridge.json"))
    p.add_argument("--links", default=str(root / "existing_lookup_record_ids_private.json"))
    p.add_argument("--ledger", default=str(root / "operation_ledger_private.json"))
    p.add_argument("--approval", default=str(root / "external_save_approval_PRIVATE.json"))
    p.add_argument("--snapshot", default=str(root / "opportunity_reloaded_snapshot_PRIVATE.json"))
    p.add_argument("--output", default=str(root / "readback_review_PRIVATE.json"))
    args = p.parse_args()
    def read(path):
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    request = read(args.request)
    # An unreviewed change request must not require or invent Save approval.
    if (request.get("reviewed_current_deal_values") is not True
            or not request.get("changes")):
        result = _hold("HOLD_CHANGE_REVIEW_MISSING")
    else:
        result = compare(
            request, read(args.bridge), read(args.links), read(args.ledger),
            read(args.approval), read(args.snapshot))
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        p.error("Prior private result exists; choose new --output")
    with target.open("x", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print("READBACK CONTENT STATUS:", result["status"])
    print("SAVE CONFIRMED: FALSE")
    print("SAVE ALLOWED: FALSE")
    print("PRIVATE REVIEW OUTPUT:", target)


if __name__ == "__main__":
    main()
