"""Read-only Lead Convert planning contract for the Korea Salesforce workflow.

Never calls Salesforce, never creates an Account/Contact/Opportunity and never
clicks Convert. Synthetic CI tests exercise the decision rules.
"""
import re
from dataclasses import asdict, dataclass

SFID = re.compile(r"^001[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?$")
ENGLISH_NAME = re.compile(r"^[A-Za-z][A-Za-z .'-]*$")


class ConversionHold(ValueError):
    """UI conversion must stop instead of guessing."""


@dataclass(frozen=True)
class AccountCandidate:
    record_id: str
    institution_name: str
    is_existing: bool = True


@dataclass(frozen=True)
class LeadConvertPreview:
    existing_account_id: str
    contact_first_name_korean: str
    contact_last_name_english: str
    create_account: bool = False
    create_contact: bool = True
    create_opportunity: bool = False
    no_opportunity_checkbox_checked: bool = True
    # Live conversion is explicitly blocked for all previews.
    submit_convert: bool = False


def plan_account_contact_only(
    candidates: list[AccountCandidate],
    selected_account_id: str,
    korean_name: str,
    english_name: str,
    *,
    existing_contact_match_count: int = 0,
    no_opportunity_checkbox_checked: bool = True,
    contact_create_new_checked: bool = True,
) -> dict:
    """Return a validated test-only conversion preview.

    Account must be a uniquely selected EXISTING Salesforce suggestion,
    not a typed string or the 'Create New' suggestion.
    First Name is Korean; Last Name is romanized English, matching a verified
    existing Salesforce Contact example.
    """
    matching = [
        item for item in candidates
        if item.record_id == selected_account_id and item.is_existing
    ]
    if len(matching) != 1 or not SFID.fullmatch(selected_account_id):
        raise ConversionHold("Select exactly one existing Account suggestion")
    if existing_contact_match_count:
        raise ConversionHold("Contact duplicate review required before creation")
    if not korean_name or not any("\uac00" <= c <= "\ud7a3" for c in korean_name):
        raise ConversionHold("Contact First Name must contain Korean characters")
    if not english_name or not ENGLISH_NAME.fullmatch(english_name):
        raise ConversionHold("Contact Last Name must be English romanization")
    if not no_opportunity_checkbox_checked:
        raise ConversionHold("Do not create an Opportunity during Lead Convert")
    if not contact_create_new_checked:
        raise ConversionHold("Contact Create New must be selected")
    plan = LeadConvertPreview(
        existing_account_id=selected_account_id,
        contact_first_name_korean=korean_name.strip(),
        contact_last_name_english=english_name.strip(),
    )
    return asdict(plan)
