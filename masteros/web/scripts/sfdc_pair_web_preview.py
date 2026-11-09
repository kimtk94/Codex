"""Read-only local web bridge for Salesforce-linked Opportunity/Quote pricing.

All Salesforce reads happen on an authenticated operator PC. The browser never
supplies authoritative pricing or customer identities, and there is no SAVE
mode, CRM write action, or Feishu mutation in this module.
"""
import json
import re
import sys

from feishu_sfdc_local_worker import prepare_pair, process
from sfdc_pair_readback import read_live_saved_pair

MAX_INPUT = 5000
ID_RE = {
    "006": re.compile(r"006[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?\Z"),
    "a0P": re.compile(r"a0P[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?\Z"),
}


def _blocked(code):
    return {"status": "BLOCK", "code": code, "salesforce_write": False}


def _id(value, prefix):
    return isinstance(value, str) and ID_RE[prefix].fullmatch(value) is not None


def _nonnegative_rate(value):
    if value in ("", None):
        return ""
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 1_000_000_000:
        raise ValueError("RATE_INVALID")
    return str(value)


def validate_input(req):
    if not isinstance(req, dict) or isinstance(req, list):
        raise ValueError("INVALID_REQUEST")
    mode = req.get("mode")
    if mode not in ("CHECK_PRICE", "CHECK_FORMS", "CHECK_READBACK"):
        raise ValueError("READ_ONLY_MODE_REQUIRED")
    if req.get("runMode") not in (None, "CHECK"):
        raise ValueError("SAVE_NOT_SUPPORTED")
    if not _id(req.get("sourceOpportunityId"), "006") or not _id(req.get("sourceQuoteId"), "a0P"):
        raise ValueError("SOURCE_IDS_INVALID")
    name = req.get("newOpportunityName")
    if not isinstance(name, str) or not 5 <= len(name.strip()) <= 230 or name != name.strip():
        raise ValueError("OPPORTUNITY_NAME_INVALID")
    samples = req.get("samples")
    size = req.get("dataSizeGb")
    if not isinstance(samples, int) or isinstance(samples, bool) or not 1 <= samples <= 500:
        raise ValueError("SAMPLE_COUNT_INVALID")
    if isinstance(size, bool) or not isinstance(size, (int, float)) or not 0 < size <= 100000:
        raise ValueError("DATA_SIZE_INVALID")
    from math import isfinite
    if not isfinite(size):
        raise ValueError("DATA_SIZE_INVALID")
    product_rate = _nonnegative_rate(req.get("productUnitOverrideKrw"))
    cloud_rate = _nonnegative_rate(req.get("cloudUnitOverrideKrw"))
    new_id = req.get("newOpportunityId")
    if mode == "CHECK_READBACK":
        if not _id(new_id, "006") or new_id == req["sourceOpportunityId"]:
            raise ValueError("NEW_OPPORTUNITY_ID_INVALID")
    elif new_id not in (None, ""):
        raise ValueError("READBACK_ID_NOT_EXPECTED")
    return {
        "mode": mode,
        "x": {
            "Action": "OPPO_QUOTE_PAIR",
            "Run Mode": "CHECK",
            "Source Oppo ID": req["sourceOpportunityId"],
            "Source Quote ID": req["sourceQuoteId"],
            "New Opportunity Name": name,
            "New Samples": str(samples),
            "Data Size Gb": str(size),
            "Requested Product Unit KRW": product_rate,
            "Requested Cloud Unit KRW": cloud_rate,
        },
        "new_id": new_id,
    }


def run(req):
    try:
        parsed = validate_input(req)
    except ValueError as exc:
        return _blocked(str(exc))
    mode, x = parsed["mode"], parsed["x"]
    if mode == "CHECK_FORMS":
        result = process(x)
        return {
            "status": result.get("status", "BLOCK"),
            "code": result.get("code") or "FORM_PREFLIGHT_INCOMPLETE",
            "pricing": result.get("price_fields") or {},
            "scope": "REFERENCE_OPPORTUNITY_QUOTE_FORMS_ONLY",
            "salesforce_write": False,
            "save_permitted": False,
        }
    prepared = prepare_pair(x)
    if prepared.get("status") not in ("READY", "PRICE_ONLY"):
        return _blocked(prepared.get("code") or "SOURCE_PRICE_UNVERIFIED")
    pricing = prepared.get("price_fields") or {}
    if mode == "CHECK_PRICE":
        return {
            "status": "PREVIEW_READY" if prepared["status"] == "READY" else "HOLD",
            "code": prepared.get("code") or "PRICING_VALIDATED",
            "pricing": pricing,
            "scope": "SOURCE_QUOTE_PROJECTION_ONLY",
            "salesforce_write": False,
            "save_permitted": False,
        }
    if prepared["status"] != "READY":
        return _blocked("MULTI_PRODUCT_NEW_PAIR_READBACK_NOT_SUPPORTED")
    result = read_live_saved_pair(prepared, parsed["new_id"])
    return {
        "status": result.get("status", "BLOCK"),
        "code": result.get("code") or "READBACK_NOT_VERIFIED",
        "pricing": pricing,
        "readback": {
            "verified": result.get("verified") is True,
            "new_opportunity_id": result.get("new_opportunity_id") or "",
            "new_quote_id": result.get("new_quote_id") or "",
            "net_krw": result.get("net_krw"),
            "gross_krw": result.get("gross_krw"),
            "cloud_qty": result.get("cloud_qty"),
        },
        "scope": "INDEPENDENT_EXISTING_SAVED_PAIR_READBACK_ONLY",
        "salesforce_write": False,
        "save_permitted": False,
    }


def main():
    try:
        raw = sys.stdin.buffer.read(MAX_INPUT + 1)
        if not raw or len(raw) > MAX_INPUT:
            result = _blocked("REQUEST_TOO_LARGE")
        else:
            result = run(json.loads(raw.decode("utf-8")))
    except (UnicodeError, ValueError, TypeError):
        result = _blocked("INVALID_JSON")
    except Exception:
        # Fail closed and never leak raw Salesforce data or credentials.
        result = _blocked("LOCAL_SOURCE_UNAVAILABLE")
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
