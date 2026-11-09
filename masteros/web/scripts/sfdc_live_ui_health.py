"""Read-only real Salesforce list-view availability probe.

Connects to the existing authorized PC Chrome CDP session. No writes, no
credentials in stdout, no contact/account/project data in JSON.
"""
from __future__ import annotations
import datetime as dt
import json
from urllib.parse import urlparse

BASE = "https://novogene.lightning.force.com"
ROUTES = {
    "lead": "/lightning/o/Lead/list",
    "opportunity": "/lightning/o/Opportunity/list",
    "quote": "/lightning/o/Quotation__c/list",
}

def summarize(results):
    checks = {k: "PASS" if results.get(k) is True else "BLOCK"
              for k in ROUTES}
    return {
        "status": "PASS" if all(v == "PASS" for v in checks.values()) else "BLOCK",
        "lead_view": checks["lead"],
        "opportunity_view": checks["opportunity"],
        "quote_view": checks["quote"],
        "checked_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "read_only": True,
        "crm_write_verified": False,
    }

def probe():
    from playwright.sync_api import sync_playwright
    checks = {}
    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(
            "http://127.0.0.1:9222", timeout=9000)
        context = browser.contexts[0]
        page = context.new_page()
        try:
            for item, route in ROUTES.items():
                try:
                    page.goto(BASE + route, wait_until="domcontentloaded",
                              timeout=22000)
                    page.locator(
                        'input[placeholder="Search this list..."]'
                    ).first.wait_for(state="visible", timeout=11000)
                    checks[item] = (
                        urlparse(page.url).hostname == "novogene.lightning.force.com"
                        and "Login" not in page.title()
                    )
                except Exception:
                    checks[item] = False
        finally:
            page.close()
    return summarize(checks)

if __name__ == "__main__":
    try:
        output = probe()
    except Exception:
        output = summarize({})
    print(json.dumps(output, ensure_ascii=True, sort_keys=True))
