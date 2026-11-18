"""Single-record, fail-closed Salesforce Opportunity + Quotation save preflight.

This module never connects to Salesforce or clicks Save. Only operator-laptop
readback may supply the private candidate and authenticated source evidence.
GitHub Actions runs synthetic fixtures only.

A passing preflight is READY_FOR_HUMAN_REVIEW, NOT permission to write.
The user must approve the exact immutable request digest and an independent
laptop-only execution adapter must recheck identity and duplicate counts.
"""
from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
import re

SFID = re.compile(r"^[A-Za-z0-9]{15}(?:[A-Za-z0-9]{3})?$")
NAME = re.compile(r"^[^\r\n\t]{5,180}$")
QID = re.compile(r"^QID-\d{4}-\d{2}-\d{2}-\d{4,}$")
PROCESS = re.compile(r"^Process-[A-Za-z0-9-]{8,64}$")
MONEY = re.compile(r"^(?:0|[1-9]\d{0,11})(?:\.\d{1,4})?$")
COUNT = re.compile(r"^[1-9]\d{0,5}$")
UNITS = {"Gb", "M raw reads", "NA", "sample", "K tags", "Lane", "Cell"}
MAX_AGE_SECONDS = 1800


def _month_after(d: date):
    year = d.year + (d.month == 12)
    month = 1 if d.month == 12 else d.month + 1
    return date(year, month, min(d.day, monthrange(year, month)[1]))


def _krw(value):
    if not isinstance(value, str) or not MONEY.fullmatch(value):
        return None
    try:
        n = Decimal(value)
    except InvalidOperation:
        return None
    return n if n.is_finite() and n >= 0 else None


def _hold(*codes):
    return {
        "status": "HOLD_SFDC_SAVE_PREFLIGHT",
        "reason_codes": sorted(set(codes)),
        "ready_for_review": False,
        "approval_digest": None,
        "salesforce_save_permitted": False,
        "opportunity_created": False,
        "quotation_created": False,
        "crm_writes": 0,
    }


def audit_save_preflight(candidate, evidence, *, asof_utc=None):
    errors = []
    if not isinstance(candidate, dict) or not isinstance(evidence, dict):
        return _hold("MISSING_PRIVATE_REVIEW_AND_SOURCE")
    if asof_utc is None:
        asof_utc = datetime.now(timezone.utc)
    if asof_utc.tzinfo is None:
        return _hold("UTC_TIME_INVALID")
    asof_utc = asof_utc.astimezone(timezone.utc)

    if candidate.get("operation") != "CREATE_NEW_OPPORTUNITY_AND_QUOTATION":
        errors.append("WRONG_TRANSACTION_TYPE")
    if candidate.get("currency") != "KRW" or candidate.get("vat_rate") != "0.10":
        errors.append("CURRENCY_OR_VAT_RATE")
    if candidate.get("country") != "Korea":
        errors.append("COUNTRY_UNVERIFIED")
    name = candidate.get("opportunity_name")
    quote_name = candidate.get("quotation_name")
    if not isinstance(name, str) or not NAME.fullmatch(name) or quote_name != name:
        errors.append("OPPORTUNITY_QUOTE_NAME_MISMATCH")
    if not str(candidate.get("description", "")).strip():
        errors.append("NEW_PROGRESS_DESCRIPTION_REQUIRED")
    if str(candidate.get("description", "")).strip() == str(candidate.get("source_progress_description", "")).strip():
        errors.append("PROGRESS_DESCRIPTION_COPIED")

    ids = [(candidate.get("account_id"), "001", "ACCOUNT_ID"),
           (candidate.get("contact_id"), "003", "CONTACT_ID")]
    for raw, prefix, label in ids:
        if not isinstance(raw, str) or not raw.startswith(prefix) or not SFID.fullmatch(raw):
            errors.append(label + "_UNVERIFIED")
    if not isinstance(candidate.get("stage"), str) or not candidate["stage"]:
        errors.append("STAGE_MISSING")
    if not isinstance(candidate.get("forecast_category"), str) or not candidate["forecast_category"]:
        errors.append("FORECAST_CATEGORY_MISSING")
    if not isinstance(candidate.get("service_line"), str) or not candidate["service_line"]:
        errors.append("SERVICE_LINE_MISSING")
    try:
        received = date.fromisoformat(str(candidate["request_date_kst"]))
        closed = date.fromisoformat(str(candidate["close_date_kst"]))
        if closed != _month_after(received):
            errors.append("CLOSE_DATE_NOT_PLUS_ONE_MONTH")
    except (ValueError, KeyError, TypeError):
        errors.append("DATES_UNVERIFIED")

    if evidence.get("source") != "AUTHENTICATED_SFDC_UI_READ_ONLY" or evidence.get("salesforce_write") is not False:
        errors.append("SOURCE_READBACK_UNVERIFIED")
    try:
        observed = datetime.fromisoformat(evidence["checked_at_utc"].replace("Z", "+00:00"))
        age = (asof_utc - observed.astimezone(timezone.utc)).total_seconds()
        if not 0 <= age <= MAX_AGE_SECONDS:
            errors.append("READBACK_STALE")
    except (KeyError, ValueError, TypeError, AttributeError):
        errors.append("READBACK_TIME_MISSING")
    expected_truth = (
        "account_contact_relation_verified",
        "opportunity_record_type_verified",
        "stage_and_forecast_verified",
        "service_line_verified",
        "current_product_and_process_ids_verified",
        "current_native_krw_rates_verified",
        "per_process_pack_rules_verified",
        "client_price_condition_approved",
        "opportunity_amount_field_verified",
        "opportunity_quote_schema_verified",
        "quote_fee_mode_verified",
        "cloud_required_and_allocation_verified",
    )
    errors.extend("UNVERIFIED_" + key.upper() for key in expected_truth if evidence.get(key) is not True)

    # Salesforce Name is not a unique key: identical Opportunity and Quotation
    # names are intentional. Existing 006/a0P IDs are reference records,
    # whereas a newly saved record MUST receive a distinct Salesforce ID.
    # A legacy name-count check with zero matches is supported only for
    # backwards-compatible no-collision cases; same-name cases MUST have
    # authenticated, query-complete ID evidence for both objects.
    duplicates = evidence.get("duplicate_check")
    if not isinstance(duplicates, dict):
        errors.append("DUPLICATE_READBACK_MISSING")
    elif duplicates.get("scope") == "ACCOUNT_CONTACT_NAME":
        if duplicates.get("matching_opportunities") != 0 or duplicates.get("matching_quotations") != 0:
            errors.append("IDENTICAL_NAME_REQUIRES_NATIVE_ID_SNAPSHOT")
    elif duplicates.get("scope") == "SOURCE_RECORD_ID_SNAPSHOT":
        expected = (
            ("source_opportunity_id", "006", "matching_opportunity_ids"),
            ("source_quotation_id", "a0P", "matching_quotation_ids")
        )
        if (duplicates.get("checked_current_authenticated_ui") is not True or
            duplicates.get("query_complete") is not True):
            errors.append("NATIVE_ID_READBACK_INCOMPLETE")
        for field, prefix, list_key in expected:
            wanted = candidate.get(field)
            matching = duplicates.get(list_key)
            if (not isinstance(wanted,str) or not wanted.startswith(prefix) or
                not SFID.fullmatch(wanted) or duplicates.get(field) != wanted):
                errors.append("SOURCE_" + field.upper() + "_MISMATCH")
            if (not isinstance(matching,list) or len(matching)>1000 or
                not all(isinstance(v,str) and v.startswith(prefix) and SFID.fullmatch(v) for v in matching) or
                len(matching)!=len(set(matching)) or wanted not in matching):
                errors.append("UNVERIFIED_" + list_key.upper())
        # Other native IDs with the exact same Name are allowed. Their
        # identity is preserved and they must never be overwritten/reused.
    else:
        errors.append("UNKNOWN_DUPLICATE_VERIFICATION_MODE")
    if evidence.get("account_id") != candidate.get("account_id") or evidence.get("contact_id") != candidate.get("contact_id"):
        errors.append("ACCOUNT_CONTACT_SOURCE_MISMATCH")

    products = candidate.get("products")
    if not isinstance(products, list) or not 1 <= len(products) <= 8:
        return _hold(*errors, "NO_VERIFIED_QUOTE_PRODUCTS")
    try:
        samples = candidate.get("sample_quantity")
        samples = int(samples) if isinstance(samples, int) or isinstance(samples, str) and COUNT.fullmatch(samples) else 0
        if not 1 <= samples <= 100000:
            raise ValueError
    except (TypeError, ValueError):
        errors.append("NEW_SAMPLE_COUNT_UNVERIFIED")
        samples = 0
    total = Decimal("0")
    seen = set()
    cloud_quantities = []
    lines_count = 0
    for product in products:
        if not isinstance(product, dict) or not isinstance(product.get("processes"), list):
            errors.append("PRODUCT_STRUCTURE_INVALID")
            continue
        product_id = product.get("native_product_id")
        if not isinstance(product_id, str) or not SFID.fullmatch(product_id):
            errors.append("NATIVE_PRODUCT_ID_MISSING")
        if not product.get("product_name"):
            errors.append("PRODUCT_NAME_MISSING")
        if product.get("source_reference_only") is not True:
            errors.append("SOURCE_LINE_PROVENANCE_INVALID")
        for line in product["processes"]:
            lines_count += 1
            if lines_count > 100:
                errors.append("TOO_MANY_PROCESS_LINES")
                break
            if not isinstance(line, dict):
                errors.append("PROCESS_LINE_INVALID")
                continue
            key = (product_id, line.get("process_id"))
            if key in seen:
                errors.append("DUPLICATE_PRODUCT_PROCESS")
            seen.add(key)
            raw = line.get("process_id")
            native = line.get("native_process_id")
            if not isinstance(raw, str) or not PROCESS.fullmatch(raw) or not isinstance(native, str) or not SFID.fullmatch(native):
                errors.append("NATIVE_PROCESS_ID_MISSING")
            price = _krw(line.get("new_unit_price_krw"))
            qty_text = line.get("new_process_quantity")
            qty = int(qty_text) if isinstance(qty_text, str) and COUNT.fullmatch(qty_text) else None
            if price is None or qty is None or not 1 <= qty <= 100000:
                errors.append("PROCESS_QUANTITY_PRICE_INVALID")
            else:
                total += price * qty
            if line.get("data_unit") not in UNITS or line.get("new_production_depth") is None:
                errors.append("PROCESS_UNIT_DEPTH_MISSING")
            if line.get("current_native_price_rechecked") is not True:
                errors.append("PRICE_SOURCE_RECHECK_REQUIRED")
            if line.get("pack_applicable") is True and line.get("pack_verified") is not True:
                errors.append("PACK_UNVERIFIED")
            if line.get("process_category") == "ALICLOUD":
                if qty is not None:
                    cloud_quantities.append(qty)

    cloud = candidate.get("cloud")
    if not isinstance(cloud, dict) or cloud.get("required") not in (True, False):
        errors.append("ALICLOUD_REQUIRED_OR_NOT_EXPLICIT")
    elif cloud["required"]:
        gb_raw = cloud.get("total_gb")
        gb = _krw(gb_raw)
        if gb is None or gb <= 0:
            errors.append("ALICLOUD_GB_UNVERIFIED")
        else:
            expected_qty = int((gb / Decimal(100)).to_integral_value(rounding="ROUND_CEILING"))
            if cloud_quantities != [expected_qty]:
                errors.append("ALICLOUD_QTY_MISMATCH")
        if cloud.get("amount_included_in_process_rows") is not True:
            errors.append("ALICLOUD_PRICE_ALLOCATION_UNVERIFIED")
    elif cloud_quantities:
        errors.append("UNEXPECTED_ALICLOUD_ROW")

    fee = candidate.get("quote_fee")
    if not isinstance(fee, dict) or fee.get("mode") not in ("EXCLUDE", "INCLUDE_EXPLICITLY_APPROVED"):
        errors.append("FEE_MODE_UNVERIFIED")
        fee_amount = None
    elif fee["mode"] == "EXCLUDE":
        fee_amount = Decimal(0)
        if fee.get("amount_krw") != "0":
            errors.append("EXCLUDED_FEE_MUST_BE_ZERO")
    else:
        fee_amount = _krw(fee.get("amount_krw"))
        if fee_amount is None or fee.get("source_fee_rechecked") is not True:
            errors.append("CUSTOM_FEE_RECHECK_REQUIRED")
    if fee_amount is not None:
        total += fee_amount

    vat = total * Decimal("0.10")
    gross = total + vat
    if total != total.to_integral_value() or vat != vat.to_integral_value() or gross != gross.to_integral_value():
        errors.append("FRACTIONAL_KRW_TOTAL")
    if total <= 0:
        errors.append("ZERO_OR_NEGATIVE_QUOTE_TOTAL")
    if str(candidate.get("expected_net_krw")) != format(total, "f"):
        errors.append("QUOTE_AMOUNT_NOT_RECONCILED")
    if str(candidate.get("opportunity_amount_krw")) != format(total, "f"):
        errors.append("OPPORTUNITY_AMOUNT_NOT_RECONCILED")

    if errors:
        return _hold(*errors)
    # Deterministic digest of reviewed candidate: a changed quantity, price,
    # Account, Contact, fee or Process changes the approval target.
    canonical = json.dumps(candidate,sort_keys=True,ensure_ascii=False,separators=(",",":"))
    digest = "SFDC-REVIEW-" + sha256(canonical.encode("utf8")).hexdigest()[:24]
    return {
        "status": "READY_FOR_PER_RECORD_OPERATOR_APPROVAL",
        "reason_codes": [],
        "ready_for_review": True,
        "approval_digest": digest,
        "expected_net_krw": format(total,"f"),
        "expected_vat_krw": format(vat,"f"),
        "expected_gross_krw": format(gross,"f"),
        "verified_product_count": len(products),
        "verified_process_row_count": lines_count,
        "salesforce_save_permitted": False,
        "operator_final_approval_required": True,
        "opportunity_created": False,
        "quotation_created": False,
        "crm_writes": 0,
    }
