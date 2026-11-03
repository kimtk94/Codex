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
    if not isinstance(korean_name, str) or not isinstance(english_name, str):
        raise ConversionHold("Contact names must be strings")
    korean_name = korean_name.strip()
    english_name = english_name.strip()
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


def recommend_existing_account(
    candidates: list[AccountCandidate], company: str
) -> str:
    """Choose a verified existing Account with a Kyungpook-specific default.

    For an ordinary Kyungpook National University Lead, prefer its existing
    R&DB Foundation (경북대학교 산학협력단) record. A lead explicitly mentioning
    the Next-Generation Sequencing Core or the University Hospital must only
    match the corresponding unit. In all cases the option must exist uniquely
    among actual Salesforce recommendations; never create a new Account.
    """
    if not isinstance(company, str) or len(company.strip()) < 3:
        raise ConversionHold("Lead company is missing or too broad for matching")
    needle = company.strip().casefold()
    existing = [
        c for c in candidates
        if c.is_existing
        and isinstance(c.institution_name, str)
        and isinstance(c.record_id, str)
        and SFID.fullmatch(c.record_id)
    ]

    is_kyungpook = (
        "경북대" in needle
        or "kyungpook national univ" in needle
        or needle == "kyungpook"
    )
    if is_kyungpook:
        # Treat a stated sub-organization as an identity constraint, not a
        # soft preference. Otherwise use the Foundation as the default.
        if any(marker in needle for marker in (
            "핵심연구지원센터", "차세대시퀀싱", "core", "next-generation sequencing"
        )):
            markers = ("핵심연구지원센터", "core research support center")
        elif any(marker in needle for marker in ("병원", "hospital", "medical center")):
            markers = ("경북대학교병원", "kyungpook national university hospital")
        else:
            markers = ("경북대학교 산학협력단", "r&db foundation")
        matching = [
            c for c in existing
            if "경북대" in c.institution_name.casefold()
            or "kyungpook" in c.institution_name.casefold()
        ]
        matching = [
            c for c in matching
            if any(marker in c.institution_name.casefold() for marker in markers)
        ]
    else:
        matching = [
            c for c in existing if needle in c.institution_name.casefold()
        ]
    if len(matching) != 1:
        raise ConversionHold("Missing or ambiguous existing Account recommendation")
    return matching[0].record_id
