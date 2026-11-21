"""Oppo/Quote exact-name learning filter, without any Salesforce writes.

All identical Opportunity/Quotation name pairs with unique Opportunity IDs
can supply naming and linking examples, regardless of Quote Product count.
Only exactly ONE Quote Product permits the basic form dry-run template.
Multi-product or productless quotes never enter the basic product builder.
Ambiguous name links are excluded altogether. Private snapshots stay on PC.
"""

import re
from dataclasses import dataclass

AMEA_SUFFIX = re.compile(r"^(?P<oppo_name>.+)-(?P<quote_no>AMEA\d{8,}(?:-\d+)?)$")
SFID_OPPO = re.compile(r"^006[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?$")
SFID_QUOTE = re.compile(r"^a0P[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?$")
SFID_ACCOUNT = re.compile(r"^001[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?$")
SFID_CONTACT = re.compile(r"^003[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?$")


# Explicitly excluded accounts. Match only the institution segment of an
# Opportunity name, not unrelated free-text service or investigator fields.
# Future authenticated execution must also inspect the actual Account ID/name.
EXCLUDED_ACCOUNT_ALIASES = {
    "KAIST": ("kaist", "한국과학기술원", "korea advanced institute of science"),
    "HANNAM": ("hannam univ", "hannam university", "한남대학교", "한남대"),
}


def excluded_account_reason(opportunity_name: str) -> str | None:
    """Return an explicit institution skip code for disallowed examples."""
    if not isinstance(opportunity_name, str):
        return None
    name = re.sub(r"\s+", " ", opportunity_name).strip().casefold()
    # For standard Korea-Institution-service Opportunity names, only the
    # institution segment may determine account identity.
    institutional = name.split("-", 2)[1].strip() if name.startswith("korea-") and "-" in name else name.split("-", 1)[0].strip()
    for key, aliases in EXCLUDED_ACCOUNT_ALIASES.items():
        if any(
            institutional == alias
            or institutional.startswith(alias + " ")
            or institutional.startswith(alias + ".")
            for alias in aliases
        ):
            return "EXCLUDED_ACCOUNT_" + key
    return None


class ManualReview(ValueError):
    """Insufficient evidence for unattended Quote replication."""


@dataclass(frozen=True)
class OpportunitySnapshot:
    record_id: str
    name: str


@dataclass(frozen=True)
class QuoteSnapshot:
    record_id: str
    name: str
    quote_number: str
    opportunity_name: str
    product_record_count: int


def match_identical_name_quote(
    quote: QuoteSnapshot, opportunity_rows: list[OpportunitySnapshot]
) -> dict:
    """Validate naming/link identity, even when the quote has multiple products."""
    skip_reason = excluded_account_reason(quote.opportunity_name)
    if skip_reason:
        raise ManualReview(skip_reason)
    if not SFID_QUOTE.fullmatch(quote.record_id):
        raise ManualReview("Invalid Quote ID")
    match = AMEA_SUFFIX.fullmatch(quote.name)
    if match is None:
        raise ManualReview("Quote name lacks final AMEA number")
    if match.group("quote_no") != quote.quote_number:
        raise ManualReview("Quote number does not match name suffix")
    base_name = match.group("oppo_name")
    if base_name != quote.opportunity_name:
        raise ManualReview("Quote and Opportunity names differ")
    matches = [
        o for o in opportunity_rows
        if o.name == base_name and SFID_OPPO.fullmatch(o.record_id)
    ]
    if len(matches) != 1:
        raise ManualReview("Missing or ambiguous Opportunity")
    return {
        "source_quote_id": quote.record_id,
        "source_opportunity_id": matches[0].record_id,
        "opportunity_name": base_name,
        "quotation_name": quote.name,
        "quote_number": quote.quote_number,
        "product_record_count": quote.product_record_count,
        "learning_scope": "NAME_AND_PARENT_ONLY",
        "requires_live_parent_identity_check": True,
        "save_clicked": False,
        "create_opportunity": False,
        "create_quote": False,
        "send_quote": False,
    }



def match_single_product_quote(
    quote: QuoteSnapshot, opportunity_rows: list[OpportunitySnapshot]
) -> dict:
    """Permit basic form rehearsal only for unambiguous one-product pairs."""
    candidate = match_identical_name_quote(quote, opportunity_rows)
    if candidate["product_record_count"] != 1:
        raise ManualReview("Expected exactly one Quote Product for basic dry-run")
    candidate["learning_scope"] = "SINGLE_PRODUCT_DRY_RUN"
    return candidate


def verify_live_quotation_relationship(candidate: dict, evidence: dict | None) -> bool:
    """Fail closed before using a real SFDC Quotation as an automation example.

    The caller must independently read the source Quotation__c Details,
    its linked Opportunity Details, and the Contact's current Account from
    authenticated Salesforce Lightning. Names and stale Sheets cannot replace
    these IDs. This function never talks to Salesforce or writes records.

    Salesforce Quote is a custom `Quotation__c` object, not standard Quote.
    """
    if not isinstance(candidate, dict) or not isinstance(evidence, dict):
        raise ManualReview("Missing direct Lightning relationship evidence")
    if evidence.get("source") != "SFDC_LIGHTNING_DETAIL":
        raise ManualReview("Unverified Salesforce relationship source")
    if evidence.get("quote_object") != "Quotation__c":
        raise ManualReview("Expected custom Quotation__c, not standard Quote")

    validations = {
        "quotation_record_id": SFID_QUOTE,
        "parent_opportunity_id": SFID_OPPO,
        "quotation_account_id": SFID_ACCOUNT,
        "opportunity_account_id": SFID_ACCOUNT,
        "quotation_contact_id": SFID_CONTACT,
        "opportunity_main_contact_id": SFID_CONTACT,
        "contact_account_id": SFID_ACCOUNT,
    }
    for key, pattern in validations.items():
        if not pattern.fullmatch(str(evidence.get(key) or "")):
            raise ManualReview("Missing or invalid Salesforce relationship: " + key)

    if evidence["quotation_record_id"] != candidate.get("source_quote_id"):
        raise ManualReview("Quotation record ID differs from selected example")
    if evidence["parent_opportunity_id"] != candidate.get("source_opportunity_id"):
        raise ManualReview("Quotation actual parent differs from selected Opportunity")
    accounts = (
        evidence["quotation_account_id"],
        evidence["opportunity_account_id"],
        evidence["contact_account_id"],
    )
    if len(set(accounts)) != 1:
        raise ManualReview("Quotation/Opportunity/Contact Account IDs differ")
    if evidence["quotation_contact_id"] != evidence["opportunity_main_contact_id"]:
        raise ManualReview("Quotation Contact differs from Opportunity Main Contact")
    return True


def dryrun_after_read_only_identity_check(
    candidate: dict, actual_parent_opportunity_id: str,
    *, relationship_evidence: dict | None = None,
) -> dict:
    """Allow form rehearsal ONLY after Salesforce's actual parent link matches."""
    if not candidate.get("requires_live_parent_identity_check"):
        raise ManualReview("Missing live identity-check requirement")
    if actual_parent_opportunity_id != candidate.get("source_opportunity_id"):
        raise ManualReview("Actual parent Opportunity differs from list inference")
    if candidate.get("product_record_count") != 1:
        raise ManualReview("Complex-product Quote cannot use basic form rehearsal")
    if candidate.get("save_clicked") or candidate.get("create_quote"):
        raise ManualReview("This workflow must remain NO-SAVE")
    verify_live_quotation_relationship(candidate, relationship_evidence)
    return {
        **candidate,
        "actual_parent_verified": True,
        "actual_quotation_account_contact_verified": True,
        "mode": "FORM_DRY_RUN_NO_SAVE",
        "save_clicked": False,
        "create_quote": False,
        "create_opportunity": False,
        "send_quote": False,
    }



def validate_opportunity_clone_preflight(
    visible_page_text: str,
    *,
    name_input_visible: bool,
    main_contact_link_verified: bool,
) -> bool:
    """Block UI rehearsal if Salesforce cannot resolve the original Contact.

    A source Opportunity might remain readable even when its Clone form
    fails on an invalid or inaccessible Main Contact lookup. A missing field
    must not be treated as a transient timeout or bypassed by a guessed
    replacement Contact. Caller verifies Contact access independently.
    """
    if not isinstance(visible_page_text, str):
        raise ManualReview("Opportunity Clone page is not readable")
    error_tokens = (
        "Unable to find the record referenced by Opportunity.Main_Contact__c",
        "Looks like there's a problem.",
    )
    if any(token in visible_page_text for token in error_tokens):
        raise ManualReview("Salesforce Clone error: unresolved Contact or form")
    if not name_input_visible:
        raise ManualReview("Opportunity Clone Name field unavailable")
    if not main_contact_link_verified:
        raise ManualReview("Opportunity Main Contact not independently verified")
    return True
