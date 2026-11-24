"""Fail-closed Salesforce KRW total reconciliation with separately recorded totalcustom amounts.

This module is pure arithmetic, has no CRM access, and never approves prices for
a new Quote. Raw financial source evidence stays on the authorized laptop.
"""
from decimal import Decimal, InvalidOperation
import re

_VAT = Decimal("1.10")
_MONEY = re.compile(r"^(?:0|[1-9][0-9]{0,12})(?:\.[0-9]{1,2})?$")
_GST = {"10,KR-VAT", "10(KR VAT)"}


def _amount(value):
    if isinstance(value, bool):
        return None
    value = str(value)
    if not _MONEY.fullmatch(value):
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def reconcile_native_krw_quote(*, currency, gst, net, totalcustom,
                               grand, active, approved):
    """Distinguish custom-inclusive totals from actually usable process prices.

    net is the native Exclude_Tax_After_Discount__c field.
    totalcustom is the native totalcustom__c field.
    grand is the native Grand_Total2__c field.

    Important: an arithmetically valid total is NOT a validated Product/Process
    price. The meaning of totalcustom is not established; never divide it across processes or samples.
    """
    result = {
        "status": "HOLD_SOURCE_INCOMPLETE",
        "total_matched": False,
        "totalcustom_present": False,
        "process_price_approved": False,
        "quote_save_permitted": False,
        "crm_writes": 0,
    }
    if currency != "KRW":
        result["status"] = "EXCLUDE_NON_KRW"
        return result
    if gst not in _GST:
        result["status"] = "HOLD_NATIVE_KR_VAT_UNVERIFIED"
        return result
    if active is not True or approved is not True:
        result["status"] = "HOLD_INACTIVE_OR_UNAPPROVED"
        return result
    net, totalcustom, grand = (_amount(net), _amount(totalcustom), _amount(grand))
    if any(x is None for x in (net, totalcustom, grand)) or grand <= 0:
        result["status"] = "HOLD_INVALID_NATIVE_AMOUNTS"
        return result
    result["totalcustom_present"] = totalcustom > 0
    if (net + totalcustom) * _VAT != grand:
        result["status"] = "HOLD_TOTAL_STILL_MISMATCHED"
        return result
    result["total_matched"] = True
    if net == 0 and totalcustom > 0:
        result["status"] = "HOLD_TOTALCUSTOM_ONLY_ZERO_PROCESS_NET"
    elif totalcustom > 0:
        result["status"] = "HOLD_TOTALCUSTOM_PROCESS_UNALLOCATED"
    elif net == 0:
        result["status"] = "HOLD_ZERO_PROCESS_NET"
    else:
        result["status"] = "TOTAL_MATCHED_PROCESS_READBACK_REQUIRED"
    return result
