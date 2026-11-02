"""Fail-closed header audit for SFDC Quotation report mirroring.

A stale or mislabeled source tab containing Opportunity columns must never be
treated as Quotation relationship evidence. Pure module; no Salesforce or Sheets IO.
"""

FIELD_GROUPS = {
    "SFDC quotation record ID": (
        "SFDC Quotation ID", "Salesforce Quotation ID", "Quote Record ID",
    ),
    "quotation business ID": ("Quotation ID", "AMEA No.", "AMEA ID"),
    "related opportunity ID": ("Opportunity ID", "OpportunityId", "Opportunity: ID"),
    "active checkbox": ("IsActive", "Is Active", "Active", "Is Active Quote"),
}


def missing_quotation_columns(header):
    normalized = {str(value).strip().casefold() for value in (header or [])}
    return [label for label, choices in FIELD_GROUPS.items()
            if not any(option.casefold() in normalized for option in choices)]


def validate_quotation_columns(header):
    missing = missing_quotation_columns(header)
    if missing:
        raise ValueError(
            "Quotation source schema invalid; refusing downstream Sheet writes: "
            + ", ".join(missing)
        )
    return True
