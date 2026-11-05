"""Pure validation rules for SFDC Lead -> Contact -> CDMS.

No Salesforce access, network requests or write side effects in this module.
The browser runner must verify all gates before any Save/Convert/Sync click.
"""

from dataclasses import dataclass
import re


ACADEMIC_PI = "ACADEMIC:Principle Investigator (PI) – Independent researcher"


@dataclass(frozen=True)
class LeadContactPlan:
    first_name: str
    last_name: str
    account_id: str
    org_type: str
    job_function: str
    shipping_street: str
    shipping_city: str
    shipping_state: str
    shipping_postal_code: str
    shipping_country: str
    create_opportunity: bool = False


def english_full_name(surname: str, given_name_syllables: list[str]) -> str:
    """Build surname-first English name with no whitespace, e.g. OhJunHyeok.

    Inputs must be independently verified romanizations; do not infer spelling
    from a Korean name or from an email address.
    """
    if not surname or not given_name_syllables:
        raise ValueError("A surname and one or more given-name syllables are required")
    parts = [surname, *given_name_syllables]
    if any(not re.fullmatch(r"[A-Za-z]+", p or "") for p in parts):
        raise ValueError("Romanized surname and given-name syllables are required")
    return "".join(part[:1].upper() + part[1:].lower() for part in parts)


def build_contact_plan(
    *,
    korean_full_name: str,
    romanized_surname: str,
    romanized_given_syllables: list[str],
    verified_account_id: str,
    account_address: dict[str, str],
    org_type: str,
    job_options: list[str],
) -> LeadContactPlan:
    """Prepare a safe Contact plan from an already selected existing Account.

    The first Job Function *in the live option list* is selected, skipping
    blank/None placeholders. Academic must resolve to the PI option.
    """
    name = korean_full_name.strip()
    if not re.fullmatch(r"[가-힣]{2,6}", name):
        raise ValueError("Full Korean name is required")
    if len(romanized_given_syllables) != len(name) - 1:
        raise ValueError("Romanized given-name syllable count must match the Korean name")
    if not re.fullmatch(r"001[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?", verified_account_id):
        raise ValueError("A verified Salesforce Account ID is required")
    if not job_options:
        raise ValueError("Job Function choices must come from the live UI")
    first_option = next((j for j in job_options if j and j.strip() and j.strip() not in {"--None--", "-- None --"}), None)
    if not first_option:
        raise ValueError("No valid Job Function option")
    if org_type == "Academic" and first_option != ACADEMIC_PI:
        raise ValueError("Academic Job Function first choice must be PI")
    required = ("street", "city", "postal_code", "country")
    if any(not account_address.get(k, "").strip() for k in required):
        raise ValueError("Account address missing a required component; do not guess")
    return LeadContactPlan(
        first_name=name,
        last_name=english_full_name(romanized_surname, romanized_given_syllables),
        account_id=verified_account_id,
        org_type=org_type,
        job_function=first_option,
        shipping_street=account_address["street"].strip(),
        shipping_city=account_address["city"].strip(),
        shipping_state=account_address.get("state", "").strip(),
        shipping_postal_code=account_address["postal_code"].strip(),
        shipping_country=account_address["country"].strip(),
    )


def cdms_sync_verified(*, sync_message: str, cms_contact_id: str) -> bool:
    """Success toast alone is insufficient: require a persisted CMS contact ID."""
    return (
        sync_message.strip() == "Sync completed"
        and bool(re.fullmatch(r"CP[0-9]+", cms_contact_id.strip()))
    )
