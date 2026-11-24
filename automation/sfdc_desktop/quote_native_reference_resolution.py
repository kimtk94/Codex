"""Deterministic mapping of native SFDC reference records to Report IDs.

Safe pure helpers for the laptop's authenticated GET-only Source API reader.
No guesses from Process short codes, shared names, or Gb geometry.
"""
import re

_REPORT_ID = re.compile(r"^Process-[A-Za-z0-9-]{8,64}$")
_ALLOWED_UNITS = frozenset(("G raw data", "Gb", "M raw reads", "K tags",
                            "NA", "sample"))


def resolve_report_process_id(master_fields, expected_ids):
    """Only accept an exact Process-* identifier from the referenced master.

    Quotation_Process__c.Process_ID__c may be GY0001 or PR0019, which is a
    different namespace and must NEVER be cast to a Report Process ID.
    """
    if not isinstance(master_fields, dict) or not isinstance(expected_ids, (list, tuple, set)):
        return None
    expected = {x for x in expected_ids if isinstance(x, str) and _REPORT_ID.fullmatch(x)}
    candidates = {
        str(master_fields.get(key, ""))
        for key in ("Name", "Process_ID__c", "Process_Name__c",
                    "Original_Process_ID__c", "Process_External_ID__c")
        if isinstance(master_fields.get(key), str)
        and _REPORT_ID.fullmatch(master_fields[key])
    }
    if len(candidates) != 1:
        return None
    candidate = next(iter(candidates))
    return candidate if candidate in expected else None


def resolve_native_data_unit(value, display_value, picklist_values):
    """Require a source-defined label. In particular, NEVER guess that code 4 means Gb."""
    labels = set()
    if isinstance(value, str) and value in _ALLOWED_UNITS:
        labels.add(value)
    if isinstance(display_value, str) and display_value in _ALLOWED_UNITS:
        labels.add(display_value)
    if isinstance(picklist_values, list):
        entries = [
            x for x in picklist_values
            if isinstance(x, dict) and str(x.get("value")) == str(value)
            and isinstance(x.get("label"), str)
            and x["label"] in _ALLOWED_UNITS
        ]
        labels.update(x["label"] for x in entries)
    return next(iter(labels)) if len(labels) == 1 else None


def resolve_product_service(master_fields):
    """Only a directly retrieved SFDC Product master name, not process geometry."""
    if not isinstance(master_fields, dict):
        return None
    value = master_fields.get("Name")
    if not isinstance(value, str) or not value.strip() or len(value) > 200:
        return None
    return value.strip()


def resolve_reference_status(*, resolved_process_rows, expected_rows,
                             verified_service_labels, expected_product_count):
    """Classify source reference completeness without price promotion."""
    result = {
        "status": "HOLD_REFERENCE_SOURCE_INCOMPLETE",
        "original_process_rows_verified": 0,
        "product_service_name_verified": False,
        "historical_price_index_promoted": False,
        "new_quote_price_approved": False,
        "salesforce_write": False,
        "save_permitted": False,
    }
    if not isinstance(resolved_process_rows, list) or not isinstance(expected_rows, list):
        return result
    if not isinstance(expected_product_count, int) or not 1 <= expected_product_count <= 12:
        return result
    if not isinstance(verified_service_labels, list) or (
        len(verified_service_labels) != expected_product_count
    ) or any(not isinstance(x, str) or not x.strip() for x in verified_service_labels):
        result["status"] = "HOLD_PRODUCT_SERVICE_MASTER_UNRESOLVED"
        return result
    if len(resolved_process_rows) != len(expected_rows) or not resolved_process_rows:
        result["status"] = "HOLD_PROCESS_REFERENCE_ROW_COUNT"
        return result
    # Each child must carry its exact original product AND Process ID; multiple
    # Products may share a Process ID. No matching by process name alone.
    def identity(row):
        return (row.get("quotation_product_id"), row.get("process_id")) if isinstance(row, dict) else None
    keys = [identity(x) for x in resolved_process_rows]
    expected_keys = [identity(x) for x in expected_rows]
    if (None in keys or None in expected_keys or len(keys) != len(set(keys)) or
        len(expected_keys) != len(set(expected_keys)) or set(keys) != set(expected_keys)):
        result["status"] = "HOLD_PROCESS_REFERENCE_ID_MISMATCH"
        return result
    result["status"] = "SOURCE_REFERENCES_RESOLVED_RATE_PROMOTION_REQUIRES_REVIEW"
    result["original_process_rows_verified"] = len(keys)
    result["product_service_name_verified"] = True
    return result



def resolve_2026_native_krw_product_signature(source_service_name, index_rows):
    """Only match an exact native Product master service name to ONE 2026 signature.

    Different products can have identical Process layouts. Matching Process
    geometry, Gb, an approximate label, or converted USD is never accepted.
    This resolves historical comparison identity ONLY, not rate approval.
    """
    if (not isinstance(source_service_name, str) or not source_service_name.strip()
        or not isinstance(index_rows, list)):
        return None
    signatures = {
        row.get("product_signature")
        for row in index_rows if isinstance(row, dict)
        and row.get("product_name") == source_service_name
        and row.get("currency") == "KRW"
        and row.get("was_usd_converted") is False
        and row.get("approval_status") == "APPROVED"
        and row.get("active") is True
        and isinstance(row.get("created_date"), str)
        and row["created_date"].startswith("2026-")
        and isinstance(row.get("product_signature"), str)
    }
    return next(iter(signatures)) if len(signatures) == 1 else None
