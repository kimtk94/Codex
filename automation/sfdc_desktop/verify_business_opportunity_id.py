#!/usr/bin/env python3
"""Read-only bridge of an actual Salesforce 006 record to a Novogene Opp-* business ID.

Never equate these distinct identifier namespaces, infer from Opportunity names,
or certify a candidate based only on nearby text.
"""
import argparse
import json
import re
from pathlib import Path

BUSINESS_ID = re.compile(r"Opp-\d{4}-\d{2}-\d{2}-\d+\Z")
SFDC_OPPORTUNITY_ID = re.compile(r"006[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?\Z")
EXACT_LABELS = {"opportunity id", "opportunity number"}


def verify(snapshot, matches, observed_business_id=""):
    """Pure, fail-closed evidence verifier; no network calls or Salesforce writes."""
    route_id = str(snapshot.get("record_id_from_url") or "").strip()
    if (snapshot.get("source") != "Salesforce visible UI"
            or snapshot.get("saved_or_modified") is not False
            or snapshot.get("record_id_evidence") != "lightning_opportunity_route"
            or not SFDC_OPPORTUNITY_ID.fullmatch(route_id)):
        raise ValueError("Verified, read-only Salesforce Opportunity route is required")
    if not isinstance(matches, list):
        raise ValueError("Catalog matches must be a list")
    observed_business_id = observed_business_id.strip()
    if observed_business_id and not BUSINESS_ID.fullmatch(observed_business_id):
        raise ValueError("Observed business ID must use exact Opp-YYYY-MM-DD-number format")

    evidence = []
    for frame in snapshot.get("frames", []):
        for item in frame.get("fields", []):
            label = str(item.get("label") or "").strip()
            if label.casefold() not in EXACT_LABELS:
                continue  # An ID in Opportunity Name or unrelated text is not evidence.
            value = str(item.get("value") or "").strip()
            if BUSINESS_ID.fullmatch(value):
                evidence.append({"business_id": value, "source": "labeled_field",
                                 "label": label, "trust": "DIRECT"})
        for item in frame.get("business_id_candidates", []):
            candidate = str(item.get("id") or "").strip()
            if BUSINESS_ID.fullmatch(candidate):
                evidence.append({"business_id": candidate, "source": "nearby_label_candidate",
                                 "label": "Opportunity ID nearby", "trust": "CANDIDATE"})
    if observed_business_id:
        evidence.append({"business_id": observed_business_id,
                         "source": "user_confirmed_visible_system_information",
                         "label": "System Information > Opportunity ID", "trust": "DIRECT"})

    ids = sorted({entry["business_id"] for entry in evidence})
    direct_ids = {entry["business_id"] for entry in evidence if entry["trust"] == "DIRECT"}
    selected = [row for row in matches if isinstance(row, dict)
                and str(row.get("opportunity_id") or "").strip() in ids]
    if len(ids) > 1:
        status = "CONFLICTING_BUSINESS_IDS"
    elif not ids:
        status = "BUSINESS_ID_NOT_FOUND_OR_NOT_UNIQUE"
    elif len(selected) > 1:
        status = "DUPLICATE_CATALOG_BUSINESS_ID"
    elif not selected:
        status = "BUSINESS_ID_NOT_IN_CATALOG"
    elif ids[0] not in direct_ids:
        status = "CANDIDATE_MATCH_NEEDS_REVIEW"
    elif any(item["source"] == "user_confirmed_visible_system_information" for item in evidence):
        status = "VERIFIED_BY_USER_SYSTEM_INFORMATION"
    else:
        status = "VERIFIED_BUSINESS_ID_MATCH"
    trusted = status in {"VERIFIED_BY_USER_SYSTEM_INFORMATION", "VERIFIED_BUSINESS_ID_MATCH"}
    return {
        "version": "business-id-bridge-v2",
        "web_record_id": route_id,
        "record_id_evidence": "lightning_opportunity_route",
        "business_id_evidence": evidence,
        "status": status,
        "matched_catalog_business_ids": [selected[0]["opportunity_id"]] if trusted else [],
        "save_allowed": False,
        "salesforce_save_performed": False,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--matches", required=True)
    parser.add_argument("--output", default="")
    parser.add_argument("--observed-business-id", default="",
                        help="Only when manually confirmed in this record's System Information")
    args = parser.parse_args()
    snap = json.loads(Path(args.snapshot).read_text(encoding="utf-8-sig"))
    rows = json.loads(Path(args.matches).read_text(encoding="utf-8-sig")).get("matches", [])
    try:
        result = verify(snap, rows, args.observed_business_id)
    except ValueError as exc:
        parser.error(str(exc))
    dest = Path(args.output) if args.output else Path(args.snapshot).with_name("business_id_bridge.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    # Never publish business IDs, customer fields, or exact Salesforce record IDs to CI logs.
    print("MAPPING STATUS:", result["status"])
    print("DIRECT EVIDENCE:", sum(e["trust"] == "DIRECT" for e in result["business_id_evidence"]))
    print("CATALOG UNIQUE MATCH:", len(result["matched_catalog_business_ids"]) == 1)
    print("REPORT (PRIVATE):", dest)
    print("SALESFORCE SAVE: DISABLED")


if __name__ == "__main__":
    main()
