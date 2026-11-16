#!/usr/bin/env python3
"""Local-only read-only SFDC Contact search, backed by verified 2026 KRW Quote identities.

Discovery is strictly scoped to already-verified original-KRW 2026 Quote contacts
in a private local index. Each result is LIVE rechecked in authenticated Salesforce:
Quote -> Account(001), Contact(003), Opportunity(006), and Contact -> Account/email.
No CRM Save, API mutations, refresh token copying, remote upload or price application.
"""
import datetime as dt
import json
import os
from pathlib import Path
import re
import sys
import unicodedata

BASE = "https://novogene.lightning.force.com"
A = re.compile(r"^001[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?$")
C = re.compile(r"^003[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?$")
O = re.compile(r"^006[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?$")
Q = re.compile(r"^QID-2026-\d{2}-\d{2}-[0-9]{4,}$")
R = re.compile(r"^a0P[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?$")
EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
VERSION = "sfdc-2026-krw-oppo-contact-index-v1"
SOURCE = "SFDC_AUTHENTICATED_QUOTE_AND_CONTACT_READ_ONLY"


def path_for_index():
    configured = os.getenv("SFDC_LOCAL_KRW_CONTACT_INDEX", "")
    if configured:
        return Path(configured)
    local = os.getenv("LOCALAPPDATA", "")
    return (Path(local) / "SFDC_KRW_Price" / "native_contact_verified_private.json"
            if local else Path.home() / ".sfdc_desktop" / "native_contact_verified_private.json")


def normalized_name(name):
    return unicodedata.normalize("NFKC", name).strip().replace(" ", "") if isinstance(name, str) else ""


def validate_query(request):
    if not isinstance(request, dict) or set(request) - {"query", "limit", "accountId"}:
        raise ValueError("REQUEST_FIELDS_INVALID")
    name = normalized_name(request.get("query"))
    if not re.fullmatch(r"[\uAC00-\uD7A3]{2,20}", name):
        raise ValueError("KOREAN_NAME_REQUIRED")
    limit = request.get("limit")
    account = request.get("accountId", "")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 10:
        raise ValueError("RESULT_LIMIT_INVALID")
    if not isinstance(account, str) or (account and not A.fullmatch(account)):
        raise ValueError("ACCOUNT_ID_INVALID")
    return name, limit, account


def select_candidates(document, request, now=None):
    name, limit, account = validate_query(request)
    if not isinstance(document, dict) or document.get("version") != VERSION or \
            document.get("source") != SOURCE or document.get("salesforce_write_performed") is not False:
        raise ValueError("UNTRUSTED_LOCAL_CONTACT_SOURCE")
    timestamp = document.get("generated_at")
    if not isinstance(timestamp, str):
        raise ValueError("SOURCE_TIMESTAMP_MISSING")
    try:
        stamp = dt.datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        raise ValueError("SOURCE_TIMESTAMP_INVALID") from None
    if stamp.tzinfo is None:
        raise ValueError("SOURCE_TIMEZONE_MISSING")
    now = now or dt.datetime.now(dt.timezone.utc)
    age = (now - stamp.astimezone(dt.timezone.utc)).total_seconds()
    if not -300 <= age <= 24 * 3600:
        raise ValueError("CONTACT_INDEX_STALE")
    candidates = document.get("contacts")
    if not isinstance(candidates, list) or not 1 <= len(candidates) <= 500:
        raise ValueError("CONTACT_INDEX_EMPTY_OR_TOO_LARGE")
    by_id = {}
    for item in candidates:
        if not isinstance(item, dict):
            raise ValueError("CONTACT_ROW_INVALID")
        cid = item.get("contact_id")
        aid = item.get("account_id")
        opps = item.get("linked_opportunity_ids")
        if not C.fullmatch(str(cid)) or not A.fullmatch(str(aid)) or \
                not R.fullmatch(str(item.get("quote_record_id"))) or \
                not Q.fullmatch(str(item.get("source_qid"))) or \
                not isinstance(opps, list) or len(opps) != 1 or not O.fullmatch(str(opps[0])) or \
                item.get("sfdc_quote_contact_oppo_verified") is not True or \
                item.get("salesforce_write_performed") is not False or \
                not EMAIL.fullmatch(str(item.get("email"))) or \
                not item.get("account_name") or \
                not re.fullmatch(r"[\uAC00-\uD7A3]{2,20}", normalized_name(item.get("korean_name"))):
            raise ValueError("CONTACT_ROW_UNVERIFIED")
        if cid in by_id:
            raise ValueError("CONTACT_DUPLICATE_ID")
        by_id[cid] = item
    matches = [x for x in by_id.values() if normalized_name(x["korean_name"]) == name and
               (not account or x["account_id"][:15] == account[:15])]
    if len(matches) > limit:
        raise ValueError("INCOMPLETE_CONTACT_MATCH_SCOPE")
    return matches


def linked_ids(page, kind):
    hrefs = page.locator("a[href]").evaluate_all(
        "xs=>xs.map(x=>x.getAttribute('href')||'')")
    rx = re.compile(r"/lightning/r/" + re.escape(kind) +
                    r"/([A-Za-z0-9]{15,18})/view")
    return {m.group(1) for href in hrefs for m in [rx.search(href)] if m}


def field(lines, name):
    for i, line in enumerate(lines[:-1]):
        if line == name:
            return lines[i + 1]
    return ""


def recheck_live(page, entry):
    qid = entry["source_qid"]
    page.goto(BASE + "/lightning/r/Quotation__c/" + entry["quote_record_id"] + "/view",
              wait_until="domcontentloaded", timeout=25000)
    page.wait_for_function("q=>document.title.includes(q)", arg=qid, timeout=12000)
    page.get_by_role("tab", name="Details", exact=True).click(timeout=10000)
    lines = [x.strip() for x in page.locator("body").inner_text(timeout=10000).splitlines() if x.strip()]
    if field(lines, "Currency") != "KRW" or field(lines, "Active") != "True" or \
            field(lines, "Quotation ID") != entry["amea_id"]:
        raise ValueError("QUOTE_STATUS_CHANGED")
    accounts, contacts, opportunities = (linked_ids(page, kind)
                                         for kind in ("Account", "Contact", "Opportunity"))
    if len(accounts) != 1 or len(contacts) != 1 or len(opportunities) != 1:
        raise ValueError("AMBIGUOUS_LIVE_QUOTE_RELATIONSHIP")
    aid, cid, oid = (next(iter(xs)) for xs in (accounts, contacts, opportunities))
    if aid[:15] != entry["account_id"][:15] or cid[:15] != entry["contact_id"][:15] or \
            oid[:15] != entry["linked_opportunity_ids"][0][:15]:
        raise ValueError("LIVE_IDENTITY_RELATIONSHIP_CHANGED")
    page.goto(BASE + "/lightning/r/Contact/" + cid + "/view",
              wait_until="domcontentloaded", timeout=25000)
    page.get_by_role("tab", name="Details", exact=True).click(timeout=10000)
    accounts = linked_ids(page, "Account")
    if not accounts or aid[:15] not in {x[:15] for x in accounts}:
        raise ValueError("CONTACT_ACCOUNT_CHANGED_OR_UNVERIFIED")
    emails = page.locator('a[href^="mailto:"]').evaluate_all(
        "xs=>xs.map(x=>(x.getAttribute('href')||'').slice(7).split('?')[0].toLowerCase())")
    if entry["email"].lower() not in emails:
        raise ValueError("CONTACT_EMAIL_CHANGED")
    return {
        "korean_name": normalized_name(entry["korean_name"]),
        "institution_name": entry["account_name"],
        "account_id": aid,
        "contact_id": cid,
        "email": entry["email"],
        "linked_opportunity_ids": [oid],
        "source_qid": qid,
        "source_verified_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "requires_server_identity_recheck": False,
    }


def process(request, index_document, live_check):
    selected = select_candidates(index_document, request)
    if not selected:
        return {"status": "PASS", "candidates": [], "unresolved_matches": 0,
                "coverage": "VERIFIED_2026_KRW_QUOTE_CONTACTS_ONLY",
                "salesforce_write": False, "local_only": True}
    results = []
    failures = 0
    for item in selected:
        try:
            row = live_check(item)
            if row is None:
                raise ValueError("CONTACT_LIVE_RECHECK_FAILED")
            results.append(row)
        except Exception:
            failures += 1
    # Do not silently turn an incomplete homonym search into a unique match.
    if failures:
        return {"status": "BLOCK", "code": "INCOMPLETE_LIVE_CONTACT_SCOPE",
                "candidates": [], "unresolved_matches": failures,
                "coverage": "VERIFIED_2026_KRW_QUOTE_CONTACTS_ONLY",
                "salesforce_write": False, "local_only": True}
    return {"status": "PASS", "candidates": results, "unresolved_matches": 0,
            "coverage": "VERIFIED_2026_KRW_QUOTE_CONTACTS_ONLY",
            "salesforce_write": False, "local_only": True}


def main():
    raw = sys.stdin.read(500)
    if not 0 < len(raw) <= 400:
        raise ValueError("INPUT_LENGTH_INVALID")
    request = json.loads(raw)
    path = path_for_index()
    if not path.is_file() or path.stat().st_size > 1_000_000:
        raise ValueError("PRIVATE_CONTACT_INDEX_UNAVAILABLE")
    index_document = json.loads(path.read_text(encoding="utf-8"))
    selected = select_candidates(index_document, request)
    if not selected:
        result = process(request, index_document, None)
    else:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as driver:
            browser = driver.chromium.connect_over_cdp("http://127.0.0.1:9222", timeout=12000)
            page = browser.contexts[0].new_page()
            try:
                result = process(request, index_document, lambda item: recheck_live(page, item))
            finally:
                page.close()
                browser.close()
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, json.JSONDecodeError, KeyError, TypeError):
        print(json.dumps({"status": "BLOCK", "code": "CONTACT_SOURCE_UNAVAILABLE_OR_INVALID",
                          "salesforce_write": False, "local_only": True}))
    except Exception:
        print(json.dumps({"status": "BLOCK", "code": "SFDC_AUTHENTICATED_READBACK_UNAVAILABLE",
                          "salesforce_write": False, "local_only": True}))
