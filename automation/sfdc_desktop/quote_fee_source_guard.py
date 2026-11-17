"""Fail-closed native Salesforce Quotation Fee to Quotation Product reconciliation.

Pure validation of already authenticated, read-only Salesforce UI API evidence.
Never infer service unit prices or authorize Salesforce/Feishu writes.
"""
from collections import Counter
from decimal import Decimal
import re

from quote_custom_fee_guard import reconcile_native_krw_quote, _amount

_ID = re.compile(r"^[A-Za-z0-9]{15}(?:[A-Za-z0-9]{3})?$")
_TYPES = frozenset(("SP Sample Shipping Fee", "Sample Return Fee"))


def _hold(code):
    return {
        "status": code,
        "fee_sum_verified": False,
        "product_link_verified": False,
        "process_price_approved": False,
        "fee_approved_for_new_quote": False,
        "quote_save_permitted": False,
        "crm_writes": 0,
    }


def reconcile_quotation_fee(*, parent, fee_rows, quotation_product_ids):
    """Verify source-native fee subtotal, fee type and exact quote-product membership.

    A fee belongs to a specific Quotation Product, but remains a separate
    fee line. It is never allocated into the Product's sample/process unit price.
    Product ID membership must be read from the SAME parent Quote.
    """
    if not isinstance(parent, dict):
        return _hold("HOLD_PARENT_NOT_VERIFIED")
    keys = ("currency", "gst", "net", "totalcustom", "grand", "active", "approved")
    if any(k not in parent for k in keys):
        return _hold("HOLD_PARENT_FIELDS_MISSING")
    verified = reconcile_native_krw_quote(**{k: parent[k] for k in keys})
    if not verified["total_matched"]:
        return _hold(verified["status"])
    subtotal = _amount(parent["totalcustom"])
    if subtotal is None or subtotal <= 0:
        return _hold("HOLD_NO_SEPARATE_FEE_SUBTOTAL")
    if not isinstance(fee_rows, list) or not (1 <= len(fee_rows) <= 100):
        return _hold("HOLD_FEE_SOURCE_ROWS_INVALID")
    if not isinstance(quotation_product_ids, list) or not quotation_product_ids:
        return _hold("HOLD_SAME_QUOTE_PRODUCT_SOURCE_MISSING")
    if any(not isinstance(pid, str) or not _ID.fullmatch(pid)
           for pid in quotation_product_ids):
        return _hold("HOLD_INVALID_SAME_QUOTE_PRODUCT_ID")
    ids = [pid[:15] for pid in quotation_product_ids]
    if len(ids) != len(set(ids)):
        return _hold("HOLD_DUPLICATE_PRODUCT_SOURCE")
    related_products = set(ids)
    total = Decimal("0")
    counts = Counter()
    for row in fee_rows:
        if not isinstance(row, dict):
            return _hold("HOLD_FEE_ROW_INVALID")
        fee_type = row.get("fee_type")
        if fee_type not in _TYPES:
            return _hold("HOLD_UNKNOWN_FEE_TYPE")
        if row.get("currency") != "KRW":
            return _hold("HOLD_FEE_CURRENCY_MISMATCH")
        ref = row.get("quotation_product_id")
        if not isinstance(ref, str) or not _ID.fullmatch(ref) or ref[:15] not in related_products:
            return _hold("HOLD_FEE_PRODUCT_NOT_IN_QUOTE")
        fee = _amount(row.get("fee"))
        fee_to_calculate = _amount(row.get("fee_to_calculate"))
        if fee is None or fee <= 0 or fee_to_calculate != fee:
            return _hold("HOLD_FEE_AMOUNT_UNVERIFIED")
        total += fee
        counts[fee_type] += 1
    if total != subtotal:
        return _hold("HOLD_QUOTE_FEE_SUBTOTAL_MISMATCH")
    return {
        **_hold("FEE_SUM_AND_PRODUCT_LINK_VERIFIED_PROCESS_RATE_HOLD"),
        "fee_sum_verified": True,
        "product_link_verified": True,
        "verified_fee_count": len(fee_rows),
        "fee_type_counts": dict(counts),
        "fee_subtotal_krw": str(total),
        "process_net_zero": _amount(parent["net"]) == 0,
        "source_readback_required_for_reuse": True,
    }
