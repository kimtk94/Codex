"""Contact-first, read-only Salesforce Opportunity intake opener.

SFDC-001: start from an EXISTING Contact (003) and verify Account (001).
Do not create a modal via the global Opportunity list, and never Save.
Until Contact->Opportunity New native action is independently validated,
this code opens only the verified Contact record and returns HOLD.
"""
from __future__ import annotations
import asyncio
import json
import re
import sys
from urllib.parse import urlparse

HOST = "https://novogene.lightning.force.com"
SFID = re.compile(r"^[A-Za-z0-9]{15}(?:[A-Za-z0-9]{3})?$")


def intake_contract(payload):
    if not isinstance(payload, dict) or set(payload) != {
        "name", "closeDate", "description", "contactId", "accountId"
    }:
        return "CONTACT_ORIGIN_REQUEST_INVALID"
    if not (isinstance(payload["contactId"], str) and
            payload["contactId"].startswith("003") and
            SFID.fullmatch(payload["contactId"])):
        return "EXISTING_CONTACT_NATIVE_ID_REQUIRED"
    if not (isinstance(payload["accountId"], str) and
            payload["accountId"].startswith("001") and
            SFID.fullmatch(payload["accountId"])):
        return "EXISTING_ACCOUNT_NATIVE_ID_REQUIRED"
    if not isinstance(payload["name"], str) or not 5 <= len(payload["name"]) <= 180:
        return "OPPORTUNITY_NAME_REQUIRED"
    if not isinstance(payload["description"], str) or (
        "Quote Issued" not in payload["description"] or
        "Quote Draft" in payload["description"] or
        not 12 <= len(payload["description"]) <= 3000
    ):
        return "QUOTE_ISSUED_DESCRIPTION_REQUIRED"
    if not isinstance(payload["closeDate"], str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}", payload["closeDate"]
    ):
        return "CLOSE_DATE_INVALID"
    return None


def contact_origin_url(page_url, contact_id):
    try:
        parsed = urlparse(page_url)
        return (parsed.scheme == "https" and parsed.netloc == "novogene.lightning.force.com"
            and parsed.path.startswith("/lightning/r/Contact/" + contact_id + "/"))
    except (ValueError, TypeError):
        return False


async def main():
    out = {
        "status": "HOLD_FORM_PARTIAL",
        "stage": "CONTACT_FIRST_ENTRY_REQUIRED",
        "reason": "CONTACT_ORIGIN_NOT_VERIFIED",
        "salesforce_write": False,
        "save_clicked": False,
        "crm_writes": 0,
        "page_open": False,
        "new_tabs_opened": 0,
        "fields": {"Opportunity": "NOT_CREATED"},
        "missing_for_save": [
            "Contact-origin Opportunity New UI",
            "Account", "Main Contact", "Amount", "Stage",
            "Native Product/Process/Pack", "Verified Quotation Related origin"
        ],
    }
    try:
        payload = json.loads(sys.stdin.read(1600))
        issue = intake_contract(payload)
        if issue:
            out["reason"] = issue
            print(json.dumps(out, ensure_ascii=False))
            return
        from playwright.async_api import async_playwright
        async with async_playwright() as pw:
            browser = await pw.chromium.connect_over_cdp(
                "http://127.0.0.1:9222", timeout=18000
            )
            try:
                if not browser.contexts:
                    raise RuntimeError("CHROME_AUTH_CONTEXT_MISSING")
                context = browser.contexts[0]
                matching = [
                    p for p in context.pages
                    if not p.is_closed() and
                    contact_origin_url(p.url, payload["contactId"])
                ]
                if len(matching) > 1:
                    out["reason"] = "MULTIPLE_CONTACT_TABS_AMBIGUOUS"
                else:
                    page = matching[0] if matching else await context.new_page()
                    if not matching:
                        out["new_tabs_opened"] = 1
                    url = HOST + "/lightning/r/Contact/" + payload["contactId"] + "/view"
                    if not contact_origin_url(page.url, payload["contactId"]):
                        await page.goto(url, wait_until="domcontentloaded", timeout=35000)
                    snapshot = await page.evaluate("""async (contactId) => {
                        const uri='/services/data/v62.0/ui-api/records/'+
                          encodeURIComponent(contactId)+
                          '?fields=Contact.AccountId,Contact.Name';
                        const res=await fetch(uri,{method:'GET',credentials:'same-origin'});
                        if(!res.ok)return {verified:false,http:res.status};
                        const item=await res.json();
                        return {verified:item.id===contactId,
                          account_id:item.fields?.AccountId?.value||null};
                    }""",payload["contactId"])
                    if (snapshot.get("verified") is True and
                            snapshot.get("account_id") == payload["accountId"]):
                        out["page_open"] = True
                        out["stage"] = "EXISTING_CONTACT_OPENED_READ_ONLY"
                        out["reason"] = "CONTACT_FIRST_NEW_OPPORTUNITY_ACTION_NOT_YET_VERIFIED"
                        out["fields"] = {
                            "Contact": "VERIFIED_NATIVE_003",
                            "Account": "VERIFIED_NATIVE_001",
                            "Opportunity": "NOT_CREATED",
                        }
                    else:
                        out["reason"] = "CONTACT_ACCOUNT_NATIVE_RELATION_UNVERIFIED"
            finally:
                await browser.close()
    except Exception as e:
        out["reason"] = "CONTACT_FIRST_SESSION_" + type(e).__name__.upper()
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
