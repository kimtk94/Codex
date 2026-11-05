#!/usr/bin/env python3
"""Safety contracts for a NEW Research-AMEA Salesforce Quotation.

Pure local validators; they never call Salesforce or press Save. The quote's
parent is a native 006 Opportunity record ID verified on BOTH the original
Opportunity Related list and the Quotation record after a separately approved
external Save. A business 'Opp-...' number or matching display name is not
sufficient as parent linkage.
"""
import hashlib
import json
import re
from datetime import date

from related_quotation_bridge import SF_RECORD, QUOTE_RECORD, BUSINESS, QID, same_record

RECORD_TYPE = "Research-AMEA"
REQUIRED_QUOTE_FIELDS = frozenset({
    "Quotation Name", "Business Entity", "Promotion Type", "Valid Thru"
})
REQUIRED_UI_PICKLISTS = frozenset({"Business Entity", "Promotion Type", "Valid Thru"})
REQUEST_UID = re.compile(r"REQ-[A-Za-z0-9_-]{8,64}\Z")
SAFE_QUOTE_NAME = re.compile(r"[\w\s()&,.+\-/:]{1,255}\Z", re.UNICODE)


def validate_quote_form(form):
    """Form presence is NOT create authorization. Default parent name must match."""
    if not isinstance(form, dict):
        raise ValueError("Quotation form evidence is required")
    required = (
        form.get("screen") == "New Quotation: Research-AMEA"
        and form.get("record_type") == RECORD_TYPE
        and form.get("record_type_selected_explicitly") is True
        and form.get("form_opened_from_exact_opportunity_related") is True
        and form.get("unique_quotation_name_textbox") is True
        and form.get("unique_cancel_button") is True
        and form.get("opportunity_selected") is True
        and form.get("opportunity_lookup_readonly") is True
        and form.get("opportunity_name_matches_verified_parent") is True
        and form.get("save_clicked") is False
    )
    if not required:
        raise ValueError("Quote create form parent, record type or Cancel unverified")
    controls = form.get("required_picklist_controls")
    if not isinstance(controls, dict) or set(controls) != REQUIRED_UI_PICKLISTS:
        raise ValueError("Exact required picklists not fully audited")
    for field in REQUIRED_UI_PICKLISTS:
        row = controls[field]
        if not isinstance(row, dict) or (row.get("count") != 1
                or row.get("aria_required") is not True
                or row.get("enabled") is not True):
            raise ValueError("Missing/ambiguous required Quote picklist: " + field)
    return True


def prepare_quote_request(request, parent=None):
    """Validate a proposed Quote without guessing enum values or creating a record.

    Quote request values must be entered/reviewed by the user; never derive
    Business Entity, Promotion Type or price from an old quotation.
    """
    if not isinstance(request, dict) or not isinstance(parent, dict):
        raise ValueError("Explicit quote request and parent evidence required")
    uid = str(request.get("request_uid") or "")
    if not REQUEST_UID.fullmatch(uid):
        raise ValueError("Stable request UID required")
    if request.get("record_type") != RECORD_TYPE:
        raise ValueError("Only audited Research-AMEA Quote type supported")
    if request.get("reviewed_current_quote_values") is not True:
        raise ValueError("Current Quote field values must be explicitly reviewed")
    if request.get("save_allowed") is not False:
        raise ValueError("Quote creation Save must remain prohibited in this stage")
    if (not SF_RECORD.fullmatch(str(parent.get("opportunity_record_id") or ""))
            or not BUSINESS.fullmatch(str(parent.get("business_opportunity_id") or ""))
            or parent.get("parent_verified_from_salesforce_ui") is not True):
        raise ValueError("Verified native+business Opportunity parent required")
    if (not same_record(request.get("parent_opportunity_record_id"),
                        parent.get("opportunity_record_id"))
            or request.get("parent_business_opportunity_id") != parent["business_opportunity_id"]):
        raise ValueError("Quote parent native/business ID mismatch")
    values = request.get("values")
    if not isinstance(values, dict) or set(values) != REQUIRED_QUOTE_FIELDS:
        raise ValueError("Four explicit required Quote values are needed")
    for key, value in values.items():
        if not isinstance(value, str) or not value.strip() or value != value.strip():
            raise ValueError("Quote field empty/unreviewed: " + key)
        if len(value) > 255:
            raise ValueError("Quote field exceeds safe text limit")
    if not SAFE_QUOTE_NAME.fullmatch(values["Quotation Name"]):
        raise ValueError("Quote name contains unsafe/unsupported text")
    # A Valid Thru UI picklist may contain non-date values; do not guess or
    # normalize Salesforce-controlled dropdown option labels.
    canonical = json.dumps({
        "parent": parent["opportunity_record_id"], "record_type": RECORD_TYPE,
        "values": values
    }, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return {
        "version": "sfdc-quotation-create-preflight-v1",
        "status": "QUOTE_REVIEWED_NOT_SAVED",
        "request_uid": uid,
        "parent_opportunity_record_id": parent["opportunity_record_id"],
        "parent_business_opportunity_id": parent["business_opportunity_id"],
        "quote_intent_fingerprint": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "save_allowed": False,
        "salesforce_quote_created": False,
    }


def compare_created_quotation(expected_parent, created):
    """Only checks supplied readback evidence; never claims real Save was seen."""
    if not isinstance(expected_parent, dict) or not isinstance(created, dict):
        return "HOLD_CREATE_READBACK_MISSING"
    if (expected_parent.get("parent_verified_from_salesforce_ui") is not True
            or not SF_RECORD.fullmatch(str(expected_parent.get("opportunity_record_id") or ""))
            or not BUSINESS.fullmatch(str(expected_parent.get("business_opportunity_id") or ""))):
        return "HOLD_PARENT_IDENTITY_INVALID"
    if (not QUOTE_RECORD.fullmatch(str(created.get("quotation_record_id") or ""))
            or not QID.fullmatch(str(created.get("qid") or ""))):
        return "HOLD_QUOTE_IDENTITY_MISSING"
    if not (same_record(created.get("parent_opportunity_record_id"),
                        expected_parent["opportunity_record_id"])
            and same_record(created.get("related_list_quotation_record_id"),
                            created["quotation_record_id"])
            and same_record(created.get("quotation_detail_record_id"),
                            created["quotation_record_id"])):
        return "HOLD_PARENT_OR_RELATED_LINK_MISMATCH"
    if (created.get("quotation_record_type") != RECORD_TYPE
            or created.get("parent_business_opportunity_id")
               != expected_parent["business_opportunity_id"]):
        return "HOLD_RECORD_TYPE_OR_BUSINESS_ID_MISMATCH"
    if created.get("related_list_matching_link_count") != 1:
        return "HOLD_DUPLICATE_OR_AMBIGUOUS_RELATED_LINK"
    return "QUOTE_LINK_CONTENT_MATCHES_MANUAL_REVIEW_REQUIRED"


if __name__ == "__main__":
    print("Pure Quotation creation contracts; no Salesforce Save.")
