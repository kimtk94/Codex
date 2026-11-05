#!/usr/bin/env python3
"""Validate a private browser-downloaded Oppo/Quote draft, with zero SFDC writes."""
import argparse
import json
import math
from pathlib import Path

ALLOWED_MODES = {"PE250", "PE150", "PE100", "SE100", "SE50"}
REQUIRED_CHECKS = {
    "exact_contact_email_identity",
    "account_record_id_and_contact_lookup",
    "existing_opportunity_and_quotation_duplicates",
    "approved_opportunity_name_amount_stage_close_date",
    "current_business_entity_promotion_type_valid_thru",
    "verified_price_and_quote_lines",
    "post_creation_native_006_parent_and_a0P_quote_links",
}


def inspect_web_draft(payload):
    if not isinstance(payload, dict):
        raise ValueError("DRAFT_MUST_BE_OBJECT")
    if set(payload) != {"version", "status", "request", "summary", "required_checks",
                        "salesforce_save_allowed", "opportunity_created", "quotation_created"}:
        raise ValueError("DRAFT_SCHEMA_MISMATCH")
    if payload["version"] != "oppo-quote-pmp-web-draft-v1":
        raise ValueError("DRAFT_VERSION_MISMATCH")
    if payload["status"] != "HOLD_CONTACT_ACCOUNT_QUOTE_REVIEW":
        raise ValueError("DRAFT_REVIEW_GATE_INVALID")
    for key in ("salesforce_save_allowed", "opportunity_created", "quotation_created"):
        if payload[key] is not False:
            raise ValueError("DRAFT_WRITE_GATE_INVALID")
    if not isinstance(payload["required_checks"], list) or set(payload["required_checks"]) != REQUIRED_CHECKS or len(payload["required_checks"]) != len(REQUIRED_CHECKS):
        raise ValueError("DRAFT_CHECKLIST_INVALID")
    req = payload["request"]
    if not isinstance(req, dict) or set(req) != {
        "contact_email", "service", "sequencing_mode", "sample_count",
        "depth_per_sample", "depth_unit"}:
        raise ValueError("REQUEST_SCHEMA_MISMATCH")
    if req["service"] != "PMP" or req["sequencing_mode"] not in ALLOWED_MODES:
        raise ValueError("SERVICE_OR_MODE_UNSUPPORTED")
    from oppo_quote_case_learning import validate_request_draft
    normalized = validate_request_draft(req)
    if normalized["sequencing_mode"] != req["sequencing_mode"]:
        raise ValueError("NONCANONICAL_MODE")
    summary = payload["summary"]
    if not isinstance(summary, dict) or set(summary) != {
        "nominal_total_depth", "depth_unit", "reads_basis"}:
        raise ValueError("SUMMARY_SCHEMA_MISMATCH")
    expected = normalized["total_nominal_depth"]
    actual = summary["nominal_total_depth"]
    if type(actual) not in (int, float) or not math.isfinite(actual) or not math.isclose(actual, expected, rel_tol=1e-12):
        raise ValueError("TOTAL_DEPTH_MISMATCH")
    if summary["depth_unit"] != normalized["depth_unit"] or summary["reads_basis"] != "UNSPECIFIED_WHETHER_READS_OR_READ_PAIRS":
        raise ValueError("DEPTH_UNITS_OR_BASIS_MISMATCH")
    return {"status": "LOCAL_DRAFT_VALIDATED_NO_SAVE",
            "service": "PMP", "mode":req["sequencing_mode"],
            "sample_count":req["sample_count"],
            "unit":req["depth_unit"],
            "required_live_checks":len(REQUIRED_CHECKS),
            "contact_identity_verified":False, "account_identity_verified":False,
            "quote_price_verified":False, "save_allowed":False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--draft", required=True)
    args = parser.parse_args()
    path = Path(args.draft)
    if path.stat().st_size > 250_000:
        raise SystemExit("HOLD_DRAFT_TOO_LARGE")
    try:
        result=inspect_web_draft(json.loads(path.read_text(encoding="utf-8-sig")))
        # Never print customer name/email or Salesforce identifiers to CI logs.
        print(json.dumps(result,ensure_ascii=False,sort_keys=True))
    except (ValueError,TypeError,KeyError,ImportError,json.JSONDecodeError) as exc:
        raise SystemExit("HOLD_INVALID_DRAFT:" + type(exc).__name__)


if __name__ == "__main__":
    main()
