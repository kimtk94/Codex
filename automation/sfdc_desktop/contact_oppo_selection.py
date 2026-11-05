#!/usr/bin/env python3
"""Fail-closed, local-only Contact selection for Oppo/Quote draft preparation.

No Salesforce access, no persistence, no automatic save. Input rows must be
retrieved from an authorized private source. Return IDs only to the local caller.
"""
import re
import unicodedata

EXCLUDED_ACCOUNTS = frozenset({"KAIST", "한국과학기술원", "한남대학교", "HANNAM UNIVERSITY", "한남대"})
ID_CONTACT = re.compile(r"003[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?\Z")
ID_ACCOUNT = re.compile(r"001[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?\Z")
ID_OPPORTUNITY = re.compile(r"006[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?\Z")


def normalize(value):
    return " ".join(unicodedata.normalize("NFKC", str(value or "")).casefold().split())


def excluded_account(name):
    name = normalize(name)
    # Exclusion is an identity gate, not a fuzzy substring match. In uncertain
    # cases do not auto-accept the account: select it explicitly in Salesforce.
    return name in {normalize(x) for x in EXCLUDED_ACCOUNTS}


def select_contact(name, rows, institution=None):
    """Exact normalized Korean-name selection, with Account disambiguation.

    Only contacts linked to at least one *verified* Opportunity are candidates.
    The caller must still check Salesforce current record identity and duplicates.
    """
    needle = normalize(name)
    if not needle:
        return {"status": "HOLD_NAME_REQUIRED", "candidates": []}
    if not isinstance(rows, list):
        return {"status": "HOLD_INVALID_SOURCE", "candidates": []}
    found = {}
    for row in rows:
        if not isinstance(row, dict) or normalize(row.get("name")) != needle:
            continue
        cid, aid = str(row.get("contact_id") or ""), str(row.get("account_id") or "")
        account = str(row.get("institution") or "")
        opps = row.get("opportunity_ids")
        if (not ID_CONTACT.fullmatch(cid) or not ID_ACCOUNT.fullmatch(aid)
                or not isinstance(opps, list) or not opps
                or not all(isinstance(i, str) and ID_OPPORTUNITY.fullmatch(i) for i in opps)
                or excluded_account(account)):
            continue
        if institution is not None and normalize(account) != normalize(institution):
            continue
        key = (cid, aid)
        found[key] = {"contact_id": cid, "account_id": aid,
                      "institution": account, "name": str(row.get("name"))}
    candidates = sorted(found.values(), key=lambda c: (normalize(c["institution"]), c["contact_id"]))
    if len(candidates) == 0:
        status = "HOLD_NO_ELIGIBLE_CONTACT"
    elif len(candidates) > 1:
        status = "HOLD_SELECT_EXACT_INSTITUTION_AND_CONTACT"
    else:
        status = "CANDIDATE_REQUIRES_LIVE_SFDC_VERIFICATION"
    return {"status": status, "candidates": candidates, "save_allowed": False}


def eligible_pair(case):
    """Keep only independently ID-linked, same single-service Oppo/Quote pairs."""
    if not isinstance(case, dict) or case.get("independent_link_verified") is not True:
        return "HOLD_UNVERIFIED_NATIVE_RELATION"
    if (not ID_OPPORTUNITY.fullmatch(str(case.get("opportunity_id") or ""))
            or str(case.get("quote_parent_opportunity_id") or "") != case["opportunity_id"]):
        return "HOLD_PARENT_RELATION_MISMATCH"
    if excluded_account(case.get("institution")):
        return "EXCLUDED_ACCOUNT"
    if case.get("service_count") != 1 or case.get("opportunity_service") != case.get("quote_service"):
        return "HOLD_MIXED_OR_MISMATCHED_SERVICES"
    if not case.get("opportunity_service"):
        return "HOLD_MISSING_SERVICE"
    return "ELIGIBLE_PATTERN_ONLY_NO_SAVE"
