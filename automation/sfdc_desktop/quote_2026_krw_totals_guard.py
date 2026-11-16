"""Authoritative fail-closed numeric gate for ORIGINAL 2026 KRW Salesforce Quotes.

Both single- and multi-Product desktop exporters call this before accepting
any original unit price. Never infer KRW from QQ USD reports or repair a
mismatched original Salesforce Grand Total. This module is pure/no I/O.
"""
from decimal import Decimal, InvalidOperation
import re

_ALLOWED_VAT = re.compile(r"^10(?:\.0+)?\s*(?:\([^)]{1,80}\))?$")


def require_original_krw_totals(currency, active, net, grand, vat_setting=""):
    """Return Decimal(net/grand) only for live KRW, active, exact 10% VAT Quotes.

    '10(KR VAT)' text alone does not establish correct tax arithmetic.
    No amount, quote ID or customer details appear in errors.
    """
    if currency != "KRW":
        raise ValueError("NOT_NATIVE_KRW")
    if active != "True":
        raise ValueError("NOT_ACTIVE")
    if vat_setting and not _ALLOWED_VAT.fullmatch(str(vat_setting).strip()):
        raise ValueError("QUOTE_VAT_SETTING_MISMATCH")
    try:
        subtotal = Decimal(str(net))
        gross = Decimal(str(grand))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("QUOTE_TOTAL_INVALID") from None
    if not subtotal.is_finite() or not gross.is_finite():
        raise ValueError("QUOTE_TOTAL_INVALID")
    if subtotal <= 0 or gross <= 0 or abs(gross-subtotal*Decimal("1.10")) > Decimal("0.05"):
        raise ValueError("QUOTE_VAT_TOTAL_MISMATCH")
    return subtotal, gross
