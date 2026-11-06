"""Authenticated UI-only Salesforce Contact preview: explicit single matching person.

Runs on the operator's already-authenticated desktop Chrome (CDP port 9222).
Reads All Contacts, the selected Contact, and an existing Opportunity.
Never clicks Save, touches Salesforce API, creates users or uploads files.
Default is validation only. --out explicitly writes a private local JSON
for the web preview; NEVER commit/output that file in Actions.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
from pathlib import Path
from urllib.parse import urlparse

SFID_CONTACT = re.compile(r"^003[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?$")
SFID_ACCOUNT = re.compile(r"^001[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?$")
SFID_OPPO = re.compile(r"^006[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?$")
HANGUL_NAME = re.compile(r"^[가-힣]{2,20}$")
COUNT = re.compile(r"\b(\d+)\s+items?\b")
EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
HOST = "https://novogene.lightning.force.com"

class Hold(RuntimeError):
    pass

def record_id(url, prefix):
    pieces = urlparse(url).path.split("/")
    possible = [part for part in pieces if part.startswith(prefix)]
    if not possible:
        return ""
    match = possible[0]
    return match if {
        "003": SFID_CONTACT, "001": SFID_ACCOUNT,
        "006": SFID_OPPO,
    }[prefix].fullmatch(match) else ""

def visible_record_links(page, label, prefix):
    links = page.locator('a[href*="/lightning/r/'+label+'/"]').evaluate_all(
        "(xs)=>xs.map(x=>({href:x.href,label:(x.innerText||'').trim()}))"
    )
    result = {}
    for item in links:
        sfid = record_id(item["href"], prefix)
        if sfid:
            result[sfid] = item["label"]
    return result

def strict_single_view(query, view_label, count_tokens, rows):
    if not HANGUL_NAME.fullmatch(query):
        raise Hold("HOLD_INVALID_KOREAN_NAME")
    if view_label != "All Contacts":
        raise Hold("HOLD_NOT_ALL_CONTACTS")
    counts = [int(x) for x in COUNT.findall(count_tokens)]
    if not counts or len(set(counts)) != 1 or counts[0] != 1:
        raise Hold("HOLD_RESULT_COUNT_UNVERIFIED_OR_AMBIGUOUS")
    if len(rows) != 1 or rows[0].get("contact_id") == "":
        raise Hold("HOLD_CONTACT_ID_MISSING")
    if not SFID_CONTACT.fullmatch(rows[0]["contact_id"]):
        raise Hold("HOLD_CONTACT_ID_INVALID")
    observed = re.sub(r"\s+", "", rows[0].get("display_name",""))
    if not observed.startswith(query) or (
        len(observed)>len(query) and "가" <= observed[len(query)] <= "힣"
    ):
        raise Hold("HOLD_KOREAN_NAME_NOT_EXACT")
    return rows[0]["contact_id"]

def verified_private_evidence(query, candidate, opportunity_id, *, timestamp):
    if not HANGUL_NAME.fullmatch(query) or not SFID_OPPO.fullmatch(opportunity_id):
        raise Hold("HOLD_NAME_OR_OPPORTUNITY_ID")
    if (not SFID_CONTACT.fullmatch(candidate.get("contact_id","")) or
        not SFID_ACCOUNT.fullmatch(candidate.get("account_id","")) or
        not EMAIL.fullmatch(candidate.get("email","")) or
        candidate.get("korean_name") != query or
        not str(candidate.get("institution_name","")).strip()):
        raise Hold("HOLD_CONTACT_IDENTITY_INCOMPLETE")
    institution = candidate["institution_name"].casefold()
    if any(x in institution for x in
           ("kaist", "한국과학기술원", "hannam univ", "한남대학교", "한남대")):
        raise Hold("HOLD_ACCOUNT_EXCLUDED")
    if candidate.get("opportunity_contact_id") != candidate["contact_id"]:
        raise Hold("HOLD_OPPORTUNITY_MAIN_CONTACT_MISMATCH")
    if candidate.get("opportunity_account_id") != candidate["account_id"]:
        raise Hold("HOLD_OPPORTUNITY_ACCOUNT_MISMATCH")
    return {
        "version": "sfdc-oppo-contact-readback-v1",
        "source": "SFDC_LIGHTNING_READ_ONLY",
        "scope": "OPPORTUNITY_LINKED_CONTACTS",
        "salesforce_write_performed": False,
        "query": query,
        "generated_at": timestamp,
        "unresolved_matches": 0,
        "candidates": [{
            "contact_id": candidate["contact_id"],
            "account_id": candidate["account_id"],
            "korean_name": query,
            "institution_name": candidate["institution_name"].strip(),
            "email": candidate["email"],
            "linked_opportunity_ids": [opportunity_id],
        }],
    }

def audit_one(korean_name, opportunity_id):
    from playwright.sync_api import sync_playwright
    if not HANGUL_NAME.fullmatch(korean_name) or not SFID_OPPO.fullmatch(opportunity_id):
        raise Hold("HOLD_INVALID_INPUT")
    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9222")
        ctx = browser.contexts[0]
        tab = ctx.new_page()
        detail = ctx.new_page()
        opp = ctx.new_page()
        try:
            tab.goto(HOST+"/lightning/o/Contact/list",wait_until="domcontentloaded",timeout=20000)
            search = tab.get_by_placeholder("Search this list...")
            search.wait_for(timeout=12000)
            tab.get_by_role("button",name="Select a List View: Contacts").click()
            tab.get_by_text("All Contacts",exact=True).click()
            tab.get_by_placeholder("Search this list...").fill(korean_name)
            tab.get_by_placeholder("Search this list...").press("Enter")
            tab.wait_for_timeout(1400)
            rows = tab.locator("table tbody tr")
            entries = []
            for row in rows.all():
                links = row.locator('a[href*="/lightning/r/003"]').evaluate_all(
                    "(xs)=>xs.map(x=>({href:x.href,text:(x.innerText||'').trim()}))"
                )
                if links:
                    entries.append({
                        "contact_id": record_id(links[0]["href"],"003"),
                        "display_name": links[0]["text"],
                    })
                else:
                    entries.append({"contact_id":"","display_name":""})
            text = tab.locator("body").inner_text(timeout=6000)
            view_label = "All Contacts" if tab.title().startswith("All Contacts") else "unknown"
            cid = strict_single_view(korean_name,view_label,text,entries)
            detail.goto(HOST+"/lightning/r/Contact/"+cid+"/view",wait_until="domcontentloaded",timeout=20000)
            detail.wait_for_timeout(900)
            if "Contact" not in detail.title():
                raise Hold("HOLD_CONTACT_DETAIL_MISSING")
            accounts = visible_record_links(detail,"Account","001")
            if len(accounts)!=1:
                raise Hold("HOLD_CONTACT_ACCOUNT_NOT_UNIQUE")
            account_id,institution_name = next(iter(accounts.items()))
            mail = detail.locator('a[href^="mailto:"]').evaluate_all(
                "(xs)=>xs.map(x=>x.getAttribute('href').substring(7))"
            )
            unique_mail = sorted(set(e for e in mail if EMAIL.fullmatch(e)))
            if len(unique_mail)!=1:
                raise Hold("HOLD_CONTACT_EMAIL_UNVERIFIED")
            opp.goto(HOST+"/lightning/r/Opportunity/"+opportunity_id+"/view",wait_until="domcontentloaded",timeout=20000)
            opp.wait_for_timeout(800)
            if "Opportunity" not in opp.title():
                raise Hold("HOLD_OPPORTUNITY_DETAIL_MISSING")
            op_contacts = visible_record_links(opp,"Contact","003")
            op_accounts = visible_record_links(opp,"Account","001")
            if len(op_contacts)!=1 or len(op_accounts)!=1:
                raise Hold("HOLD_OPPORTUNITY_LINK_AMBIGUOUS")
            candidate = {
                "contact_id": cid, "account_id": account_id,
                "korean_name": korean_name, "institution_name": institution_name,
                "email": unique_mail[0],
                "opportunity_contact_id": next(iter(op_contacts)),
                "opportunity_account_id": next(iter(op_accounts)),
            }
            timestamp=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
            return verified_private_evidence(korean_name,candidate,opportunity_id,timestamp=timestamp)
        finally:
            tab.close()
            detail.close()
            opp.close()
            browser.close()

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--korean-name",required=True)
    parser.add_argument("--reference-opportunity-id",required=True)
    parser.add_argument("--out",help="Explicit private local filename, no GitHub uploads")
    args=parser.parse_args()
    try:
        payload=audit_one(args.korean_name,args.reference_opportunity_id)
        if args.out:
            dest=Path(args.out).expanduser().resolve()
            if "Codex" in dest.parts or ".git" in dest.parts:
                raise Hold("HOLD_OUTPUT_INSIDE_REPOSITORY")
            dest.parent.mkdir(parents=True,exist_ok=True)
            with dest.open("x",encoding="utf-8") as f:
                json.dump(payload,f,ensure_ascii=False,indent=2)
        print(json.dumps({"status":"PASS_SINGLE_VERIFIED_RELATIONSHIP",
                          "candidate_count":1,
                          "file_written":bool(args.out),
                          "salesforce_save":False},ensure_ascii=False))
    except Hold as err:
        print(json.dumps({"status":str(err),"file_written":False,"salesforce_save":False}))
        return 2
    except Exception:
        print('{"status":"HOLD_BROWSER_OR_UI_ERROR","file_written":false,"salesforce_save":false}')
        return 2
    return 0

if __name__=="__main__":
    raise SystemExit(main())
