"""Pure read-only identity rules for Oppo-linked Contact learning."""

import re


class OppoContactHold(ValueError):
    pass


def eligible_contact(opportunity, contact):
    """Only verified Opportunity Main Contact and Account links qualify."""
    opp_id = opportunity.get("opportunity_id", "")
    main_id = opportunity.get("main_contact_id", "")
    opp_account_id = opportunity.get("account_id", "")
    contact_id = contact.get("contact_id", "")
    contact_account_id = contact.get("account_id", "")

    for value, prefix in (
        (opp_id, "006"), (main_id, "003"), (contact_id, "003"),
        (opp_account_id, "001"), (contact_account_id, "001"),
    ):
        if not isinstance(value, str) or len(value) != 18 or not value.startswith(prefix) or not value.isalnum():
            raise OppoContactHold("INVALID_OR_MISSING_SALESFORCE_ID")

    if main_id != contact_id:
        raise OppoContactHold("MAIN_CONTACT_ID_MISMATCH")
    if opp_account_id != contact_account_id:
        raise OppoContactHold("CONTACT_ACCOUNT_ID_MISMATCH")

    institution = (contact.get("institution_name") or "").casefold()
    if not institution:
        raise OppoContactHold("MISSING_INSTITUTION")
    if any(term in institution for term in ("kaist", "한국과학기술원", "hannam", "한남대학교", "한남대")):
        raise OppoContactHold("EXCLUDED_ACCOUNT")

    korean_name = (contact.get("korean_name") or "").strip()
    if not re.fullmatch(r"[가-힣]{2,20}", korean_name):
        raise OppoContactHold("INVALID_KOREAN_NAME")
    email = (contact.get("email") or "").strip()
    if "@" not in email or email.startswith("@") or email.endswith("@"):
        raise OppoContactHold("MISSING_CONTACT_EMAIL")

    return {
        "contact_id": contact_id,
        "account_id": contact_account_id,
        "korean_name": korean_name,
        "institution_name": contact["institution_name"],
        "email": email,
        "linked_opportunity_ids": [opp_id],
        "status": "VERIFIED_SOURCE_LINKS_RECHECK_REQUIRED",
        "save_clicked": False,
    }
