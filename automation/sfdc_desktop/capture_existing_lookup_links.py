#!/usr/bin/env python3
"""Capture exact existing Account and Main Contact ID links from Salesforce UI.

Only authenticated local Chrome CDP. Read-only navigation, no Lookup selection,
no CRM Save, no screenshots, no raw customer data in GitHub or console logs.
"""
import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright

from audit_existing_opportunity_no_save import validate_preflight, SFDC_ROUTE

ACCOUNT = re.compile(r"001[A-Za-z0-9]{15}\Z")
CONTACT = re.compile(r"003[A-Za-z0-9]{15}\Z")
DOM_SCRIPT = r"""() => {
  const found = [], seen = new Set();
  function scan(root) {
    if (!root || seen.has(root)) return;
    seen.add(root);
    for (const element of root.querySelectorAll('*')) {
      if (element.shadowRoot) scan(element.shadowRoot);
      if (element.localName !== 'a') continue;
      const href = element.getAttribute('href') || '';
      const match = href.match(/^\/lightning\/r\/(Account|Contact)\/([A-Za-z0-9]{18})\/(?:view)?(?:[/?]|$)/);
      if (!match) continue;
      const field = element.closest('record_flexipage-record-field');
      if (!field) continue;
      const label = (field.innerText || '').slice(0, 800);
      found.push({
        object: match[1], record_id: match[2],
        is_account_name: /\bAccount Name\b/i.test(label),
        is_main_contact: /\bMain Contact\b/i.test(label),
        is_end_user_account: /end user account/i.test(label),
        is_end_user_contact: /end user contact/i.test(label)
      });
    }
  }
  scan(document);
  return found;
}"""


def validate_links(candidates):
    """Require exactly one correctly labeled native ID for each principal lookup."""
    if not isinstance(candidates, list):
        raise ValueError("DOM record links must be a list")
    accounts = [x for x in candidates if isinstance(x, dict)
                and x.get("object") == "Account"
                and x.get("is_account_name") is True
                and x.get("is_end_user_account") is False]
    contacts = [x for x in candidates if isinstance(x, dict)
                and x.get("object") == "Contact"
                and x.get("is_main_contact") is True
                and x.get("is_end_user_contact") is False]
    if len(accounts) != 1 or len(contacts) != 1:
        raise ValueError("Account Name / Main Contact links missing or ambiguous")
    account_id = str(accounts[0].get("record_id") or "")
    contact_id = str(contacts[0].get("record_id") or "")
    if not ACCOUNT.fullmatch(account_id) or not CONTACT.fullmatch(contact_id):
        raise ValueError("Labels must link to exact Salesforce Account/Contact IDs")
    return {"account_record_id": account_id, "contact_record_id": contact_id}


def capture(browser, bridge):
    target = str(bridge.get("opportunity_record_id") or "")
    pages = []
    for context in browser.contexts:
        for page in context.pages:
            url = urlsplit(page.url)
            match = SFDC_ROUTE.fullmatch(url.path)
            if url.hostname == "novogene.lightning.force.com" and match and match.group(1) == target:
                pages.append(page)
    if len(pages) != 1:
        raise ValueError("One unique authenticated Opportunity target required")
    page = pages[0]
    validate_preflight(
        bridge, urlsplit(page.url).path,
        page.get_by_role("button", name="Save", exact=True).count(),
        page.get_by_role("button", name="Cancel", exact=True).count()
    )
    tab = page.get_by_role("tab", name="Details", exact=True)
    if tab.count() != 1:
        raise ValueError("Exactly one Details tab required")
    if tab.get_attribute("aria-selected") != "true":
        tab.click(timeout=7000)
        page.wait_for_timeout(250)
    record_ids = validate_links(page.evaluate(DOM_SCRIPT))
    return {
        "version": "sfdc-existing-opportunity-lookup-links-v1",
        "source": "read-only existing Opportunity Details field links",
        "captured_utc": datetime.now(timezone.utc).isoformat(),
        "opportunity_record_id": target,
        **record_ids,
        "account_contact_field_links_verified": True,
        "lookup_selection_performed": False,
        "salesforce_save_allowed": False,
        "salesforce_save_performed": False,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--bridge", default=str(
        Path.home() / ".sfdc_desktop" / "verified_live_quotation_report_bridge.json"))
    p.add_argument("--output", default=str(
        Path.home() / ".sfdc_desktop" / "existing_lookup_record_ids_private.json"))
    p.add_argument("--cdp-url", default="http://127.0.0.1:9222")
    args = p.parse_args()
    if args.cdp_url != "http://127.0.0.1:9222":
        p.error("Only local CDP endpoint is supported")
    source = json.loads(Path(args.bridge).read_text(encoding="utf-8-sig"))
    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(args.cdp_url, timeout=12000)
        result = capture(browser, source)
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("EXISTING ACCOUNT FIELD LINK: EXACTLY ONE (001...)")
    print("EXISTING MAIN CONTACT FIELD LINK: EXACTLY ONE (003...)")
    print("LOOKUP SELECTION PERFORMED: FALSE")
    print("SALESFORCE SAVE PERFORMED: FALSE")
    print("PRIVATE RESULT:", target)


if __name__ == "__main__":
    main()
