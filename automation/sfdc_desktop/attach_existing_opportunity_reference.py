#!/usr/bin/env python3
"""Attach local, read-only UI reference to draft, without cross-namespace ID guesses.

An 18-character Salesforce '006...' record ID must never be compared to the
Novogene business ID 'Opp-YYYY-MM-DD-number' by equality or string prefix.
"""
import argparse
import json
import re
from pathlib import Path

SFDC_RECORD = re.compile(r"006[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?\Z")
VERIFIED = {"VERIFIED_BY_USER_SYSTEM_INFORMATION", "VERIFIED_BUSINESS_ID_MATCH"}
PREFERRED = ("Opportunity Name", "Account Name", "Main Contact", "Amount",
             "Opportunity Currency", "Close Date", "Service Line", "Stage",
             "Forecast Category", "Progress Description", "Status")


def identity_status(draft, snapshot, bridge=None):
    """Only bridge proof can link a Salesforce record to a Catalog business ID."""
    route_id = str(snapshot.get("record_id_from_url") or "").strip()
    if (snapshot.get("source") != "Salesforce visible UI"
            or snapshot.get("record_id_evidence") != "lightning_opportunity_route"
            or snapshot.get("saved_or_modified") is not False
            or not SFDC_RECORD.fullmatch(route_id)):
        return "INVALID_SFDC_ROUTE"
    if not bridge:
        return "BUSINESS_ID_BRIDGE_REQUIRED"
    if (bridge.get("version") != "business-id-bridge-v2"
            or bridge.get("save_allowed") is not False
            or bridge.get("salesforce_save_performed") is not False
            or bridge.get("status") not in VERIFIED):
        return "BRIDGE_NOT_VERIFIED"
    if bridge.get("web_record_id") != route_id:
        return "BRIDGE_RECORD_MISMATCH"
    expected_business = str(draft.get("source_opportunity_id") or "").strip()
    ids = bridge.get("matched_catalog_business_ids")
    if not expected_business or ids != [expected_business]:
        return "BRIDGE_BUSINESS_ID_MISMATCH"
    return "VERIFIED_BUSINESS_ID_BRIDGE"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--draft", required=True)
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--bridge", default="", help="Optional verified v2 bridge; absent means HOLD")
    parser.add_argument("--output", default="")
    args = parser.parse_args()
    draft = json.loads(Path(args.draft).read_text(encoding="utf-8-sig"))
    snapshot = json.loads(Path(args.snapshot).read_text(encoding="utf-8-sig"))
    bridge = json.loads(Path(args.bridge).read_text(encoding="utf-8-sig")) if args.bridge else None
    if draft.get("save_allowed") is not False:
        parser.error("Draft must explicitly prohibit Salesforce Save")
    if snapshot.get("saved_or_modified") is not False or snapshot.get("source") != "Salesforce visible UI":
        parser.error("Snapshot must be a read-only Salesforce UI capture")

    fields = {}
    for frame in snapshot.get("frames", []):
        for item in frame.get("fields", []):
            label = str(item.get("label") or "").strip()
            value = str(item.get("value") or "").strip()
            if label and value:
                fields.setdefault(label, set()).add(value)
    fields = {label: sorted(values) for label, values in fields.items()}
    status = identity_status(draft, snapshot, bridge)
    result = {
        "version": "sfdc-opportunity-reference-v2",
        "source_opportunity_id_from_catalog": draft.get("source_opportunity_id"),
        "source_opportunity_name_from_catalog": draft.get("Existing Opportunity Name (reference only)"),
        "source_page_title": snapshot.get("title"),
        "identity_match": status,
        "salesforce_record_id_from_url": snapshot.get("record_id_from_url"),
        "reference_reuse_allowed": status == "VERIFIED_BUSINESS_ID_BRIDGE",
        "note": "SFDC route ID and business Opp-ID are distinct; a verified bridge is mandatory",
        "fields_from_live_ui": fields,  # Private diagnostic only, never commit
        "missing_preferred_fields": [key for key in PREFERRED if key not in fields],
        "conflicting_field_values": {key: values for key, values in fields.items() if len(values) > 1},
        "new_opportunity_input": {key: draft.get(key, "") for key in PREFERRED if key != "Opportunity Currency"},
        "save_allowed": False,
        "salesforce_save_performed": False,
    }
    target = Path(args.output) if args.output else Path(args.draft).with_name("existing_opportunity_reference.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("REFERENCE IDENTITY:", status)
    print("REFERENCE REUSE ALLOWED:", result["reference_reuse_allowed"])
    print("MISSING PREFERRED FIELD COUNT:", len(result["missing_preferred_fields"]))
    print("REPORT (PRIVATE):", target)
    print("READ ONLY. NO SALESFORCE SAVE.")


if __name__ == "__main__":
    main()
