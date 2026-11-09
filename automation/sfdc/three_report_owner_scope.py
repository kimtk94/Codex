#!/usr/bin/env python3
"""Owner-qualified Quote/Opportunity attribution from QQ-delivered SFDC reports.

Only Opportunity Owner on an exact, unique Opportunity ID can attest the owner
of a Quote. Never infer from Account, contact, customer name, Opportunity name
or an out-of-export/missing Opportunity. All live Salesforce objects unverified.
"""
from collections import Counter, defaultdict

OWNER_NAME = "Kim Taehoon"
VERIFIED_STATE = "QUOTE_OPPORTUNITY_ID_VERIFIED_NOT_REVENUE"


def norm_owner(value):
    return " ".join(str(value or "").strip().casefold().split())


def owner_report_audit(tables, owner=OWNER_NAME):
    from three_report_staged_vs_generated_audit import (
        expected_relation, no_duplicates,
    )
    if not owner or not norm_owner(owner):
        raise ValueError("CSS_OWNER_NAME_INVALID")
    rows = tables["SFDC Email Opportunities Raw"]
    quotes = tables["SFDC Email Quotation Raw"]
    sink_verified = tables["SFDC Verified Relations"]
    sink_review = tables["SFDC Quote Link Review"]

    no_duplicates(rows, "Opportunity ID", "OwnerScopeOpportunity")
    no_duplicates(sink_verified, "Quotation ID", "OwnerScopeVerified")
    no_duplicates(sink_review, "Quotation ID", "OwnerScopeReview")

    opp_by_id = {r["Opportunity ID"]: r for r in rows}
    missing_owner_count = sum(not str(r.get("Opportunity Owner", "")).strip()
                              for r in rows)
    own_opportunities = {
        key for key, row in opp_by_id.items()
        if norm_owner(row.get("Opportunity Owner")) == norm_owner(owner)
    }
    if not own_opportunities:
        raise ValueError("CSS_OWNER_NAME_NOT_IN_SOURCE")
    expected_verified, expected_review, _ = expected_relation(quotes, rows)
    verified = {r["Quotation ID"]: r for r in sink_verified}
    review = {r["Quotation ID"]: r for r in sink_review}
    if set(verified) != set(expected_verified) or set(review) != set(expected_review):
        raise ValueError("CSS_OWNER_SCOPE_NOT_ALLOWED_UNTIL_LINK_PARITY")

    grouped = defaultdict(list)
    for r in quotes:
        grouped[r["SFDC Quotation ID"]].append(r)
    mismatched_owner = 0
    mismatched_stage = 0
    mismatched_active = 0
    mine_quote_ids = set()
    other_quote_ids = set()
    mine_stages = Counter()
    mine_active = Counter()
    mine_linked_opportunities = set()
    mine_source_process_rows = 0
    for qid, reference in expected_verified.items():
        opp_id = reference["opportunity"]
        source_opp = opp_by_id[opp_id]
        got = verified[qid]
        source_owner = str(source_opp.get("Opportunity Owner", "")).strip()
        sink_owner = str(got.get("Opportunity Owner", "")).strip()
        source_stage = str(source_opp.get("Stage", "")).strip()
        sink_stage = str(got.get("Opportunity Stage", "")).strip()
        if norm_owner(source_owner) != norm_owner(sink_owner):
            mismatched_owner += 1
        if source_stage != sink_stage:
            mismatched_stage += 1
        active_values = {str(r.get("Active", "")).strip().upper()
                         for r in grouped[qid] if str(r.get("Active", "")).strip()}
        active = next(iter(active_values)) if len(active_values) == 1 else "MIXED_OR_UNKNOWN"
        if active != str(got.get("Quote Active (report only)", "")).strip():
            mismatched_active += 1
        if norm_owner(source_owner) == norm_owner(owner):
            mine_quote_ids.add(qid)
            mine_stages[source_stage or "UNSPECIFIED"] += 1
            mine_active[active] += 1
            mine_source_process_rows += len(grouped[qid])
            mine_linked_opportunities.add(opp_id)
        else:
            other_quote_ids.add(qid)

    if mine_quote_ids & other_quote_ids:
        raise ValueError("CSS_OWNER_SCOPE_OVERLAPPING_QUOTE_IDS")
    covered = len(mine_quote_ids) + len(other_quote_ids) + len(expected_review)
    if covered != len(grouped):
        raise ValueError("CSS_OWNER_SCOPE_QUOTE_UNACCOUNTED")

    # All review Quote IDs remain unattributed. A missing/out-of-export
    # Opportunity can belong to anyone; never count it as the user's deal.
    state = ("PASS_REPORT_OWNER_TO_SINK_ONLY"
             if not (missing_owner_count or mismatched_owner or mismatched_stage
                     or mismatched_active)
             else "BLOCK_OWNER_SOURCE_OR_SINK_MISMATCH")
    return {
        "owner_report_label": owner,
        "source_opportunities_total": len(rows),
        "owner_opportunities": len(own_opportunities),
        "other_opportunities": len(rows) - len(own_opportunities),
        "owner_opportunities_missing_owner_field": missing_owner_count,
        "source_quote_ids_total": len(grouped),
        "verified_link_quote_ids": len(expected_verified),
        "review_unattributable_quote_ids": len(expected_review),
        "owner_verified_quote_ids": len(mine_quote_ids),
        "other_verified_quote_ids": len(other_quote_ids),
        "owner_distinct_opportunities_with_verified_quotes": len(mine_linked_opportunities),
        "owner_opportunities_without_verified_quotes": len(own_opportunities - mine_linked_opportunities),
        "owner_verified_quote_process_rows": mine_source_process_rows,
        "owner_quote_stage_counts": dict(sorted(mine_stages.items())),
        "owner_quote_report_active_counts": dict(sorted(mine_active.items())),
        "owner_field_readback_mismatches": mismatched_owner,
        "stage_field_readback_mismatches": mismatched_stage,
        "active_field_readback_mismatches": mismatched_active,
        "scope_status": state,
        "review_quote_owner_assignment": "NOT_PERMITTED_WITHOUT_EXACT_OPPORTUNITY_OWNER",
        "salesforce_saved_object_state": "NOT_CHECKED",
        "sfdc_owner_attribute_is_report_snapshot": True,
        "any_salesforce_write": False,
    }
