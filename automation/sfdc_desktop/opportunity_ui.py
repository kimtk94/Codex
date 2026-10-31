"""Guarded Salesforce Lightning Opportunity UI helpers.

Locators must be verified on the user's actual Salesforce org and stored locally.
This module never clicks Save and never uses Salesforce APIs.
"""
from dataclasses import dataclass
from urllib.parse import urlsplit

REQUIRED = (
    "Opportunity Name", "Account Name", "Main Contact", "Amount",
    "Opportunity Currency", "Close Date", "Service Line", "Stage",
    "Forecast Category", "Progress Description", "Status",
)

@dataclass(frozen=True)
class LookupSpec:
    input_selector: str
    result_selector: str

def unique(page, selector, label):
    locator = page.locator(selector)
    if locator.count() != 1 or not locator.is_visible() or not locator.is_enabled():
        raise RuntimeError(f"{label}: selector not unique/visible/enabled")
    return locator

def select_lookup(page, spec: LookupSpec, query: str, expected_label: str):
    """Type query, then choose exactly one matching suggestion.

    Merely typing a name does not establish Salesforce relationship.
    """
    if not query or not expected_label:
        raise ValueError("Lookup query and exact expected label required")
    field = unique(page, spec.input_selector, "lookup input")
    field.fill(query)
    result = page.locator(spec.result_selector).filter(has_text=expected_label)
    if result.count() != 1 or result.inner_text().strip() != expected_label.strip():
        raise RuntimeError("Lookup result ambiguous or not exact")
    result.click()

def choose_service(page, available_selector, selected_selector, right_arrow_selector, service):
    """Move one validated service from Available to Chosen."""
    if not service:
        raise ValueError("Service cannot be empty")
    existing = page.locator(selected_selector).get_by_text(service, exact=True)
    if existing.count() == 1:
        return "ALREADY_CHOSEN"
    option = page.locator(available_selector).get_by_text(service, exact=True)
    if option.count() != 1:
        raise RuntimeError("Service unavailable/ambiguous: " + service)
    option.click()
    unique(page, right_arrow_selector, "move-right").click()
    if page.locator(selected_selector).get_by_text(service, exact=True).count() != 1:
        raise RuntimeError("Service did not move to Chosen")
    return "CHOSEN"

def audit_form_labels(page):
    """Only visible labels, never form values, are returned."""
    labels = [s.strip() for s in page.locator("label").all_text_contents()]
    labels = sorted({s for s in labels if s})
    return {"expected_required": list(REQUIRED),
            "observed_labels": labels,
            "unseen_required": [s for s in REQUIRED if s not in labels],
            "note": "Label visibility != Create permission; validate actual locators locally."}

def fill_guarded(page, data, config):
    """Fill text and explicit exact-match picklists; no save action."""
    fields = config.get("text", {})
    picklists = config.get("picklist", {})
    required_keys = {"Opportunity Name", "Amount", "Close Date"}
    if not required_keys.issubset(data):
        raise ValueError("Missing basic required fields")
    if not all(str(data[x]).strip() for x in required_keys):
        raise ValueError("Empty basic required field")
    for field, selector in fields.items():
        if field in data and str(data[field]).strip():
            unique(page, selector, field).fill(str(data[field]))
    for field, rule in picklists.items():
        if field not in data or not str(data[field]).strip():
            continue
        allowed = set(rule.get("allowed_values", []))
        if str(data[field]) not in allowed:
            raise ValueError("Unapproved picklist value for " + field)
        unique(page, rule["selector"], field).click()
        choice = page.locator(rule["option_selector"]).get_by_text(str(data[field]), exact=True)
        if choice.count() != 1:
            raise RuntimeError("Picklist choice not unique: " + field)
        choice.click()
    return "FORM_FILLED_NOT_SAVED"
