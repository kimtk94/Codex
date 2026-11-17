"""Fail-closed native Salesforce Quote -> Products -> Processes price audit.

This is pure arithmetic and source-identity validation. It does not access SFDC.
Authenticated laptop readback provides inputs; GitHub Actions uses synthetic
fixtures exclusively. Report Process IDs can differ from native short codes
(e.g. Process-* vs GY*), so resolve the Process_Name reference's Name instead
of equating unrelated namespaces or matching on a shared process name alone.
"""
from collections import Counter
from decimal import Decimal, InvalidOperation
import re

ID = re.compile(r"^[a-zA-Z0-9]{15}(?:[a-zA-Z0-9]{3})?$")
QUOTE = re.compile(r"^QID-[0-9-]{8,50}$")
PROCESS = re.compile(r"^Process-[A-Za-z0-9-]{8,64}$")
DATE = re.compile(r"^2026-\d{2}-\d{2}$")
ALLOWED_UNIT = {"G raw data", "Gb", "M raw reads", "K tags", "NA", "sample"}


def _decimal(value, *, integer=False):
    if isinstance(value, bool) or value is None:
        return None
    try:
        d = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not d.is_finite() or d < 0 or d > Decimal("1e12"):
        return None
    if integer and d != d.to_integral_value():
        return None
    if abs(d.as_tuple().exponent) > 4:
        return None
    return d


def _result(status):
    return {
        "status": status, "verified_rows": 0, "verified_products": 0,
        "historical_index_auto_promote": False,
        "new_quote_price_approved": False,
        "salesforce_write": False, "save_permitted": False,
        "needs_source_recheck_for_new_quote": True,
    }


def audit_native_process_bundle(source, original):
    """Validate authentic original prices WITHOUT converting reported USD data.

    source: sanitized readback of a single SFDC Quote with native KRW row
      amounts and separately corroborated Quote Fee.
    original: private 2026 Source Report manifest plus approval evidence.

    A duplicate report process code across two Products is legitimate; the
    matching key includes exact source Product Name (QD-...) and the resolved
    Salesforce referenced Process object's Name (Process-...).
    """
    if not isinstance(source, dict) or not isinstance(original, dict):
        return _result("HOLD_SOURCE_MISSING")
    if source.get("source") != "AUTHENTICATED_SFDC_UI_API_GET_ONLY" or source.get("salesforce_write") is not False:
        return _result("HOLD_SOURCE_PROVENANCE")
    if source.get("quoteStatus") != "Ready to send" or source.get("currency") != "KRW" or source.get("gst") != "10,KR-VAT":
        return _result("HOLD_SOURCE_QUOTE_STATUS")
    if not DATE.fullmatch(str(original.get("created_date", ""))) or not QUOTE.fullmatch(str(original.get("quote_id", ""))):
        return _result("HOLD_2026_SOURCE_QUOTE")
    if original.get("approvalConfirmed") is not True or original.get("approvalTimeConfirmed") is not True:
        return _result("HOLD_APPROVAL_EVIDENCE")
    products = source.get("products")
    expected = original.get("expected_process_lines")
    if (not isinstance(products, list) or not 1 <= len(products) <= 12 or
        not isinstance(expected, list) or not 1 <= len(expected) <= 100):
        return _result("HOLD_SOURCE_LISTS")
    amount = _decimal(source.get("quoteNet"), integer=True)
    fee = _decimal(source.get("feeTotal"), integer=True)
    grand = _decimal(source.get("grandTotal"), integer=True)
    if any(x is None for x in (amount, fee, grand)) or amount <= 0 or (amount + fee) * Decimal("1.10") != grand:
        return _result("HOLD_QUOTE_TOTAL")
    original_lines = {}
    for line in expected:
        if not isinstance(line, dict):
            return _result("HOLD_REPORT_PROCESS_SCHEMA")
        p_name = line.get("quotation_product_id")
        p_id = line.get("process_id")
        process_name = line.get("process_name")
        unit = line.get("data_unit")
        qty = _decimal(line.get("sample_quantity"))
        size = _decimal(line.get("data_size"))
        if (not isinstance(p_name, str) or not 1 <= len(p_name) <= 128
            or not isinstance(p_id, str) or not PROCESS.fullmatch(p_id)
            or not isinstance(process_name, str) or not 1 <= len(process_name) <= 100
            or unit not in ALLOWED_UNIT or qty is None or qty <= 0
            or size is None or size <= 0):
            return _result("HOLD_REPORT_PROCESS_SCHEMA")
        k = (p_name, p_id)
        if k in original_lines:
            return _result("HOLD_AMBIGUOUS_REPORT_PROCESS")
        original_lines[k] = (process_name, qty, size, unit)
    observed = set()
    all_products = set()
    product_total = Decimal("0")
    row_count = 0
    zero_rate_count = 0
    for product in products:
        if not isinstance(product, dict):
            return _result("HOLD_PRODUCT_SCHEMA")
        record_id, product_name = product.get("recordId"), product.get("name")
        if (not isinstance(record_id, str) or not ID.fullmatch(record_id)
            or not isinstance(product_name, str) or not product_name
            or product_name in all_products):
            return _result("HOLD_PRODUCT_IDENTITY")
        all_products.add(product_name)
        declared = _decimal(product.get("net"), integer=True)
        child_rows = product.get("processRows")
        if declared is None or declared <= 0 or not isinstance(child_rows, list) or not 1 <= len(child_rows) <= 100:
            return _result("HOLD_PRODUCT_AMOUNT")
        subtotal = Decimal("0")
        for row in child_rows:
            if not isinstance(row, dict):
                return _result("HOLD_PROCESS_SCHEMA")
            if row.get("nativeActive") is not True:
                return _result("HOLD_INACTIVE_PROCESS")
            if row.get("productId", "")[:15] != record_id[:15]:
                return _result("HOLD_FOREIGN_PRODUCT_PROCESS")
            code = row.get("resolvedReportProcessId")
            k = (product_name, code)
            if (not isinstance(code, str) or not PROCESS.fullmatch(code)
                or k not in original_lines or k in observed):
                return _result("HOLD_PROCESS_REFERENCE_ALIAS_UNVERIFIED")
            process_name, qty_expected, size_expected, unit_expected = original_lines[k]
            quantity = _decimal(row.get("quantity"))
            unit_price = _decimal(row.get("unitPrice"))
            total_price = _decimal(row.get("totalPrice"))
            size = _decimal(row.get("dataSize"))
            if (quantity is None or quantity <= 0 or size is None or size <= 0
                or unit_price is None or total_price is None
                or row.get("processName") != process_name
                or quantity != qty_expected or size != size_expected
                or row.get("dataUnit") != unit_expected):
                return _result("HOLD_PROCESS_FIELDS_MISMATCH")
            if quantity * unit_price != total_price:
                return _result("HOLD_PROCESS_MULTIPLICATION")
            pack = row.get("packNo")
            if not pack and (process_name != "Data release" or unit_price > 0):
                return _result("HOLD_UNEXPECTED_MISSING_PACK")
            if unit_price == 0:
                zero_rate_count += 1
            observed.add(k)
            subtotal += total_price
            row_count += 1
        if subtotal != declared:
            return _result("HOLD_PRODUCT_SUM")
        product_total += subtotal
    if observed != set(original_lines):
        return _result("HOLD_PROCESS_ROW_COVERAGE")
    if product_total != amount:
        return _result("HOLD_QUOTE_PROCESS_SUM")
    return {**_result("NATIVE_PROCESS_AND_REPORT_REFERENCES_VERIFIED"),
            "verified_rows": row_count, "verified_products": len(products),
            "zero_price_steps": zero_rate_count,
            "source_original_krw": True,
            "eligible_for_separate_historical_index_review": True}
