#!/usr/bin/env python3
"""Safe reconciliation policy for previously submitted CRM saves.

This pure function accepts only booleans and counts. No private records, CRM
access, or writes. Missing/ambiguous post-save readback is never permission to
retry a Quote or Opportunity create operation.
"""


def reconcile_existing_save(evidence):
    if not isinstance(evidence, dict) or set(evidence) != {
        "opportunity_save_clicked", "opportunity_native_id_verified",
        "quote_save_clicked", "quote_native_id_verified",
        "quote_parent_link_verified", "matching_related_quote_count",
        "duplicate_search_complete"
    }:
        return {"status": "HOLD_INCOMPLETE_EVIDENCE", "create_allowed": False}
    for field in (
        "opportunity_save_clicked", "opportunity_native_id_verified",
        "quote_save_clicked", "quote_native_id_verified",
        "quote_parent_link_verified", "duplicate_search_complete"
    ):
        if type(evidence[field]) is not bool:
            return {"status": "HOLD_INVALID_EVIDENCE", "create_allowed": False}
    count = evidence["matching_related_quote_count"]
    if count is not None and (type(count) is not int or count < 0):
        return {"status": "HOLD_INVALID_EVIDENCE", "create_allowed": False}
    if not evidence["duplicate_search_complete"]:
        return {"status": "HOLD_DUPLICATE_SEARCH_REQUIRED", "create_allowed": False}
    if evidence["opportunity_save_clicked"] and not evidence["opportunity_native_id_verified"]:
        return {"status": "HOLD_OPPORTUNITY_SAVE_READBACK", "create_allowed": False}
    if evidence["quote_save_clicked"] and not evidence["quote_native_id_verified"]:
        return {"status": "HOLD_QUOTE_SAVE_READBACK_NEVER_RETRY", "create_allowed": False}
    if count is None:
        return {"status": "HOLD_RELATED_LIST_UNREADABLE", "create_allowed": False}
    if count > 1:
        return {"status": "HOLD_DUPLICATE_QUOTES", "create_allowed": False}
    if count == 1 and not evidence["quote_parent_link_verified"]:
        return {"status": "HOLD_QUOTE_PARENT_LINK_MISMATCH", "create_allowed": False}
    if count == 1 and evidence["quote_native_id_verified"] and evidence["quote_parent_link_verified"]:
        return {"status": "EXISTING_QUOTE_VERIFIED_NO_CREATE", "create_allowed": False}
    return {"status": "HOLD_MANUAL_REVIEW_BEFORE_CREATE", "create_allowed": False}
