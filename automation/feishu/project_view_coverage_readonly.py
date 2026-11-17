#!/usr/bin/env python3
"""Read-only Feishu Quote-first project view coverage and exclusion triage.

Never prints customer/project identifiers, free-text source values, invoice
amounts, contact information, raw filter values, tokens or Feishu row payloads.
Does not call any Feishu business write endpoint; POST is used only for auth.
"""
import collections
import datetime as dt
import json
import os
import re
import time
import urllib.error
import urllib.parse

from base_readonly_probe import request, require
from project_quote_operating_sync import (TABLES, PAID_VIEW, value,
                                         validate_sources)
from sales_home_links import API, PROJECT_BOARD, extract_token, require_success

READ_MAX_RETRIES = 2
TRANSIENT_HTTP_CODES = (429, 500, 502, 503, 504)
VIEW_IDS = {"ACTIVE": TABLES["active"][1],
            "BILLING": TABLES["billing"][1],
            "ARCHIVED": PAID_VIEW}
FIELD_WHITELIST = {
    "Source Key": "SOURCE_KEY",
    "Quote Full Name": "QUOTE_NAME",
    "Payment State": "PAYMENT_STATE",
    "Current Stage": "CURRENT_STAGE",
    "Progress %": "PROGRESS",
    "Invoice Gross M KRW": "INVOICE_GROSS",
    "Outstanding Balance M KRW": "OUTSTANDING",
    "Quote Match State": "QUOTE_MATCH",
    "Last Sync KST": "LAST_SYNC",
}
ALLOWED_OPERATORS = {
    "is", "isNot", "contains", "doesNotContain", "isEmpty", "isNotEmpty",
    "greater", "less", "equal", "notEqual", "in", "notIn", "between",
}


def get_json(path, token):
    """Retry same GET only on transient transport conditions; no write retry."""
    for attempt in range(READ_MAX_RETRIES + 1):
        try:
            return require_success(request("GET", path, token=token), "READ_ONLY")
        except (urllib.error.URLError, TimeoutError, ConnectionResetError):
            retry = True
        except RuntimeError as exc:
            retry = any(str(exc).startswith("HTTP " + str(code) + " from ")
                        for code in TRANSIENT_HTTP_CODES)
            if not retry:
                raise
        if attempt >= READ_MAX_RETRIES:
            raise RuntimeError("READ_ONLY_TRANSIENT_RETRY_EXHAUSTED") from None
        time.sleep(min(1 << attempt, 2))
    raise RuntimeError("READ_ONLY_UNREACHABLE")


def pages(path, token, extra=None):
    """Verify cursor and record identity continuity before yielding full list."""
    rows, cursor, seen = [], "", set()
    for _ in range(1000):
        params = {"page_size": 100}
        if extra:
            params.update(extra)
        if cursor:
            params["page_token"] = cursor
        qs = urllib.parse.urlencode(params)
        result = get_json(path + "?" + qs, token)
        items = result.get("items") or []
        for item in items:
            identity = item.get("record_id") or item.get("field_id") or item.get("view_id") or item.get("table_id")
            if not identity or identity in seen:
                raise RuntimeError("READ_ONLY_PAGE_DUPLICATE_OR_EMPTY_ID")
            seen.add(identity)
        rows.extend(items)
        if not result.get("has_more"):
            return rows
        new_cursor = result.get("page_token")
        if not new_cursor or new_cursor == cursor:
            raise RuntimeError("READ_ONLY_BAD_PAGE_CURSOR")
        cursor = new_cursor
    raise RuntimeError("READ_ONLY_MAX_PAGES_EXCEEDED")


def key_index(records):
    result = {}
    for row in records:
        f = row.get("fields") or {}
        key = value(f.get("Source Key")).upper()
        if not key or key in result or not row.get("record_id"):
            raise RuntimeError("SOURCE_PROJECT_KEY_INTEGRITY_BLOCK")
        result[key] = row
    return result


def membership(original, views):
    if len(original) < 100:
        raise RuntimeError("SOURCE_PROJECT_COUNT_UNEXPECTED")
    all_records = key_index(original)
    view_keys = {}
    for name, rows in views.items():
        ix = key_index(rows)
        if not set(ix).issubset(all_records):
            raise RuntimeError("VIEW_HAS_MISSING_SOURCE_KEYS")
        view_keys[name] = set(ix)
    for left in VIEW_IDS:
        for right in VIEW_IDS:
            if left < right and (view_keys[left] & view_keys[right]):
                raise RuntimeError("PROJECT_VIEW_OVERLAP_" + left + "_" + right)
    outside = set(all_records) - set().union(*view_keys.values())
    if sum(len(v) for v in view_keys.values()) + len(outside) != len(all_records):
        raise RuntimeError("PROJECT_VIEW_COVERAGE_ACCOUNTING_BLOCK")
    return all_records, view_keys, outside


def payment_bucket(raw):
    v = value(raw).lower().strip()
    if not v:
        return "MISSING"
    if re.search(r"unpaid|not paid|outstanding|미납|미수|입금 전", v):
        return "UNPAID_LIKE_NOT_BANK_VERIFIED"
    if re.search(r"partial|partially|일부|부분", v):
        return "PARTIAL_LIKE_NOT_BANK_VERIFIED"
    if v in ("paid", "payment completed", "fully paid", "결제 완료", "입금 완료", "완납"):
        return "PAID_LIKE_NOT_BANK_VERIFIED"
    if re.search(r"pending|waiting|미확인|대기|unknown", v):
        return "PENDING_OR_UNVERIFIED"
    return "OTHER_UNVERIFIED"


def stage_bucket(raw):
    v = value(raw).lower().strip()
    if not v:
        return "MISSING"
    checks = (
        ("SIF_OR_PREP", r"\bsif\b|prepayment|contract|po request"),
        ("SAMPLE_OR_QC", r"sample|\bqc\b|quality|입고|접수|검수"),
        ("LIBRARY", r"library|라이브러리"),
        ("SEQUENCING", r"sequenc|시퀀싱"),
        ("ANALYSIS", r"analy|bioinfo|분석"),
        ("DATA_OR_REPORT", r"data ready|report|statement|납품"),
        ("COMPLETE_LIKE", r"complet|finish|완료|종료"),
    )
    for label, regex in checks:
        if re.search(regex, v):
            return label
    return "OTHER_STAGE"


def quantity_bucket(raw):
    v = value(raw)
    if not v or v in ("-", "—", "no value", "N/A"):
        return "MISSING"
    try:
        from decimal import Decimal
        number = Decimal(v.replace(",", "").replace("₩", ""))
        if not number.is_finite() or number < 0:
            return "INVALID"
        return "ZERO" if number == 0 else "POSITIVE_UNVERIFIED"
    except Exception:
        return "INVALID"


def progress_bucket(raw):
    v = value(raw)
    if not v or v in ("-", "—", "no value", "N/A"):
        return "MISSING"
    try:
        from decimal import Decimal
        n = Decimal(v.replace("%", "").replace(",", ""))
        if not n.is_finite() or n < 0 or n > 100:
            return "INVALID"
        if n == 100:
            return "EXACT_100"
        if n == 0:
            return "EXACT_0"
        if n < 25:
            return "1_TO_24"
        if n < 50:
            return "25_TO_49"
        if n < 75:
            return "50_TO_74"
        return "75_TO_99"
    except Exception:
        return "INVALID"


def quote_bucket(raw):
    v = value(raw).upper().strip()
    if not v:
        return "MISSING"
    if v == "SFDC_EXACT_VERIFIED":
        return "EXACT_VERIFIED_LABEL_ONLY"
    if "UNMATCH" in v or "NO_MATCH" in v:
        return "UNMATCHED_LABEL_ONLY"
    if "HOLD" in v or "REVIEW" in v or "PENDING" in v:
        return "REVIEW_OR_HOLD"
    return "OTHER_OR_UNVERIFIED"


def classify(records):
    dimensions = {
        "PAYMENT": ("Payment State", payment_bucket),
        "STAGE": ("Current Stage", stage_bucket),
        "PROGRESS": ("Progress %", progress_bucket),
        "INVOICE_GROSS": ("Invoice Gross M KRW", quantity_bucket),
        "OUTSTANDING": ("Outstanding Balance M KRW", quantity_bucket),
        "QUOTE_MATCH": ("Quote Match State", quote_bucket),
    }
    results = {}
    for name, (field, classifier) in dimensions.items():
        counts = collections.Counter(classifier((r.get("fields") or {}).get(field))
                                     for r in records)
        if sum(counts.values()) != len(records):
            raise RuntimeError("PROJECT_AGGREGATE_COUNT_MISMATCH")
        results[name] = dict(sorted(counts.items()))
    return results


def filter_metadata(view, field_names):
    prop = view.get("property") or {}
    if isinstance(prop, str):
        try:
            prop = json.loads(prop)
        except (ValueError, TypeError):
            raise RuntimeError("VIEW_PROPERTY_UNPARSEABLE")
    if not isinstance(prop, dict):
        raise RuntimeError("VIEW_PROPERTY_INVALID")
    info = prop.get("filter_info") or {}
    if not isinstance(info, dict):
        raise RuntimeError("VIEW_FILTER_INVALID")
    conditions = info.get("conditions") or []
    if not isinstance(conditions, list):
        raise RuntimeError("VIEW_CONDITIONS_INVALID")
    result = collections.Counter()
    result["FILTER_CONDITIONS"] = len(conditions)
    result["FILTER_PRESENT"] = 1 if conditions else 0
    conjunction = str(info.get("conjunction") or "").lower()
    result["CONJUNCTION_" + (conjunction.upper() if conjunction in ("and", "or") else "OTHER")] = 1
    for cond in conditions:
        if not isinstance(cond, dict):
            raise RuntimeError("VIEW_CONDITION_INVALID")
        field_name = field_names.get(cond.get("field_id"), "")
        field = FIELD_WHITELIST.get(field_name, "OTHER_FIELD")
        operator = str(cond.get("operator") or "")
        operator_label = operator if operator in ALLOWED_OPERATORS else "OTHER"
        result["FILTER_" + field + "_" + operator_label] += 1
        # NEVER print condition 'value'; values could contain free-text customer data.
    return dict(sorted(result.items()))


def audit(token, root):
    table_path = root + "/tables/" + PROJECT_BOARD
    all_records = pages(table_path + "/records", token)
    view_records = {label: pages(table_path + "/records", token, {"view_id": view_id})
                    for label, view_id in VIEW_IDS.items()}
    original_index, view_keys, outside = membership(all_records, view_records)
    print("PROJECT_COVERAGE_TOTAL=" + str(len(all_records)))
    for name in VIEW_IDS:
        print("PROJECT_COVERAGE_" + name + "=" + str(len(view_keys[name])))
    print("PROJECT_COVERAGE_OUTSIDE_ALL_VIEWS=" + str(len(outside)))
    print("PROJECT_COVERAGE_OUTSIDE_PCT=" +
          str(round(100 * len(outside) / len(all_records), 2)))
    print("PROJECT_COVERAGE_KEY_UNIQUENESS_PASS=1")
    for label in ("OUTSIDE", "ACTIVE", "BILLING", "ARCHIVED"):
        keys = outside if label == "OUTSIDE" else view_keys[label]
        records = [original_index[key] for key in keys]
        print("PROJECT_COHORT_" + label + "_COUNT=" + str(len(records)))
        for field, cats in classify(records).items():
            for cat, count in cats.items():
                print("PROJECT_COHORT_" + label + "_" + field + "_" + cat + "=" + str(count))
    fields = pages(table_path + "/fields", token)
    field_names = {field["field_id"]: field.get("field_name") for field in fields}
    for label, view_id in VIEW_IDS.items():
        detail = get_json(table_path + "/views/" + urllib.parse.quote(view_id, safe=""), token)
        view = detail.get("view") or detail
        if not isinstance(view, dict) or view.get("view_id") != view_id:
            raise RuntimeError("PROJECT_VIEW_DETAIL_ID_MISMATCH")
        for name, count in filter_metadata(view, field_names).items():
            print("PROJECT_VIEW_" + label + "_" + name + "=" + str(count))
    print("PROJECT_VIEW_COVERAGE_AUDIT_PASS read_only=1 record_writes=0 "
          "raw_customer_values_logged=0 paid_state_not_bank_verified=1")


def main():
    if os.environ.get("FEISHU_PROJECT_VIEW_AUDIT_MODE", "plan") != "plan":
        raise RuntimeError("PROJECT_VIEW_READ_ONLY_MODE_REQUIRED")
    auth = request("POST", "/open-apis/auth/v3/tenant_access_token/internal",
                   body={"app_id": require("FEISHU_APP_ID"),
                         "app_secret": require("FEISHU_APP_SECRET")})
    token = extract_token(auth)
    audit(token, API)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Never log HTTP paths, tokens, original Feishu records or customer fields.
        print("PROJECT_VIEW_COVERAGE_BLOCK=" + type(exc).__name__)
        raise SystemExit(1)
