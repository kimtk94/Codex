"""Independent read-only gate for a *previously saved* Opportunity and Quote.

Never creates Salesforce records. Call with a fresh Salesforce UI bundle loaded
by the exact NEW Opportunity ID. An input containing only a pending or cloned
form is not readback evidence. Missing authoritative fields fail closed.
"""
import re

from sfdc_quote_price_fields import (
    evaluate as evaluate_single, evaluate_multi, PriceError,
)


def _record(value, prefix):
    return (isinstance(value, str) and
            re.fullmatch(prefix + r"[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?", value) is not None)


def _block(reason):
    return {"status": "BLOCK", "code": reason, "verified": False}


def verify_saved_pair(prepared, new_opportunity_id, live_bundle):
    """Check exact new-parent identity, per-process price and VAT readback.

    The returned PASS means an existing saved pair reconciles; it is *not*
    permission to save other records or evidence of action attribution.
    """
    if not isinstance(prepared, dict) or prepared.get("status") != "READY":
        return _block("EXPECTED_PAIR_NOT_READY")
    expected_opp = prepared.get("opportunity") or {}
    expected_quote = prepared.get("quotation") or {}
    expected_prices = prepared.get("price_fields") or {}
    source_opp_id = expected_opp.get("referenceOpportunityId")
    source_quote_id = expected_quote.get("sourceQuoteId")
    if not (_record(new_opportunity_id, "006") and _record(source_opp_id, "006")
            and _record(source_quote_id, "a0P") and new_opportunity_id != source_opp_id):
        return _block("NEW_PARENT_ID_NOT_VERIFIED")
    if not isinstance(live_bundle, dict) or live_bundle.get("status") != "PASS" or live_bundle.get("read_only") is not True:
        return _block("LIVE_BUNDLE_UNAVAILABLE")
    if (live_bundle.get("selectionStatus") != "EXACT_ONE" or
            len(live_bundle.get("linkedQuotes") or []) != 1):
        return _block("NEW_PARENT_LINK_NOT_UNIQUE")
    opp = live_bundle.get("opportunity") or {}
    quote = live_bundle["linkedQuotes"][0]
    if not isinstance(opp, dict) or not isinstance(quote, dict):
        return _block("NEW_PAIR_FIELDS_UNAVAILABLE")
    new_quote_id = quote.get("id")
    if (opp.get("id") != new_opportunity_id or
            not _record(new_quote_id, "a0P") or
            new_quote_id == source_quote_id or
            quote.get("opportunityId") != new_opportunity_id):
        return _block("NEW_QUOTE_PARENT_MISMATCH")
    if (opp.get("source") != "LIVE_SALESFORCE" or
            quote.get("source") != "LIVE_SALESFORCE" or
            opp.get("read_only") is not True or quote.get("read_only") is not True):
        return _block("INDEPENDENT_UI_SOURCE_UNVERIFIED")
    if (opp.get("name") != expected_opp.get("opportunityName") or
            quote.get("name") != expected_quote.get("quoteName") or
            quote.get("name") != opp.get("name")):
        return _block("NEW_PAIR_NAMES_MISMATCH")
    for field, expected_key in (
        ("accountId", "accountId"),
        ("contactId", "contactId"),
        ("accountName", "accountName"),
        ("contactName", "contactName"),
    ):
        expected = expected_opp.get(expected_key)
        if not expected or opp.get(field) != expected or quote.get(field) != expected:
            return _block("NEW_PAIR_CUSTOMER_MISMATCH")
    if (opp.get("samplesSource") != "SFDC_FIELD" or
            opp.get("samples") != expected_opp.get("samples")):
        return _block("NEW_OPPORTUNITY_SAMPLE_UNVERIFIED")
    if (opp.get("progressDescriptionSource") != expected_opp.get("progressDescription") or
            not opp.get("progressDescriptionSource")):
        return _block("NEW_PROGRESS_NOT_REPLACED")
    if (not isinstance(opp.get("amountKrw"), int) or
            opp.get("amountKrw") != prepared.get("expectedNet") or
            expected_prices.get("Quote Net KRW") != prepared.get("expectedNet")):
        return _block("NEW_OPPORTUNITY_NET_MISMATCH")
    if (quote.get("sourceVatRateVerified10Pct") is not True or
            quote.get("totalPriceKrw") != prepared.get("expectedNet") or
            quote.get("grandTotalKrw") != prepared.get("expectedGross") or
            expected_prices.get("Quote Gross KRW") != prepared.get("expectedGross")):
        return _block("NEW_QUOTE_VAT_TOTAL_MISMATCH")
    if (quote.get("samples") != expected_quote.get("samples") or
            quote.get("dataSize") != expected_quote.get("dataSize")):
        return _block("NEW_QUOTE_QUANTITY_UNVERIFIED")
    try:
        if quote.get("productCount") == 1:
            if (quote.get("productName") != expected_quote.get("productName") or
                    quote.get("pricingStatus") != "VERIFIED_PROCESS_LINES" or
                    quote.get("cloudLinePresent") is not True):
                return _block("NEW_PRODUCT_IDENTITY_UNVERIFIED")
            actual = evaluate_single(quote, quote["samples"], quote["dataSize"])
        elif isinstance(quote.get("productCount"), int) and quote["productCount"] >= 2:
            if quote.get("pricingStatus") != "VERIFIED_MULTI_PRODUCT_LINES":
                return _block("NEW_MULTI_PRODUCT_SOURCE_UNVERIFIED")
            actual = evaluate_multi(quote, quote["samples"], quote["dataSize"])
        else:
            return _block("NEW_QUOTE_PRODUCT_COUNT_UNVERIFIED")
    except (PriceError, ValueError, TypeError, KeyError):
        return _block("NEW_QUOTE_PROCESS_RECONCILIATION_FAILED")
    for key in ("Product Net KRW", "Cloud Unit KRW", "Cloud Qty",
                "Cloud Net KRW", "Quote Net KRW", "VAT KRW", "Quote Gross KRW",
                "Product Price Items JSON"):
        if actual.get(key) != expected_prices.get(key):
            return _block("NEW_QUOTE_PRICING_LINES_MISMATCH")
    if actual.get("Cloud Qty") != prepared.get("expectedCloudUnits"):
        return _block("NEW_QUOTE_CLOUD_QUANTITY_MISMATCH")
    if expected_prices.get("Price Status") == "MANUAL_OVERRIDE_REVIEW_REQUIRED":
        return _block("OVERRIDE_REQUIRES_SEPARATE_APPROVAL")
    return {
        "status": "PASS", "code": "NEW_OPPORTUNITY_QUOTE_INDEPENDENT_READBACK",
        "verified": True, "salesforce_write": False,
        "new_opportunity_id": new_opportunity_id,
        "new_quote_id": new_quote_id,
        "net_krw": actual["Quote Net KRW"],
        "gross_krw": actual["Quote Gross KRW"],
        "cloud_qty": actual["Cloud Qty"],
    }
