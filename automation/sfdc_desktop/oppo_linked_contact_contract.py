"""Read-only learning index for Contacts referenced by existing Opportunities.

No Salesforce API calls, no file I/O, no writes. The authenticated desktop
owns private records. GitHub Actions tests *synthetic* records only.
"""

import re
from collections import defaultdict

SF_CONTACT = re.compile(r"^003[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?$")
SF_ACCOUNT = re.compile(r"^001[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?$")
SF_OPPO = re.compile(r"^006[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?$")
KOREAN_NAME = re.compile(r"^[가-힣]{2,20}$")
EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def excluded_institution(institution: str) -> str | None:
    name = (institution or "").casefold()
    if any(s in name for s in ("kaist", "한국과학기술원", "korea advanced institute of science")):
        return "SKIP_KAIST"
    if any(s in name for s in ("hannam university", "hannam univ", "한남대학교", "한남대")):
        return "SKIP_HANNAM"
    return None


def make_oppo_linked_contact_index(edges: list[dict], contact_details: dict[str, dict]) -> dict:
    """Return only verified Oppo-linked Contacts and a separate HOLD/SKIP ledger.

    edges: each has existing oppo_id, main_contact_id, account_id and
    institution_name read from Opportunity.Detail references. Entries without
    valid real record IDs cannot become searchable or actionable.
    contact_details: keyed by Contact ID. Each value has 'korean_name',
    'email' and a current 'account_id' read from the Contact record.

    The server MUST recheck all links before acting; this merely prepares a
    review index, not permission to create or Save a record.
    """
    by_contact = defaultdict(list)
    holds = []
    skips = []
    for edge in edges:
        oppo = str(edge.get("oppo_id", ""))
        contact = str(edge.get("main_contact_id", ""))
        account = str(edge.get("account_id", ""))
        institution = str(edge.get("institution_name", ""))
        if not SF_OPPO.fullmatch(oppo) or not SF_CONTACT.fullmatch(contact) or not SF_ACCOUNT.fullmatch(account):
            holds.append({"oppo_id": oppo, "status": "HOLD_INVALID_REFERENCE"})
            continue
        skip = excluded_institution(institution)
        if skip:
            skips.append({"oppo_id": oppo, "status": skip})
            continue
        by_contact[contact].append({
            "oppo_id": oppo, "account_id": account, "institution_name": institution
        })
    index = []
    for contact_id, records in by_contact.items():
        accounts = {r["account_id"] for r in records}
        if len(accounts) != 1:
            holds.append({"contact_id": contact_id, "status": "HOLD_CONFLICTING_OPPO_ACCOUNTS"})
            continue
        detail = contact_details.get(contact_id)
        if not detail:
            holds.append({"contact_id": contact_id, "status": "HOLD_CONTACT_DETAILS_NOT_VERIFIED"})
            continue
        actual_account = detail.get("account_id", "")
        if not SF_ACCOUNT.fullmatch(str(actual_account)) or actual_account not in accounts:
            holds.append({"contact_id": contact_id, "status": "HOLD_CONTACT_ACCOUNT_RELATIONSHIP"})
            continue
        korean_name = str(detail.get("korean_name", "")).strip().replace(" ", "")
        email = str(detail.get("email", "")).strip()
        if not KOREAN_NAME.fullmatch(korean_name) or not EMAIL.fullmatch(email):
            holds.append({"contact_id": contact_id, "status": "HOLD_KOREAN_NAME_OR_EMAIL"})
            continue
        institution = next(r["institution_name"] for r in records)
        oppo_ids = sorted({r["oppo_id"] for r in records})
        index.append({
            "contact_id": contact_id, "account_id": actual_account,
            "institution_name": institution, "korean_name": korean_name,
            "email": email, "linked_opportunity_ids": oppo_ids,
            "state": "CONTACT_RECHECK_REQUIRED", "save_allowed": False,
        })

    # Same-name people in a single Account must never be silently selected.
    by_name_account = defaultdict(list)
    for row in index:
        by_name_account[(row["korean_name"], row["account_id"])].append(row["contact_id"])
    dup_ids = {
        contact_id
        for group in by_name_account.values() if len(group) > 1
        for contact_id in group
    }
    if dup_ids:
        index = [r for r in index if r["contact_id"] not in dup_ids]
        holds.extend({
            "contact_id": c, "status": "HOLD_SAME_NAME_SAME_ACCOUNT"
        } for c in sorted(dup_ids))
    return {
        "index": sorted(index, key=lambda r: (r["korean_name"], r["institution_name"], r["contact_id"])),
        "hold": holds, "skip": skips,
        "no_save": True,
    }
