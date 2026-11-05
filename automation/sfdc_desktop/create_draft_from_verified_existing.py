#!/usr/bin/env python3
"""Create an unsaved draft only from a v2 verified business-ID / SFDC route bridge."""
import argparse
import json
from pathlib import Path

from verify_business_opportunity_id import SFDC_OPPORTUNITY_ID

VERIFIED = {"VERIFIED_BY_USER_SYSTEM_INFORMATION", "VERIFIED_BUSINESS_ID_MATCH"}
FIELDS = ("Opportunity Name", "Account Name", "Main Contact", "Amount",
          "Opportunity Currency", "Close Date", "Service Line", "Stage",
          "Forecast Category", "Progress Description", "Status")


def select_verified_source(bridge, snap, matches):
    """Fail-closed: old v1 bridge and arbitrary catalog matches are never sufficient."""
    route_id = str(snap.get("record_id_from_url") or "").strip()
    if (snap.get("source") != "Salesforce visible UI"
            or snap.get("saved_or_modified") is not False
            or snap.get("record_id_evidence") != "lightning_opportunity_route"
            or not SFDC_OPPORTUNITY_ID.fullmatch(route_id)):
        raise ValueError("Verified read-only Salesforce Opportunity route required")
    if (bridge.get("version") != "business-id-bridge-v2"
            or bridge.get("record_id_evidence") != "lightning_opportunity_route"
            or bridge.get("status") not in VERIFIED
            or bridge.get("save_allowed") is not False
            or bridge.get("salesforce_save_performed") is not False):
        raise ValueError("Verified v2 business-ID bridge required")
    if bridge.get("web_record_id") != route_id:
        raise ValueError("Bridge and UI Salesforce 006 IDs differ")
    ids = bridge.get("matched_catalog_business_ids")
    if not isinstance(ids, list) or len(ids) != 1:
        raise ValueError("Exactly one verified business-ID catalog match required")
    if not isinstance(matches, list):
        raise ValueError("Catalog must be a list")
    selected = [row for row in matches if isinstance(row, dict)
                and str(row.get("opportunity_id") or "") == ids[0]]
    if len(selected) != 1:
        raise ValueError("Catalog has missing or duplicate business ID")
    return selected[0]


def build_draft(bridge, snap, matches):
    row = select_verified_source(bridge, snap, matches)
    actual = {}
    for frame in snap.get("frames", []):
        for item in frame.get("fields", []):
            label = str(item.get("label") or "").strip()
            value = str(item.get("value") or "").strip()
            if label in FIELDS and value:
                actual.setdefault(label, set()).add(value)
    reference = {k: next(iter(v)) for k, v in actual.items() if len(v) == 1}
    # All deal-specific fields remain blank until separately reviewed.
    draft = {key: "" for key in FIELDS if key != "Opportunity Currency"}
    draft.update({
        "Account Name": str(row.get("account") or ""),
        "Main Contact": str(row.get("contact") or ""),
        "source_opportunity_id": row["opportunity_id"],
        "source_salesforce_record_id": snap.get("record_id_from_url"),
        "existing_opportunity_reference": reference,  # local private file only
        "existing_catalog_reference": row,
        "lookup_verified": False,
        "review_required": True,
        "save_allowed": False,
        "salesforce_save_performed": False,
    })
    return draft


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--bridge", required=True)
    p.add_argument("--matches", required=True)
    p.add_argument("--snapshot", required=True)
    p.add_argument("--output", default="")
    a = p.parse_args()
    bridge = json.loads(Path(a.bridge).read_text(encoding="utf-8-sig"))
    rows = json.loads(Path(a.matches).read_text(encoding="utf-8-sig")).get("matches", [])
    snap = json.loads(Path(a.snapshot).read_text(encoding="utf-8-sig"))
    try:
        draft = build_draft(bridge, snap, rows)
    except ValueError as exc:
        p.error(str(exc))
    target = Path(a.output) if a.output else Path(a.bridge).with_name("verified_existing_to_new_draft.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(draft, ensure_ascii=False, indent=2), encoding="utf-8")
    print("VERIFIED IDENTITY AND CATALOG MATCH: PASS")
    print("CURRENT DEAL AMOUNT / DATE / STAGE: NOT APPROVED")
    print("LOOKUP VERIFIED: FALSE")
    print("REPORT (PRIVATE):", target)
    print("No Salesforce changes; Save forbidden.")


if __name__ == "__main__":
    main()
