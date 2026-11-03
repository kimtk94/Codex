"""Oppo/Quote exact-name learning filter, without any Salesforce writes.

Only identical Opportunity/Quotation names (ignoring one final -AMEA number)
with a unique existing Opportunity and exactly one Quote Product are eligible
for a simple-product dry-run template. All ambiguous and multi-product cases
go to manual review. List snapshots must remain PRIVATE on the user's PC.
"""

import re
from dataclasses import dataclass, asdict

AMEA_SUFFIX = re.compile(r"^(?P<oppo_name>.+)-(?P<quote_no>AMEA\d{8,}(?:-\d+)?)$")
SFID_OPPO = re.compile(r"^006[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?$")
SFID_QUOTE = re.compile(r"^a0P[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?$")


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


def match_single_product_quote(
    quote: QuoteSnapshot, opportunity_rows: list[OpportunitySnapshot]
) -> dict:
    """Validate the candidate based on existing, read-only list snapshots."""
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
    if quote.product_record_count != 1:
        raise ManualReview("Expected exactly one Quote Product")
    return {
        "source_quote_id": quote.record_id,
        "source_opportunity_id": matches[0].record_id,
        "opportunity_name": base_name,
        "quotation_name": quote.name,
        "quote_number": quote.quote_number,
        "product_record_count": 1,
        "requires_live_parent_identity_check": True,
        "save_clicked": False,
        "create_opportunity": False,
        "create_quote": False,
        "send_quote": False,
    }


def dryrun_after_read_only_identity_check(
    candidate: dict, actual_parent_opportunity_id: str
) -> dict:
    """Allow form rehearsal ONLY after Salesforce's actual parent link matches."""
    if not candidate.get("requires_live_parent_identity_check"):
        raise ManualReview("Missing live identity-check requirement")
    if actual_parent_opportunity_id != candidate.get("source_opportunity_id"):
        raise ManualReview("Actual parent Opportunity differs from list inference")
    if candidate.get("save_clicked") or candidate.get("create_quote"):
        raise ManualReview("This workflow must remain NO-SAVE")
    return {
        **candidate,
        "actual_parent_verified": True,
        "mode": "FORM_DRY_RUN_NO_SAVE",
        "save_clicked": False,
        "create_quote": False,
        "create_opportunity": False,
        "send_quote": False,
    }
