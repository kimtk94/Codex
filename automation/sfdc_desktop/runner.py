#!/usr/bin/env python3
"""Salesforce UI automation P0: permission discovery + guarded form entry (NO SFDC API).

Use only with company-approved browser automation. Default is audit/dry-run.
Credentials/MFA are entered by the human in a visible browser, never automated.
"""
import argparse
import csv
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
HOME = Path(os.environ.get("SFDC_AUTOMATION_HOME", Path.home() / ".sfdc_desktop"))
PROFILE = HOME / "chrome_profile"
SAFE_HOST = re.compile(r"^([a-z0-9-]+\.)*(salesforce\.com|force\.com|salesforce\.mil)$", re.I)
OBJECTS = {"Account", "Contact", "Opportunity", "Task"}
FIELDS = {"Name", "Subject", "Description", "Phone", "Email", "StageName", "CloseDate", "Amount"}

def output(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=2))

def screenshot_safe(page, name):
    """Do NOT save screenshots: may contain sensitive customer data."""
    return None

def check_url(url):
    from urllib.parse import urlsplit
    host = (urlsplit(url).hostname or "").lower()
    if not SAFE_HOST.fullmatch(host):
        raise ValueError("Refusing non-Salesforce URL: " + host)
    return url

def audit(page):
    # Read-only inspection of accessible Salesforce UI, no network API calls.
    return {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "page_url": page.url.split("?")[0],
        "page_title": page.title(),
        "buttons": sorted(set(page.get_by_role("button").all_text_contents()))[:80],
        "links": sorted(set(page.get_by_role("link").all_text_contents()))[:80],
        "note": "UI visibility only; not proof of Salesforce CRUD permissions.",
    }

def load_queue(path):
    with Path(path).open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    required = {"source_id", "object_type", "record_key"}
    if not rows or not required.issubset(rows[0]):
        raise ValueError("CSV needs source_id,object_type,record_key and at least one row")
    ids = set()
    for row in rows:
        if row["object_type"] not in OBJECTS:
            raise ValueError("Unsupported object_type")
        key = (row["object_type"], row["record_key"])
        if not row["source_id"] or not row["record_key"] or key in ids:
            raise ValueError("Missing identifier or duplicate object/record_key in queue")
        ids.add(key)
    return rows

def fill_form(page, row, mapping):
    """Only permit explicitly mapped UI fields; selector mapping is local only."""
    obj = row["object_type"]
    cfg = mapping.get(obj)
    if not cfg or not cfg.get("url") or not cfg.get("fields"):
        raise ValueError("Missing verified UI mapping for " + obj)
    page.goto(check_url(cfg["url"]), wait_until="domcontentloaded")
    page.wait_for_load_state("domcontentloaded")
    for name, selector in cfg["fields"].items():
        if name in row and row[name]:
            if name not in FIELDS:
                raise ValueError("Unapproved field: " + name)
            loc = page.locator(selector)
            if loc.count() != 1 or not loc.is_visible() or not loc.is_enabled():
                raise RuntimeError("Field unavailable/nonunique: " + name)
            loc.fill(row[name])
    return {"source_id": row["source_id"], "object_type": obj, "record_key": row["record_key"],
            "status": "FORM_FILLED_NOT_SAVED"}

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--url", required=True, help="Salesforce UI starting URL")
    p.add_argument("--mode", choices=["audit", "queue-check", "fill"], default="audit")
    p.add_argument("--queue", help="Locally exported sanitized CSV (never commit)")
    p.add_argument("--mapping", help="Local verified selectors JSON; never commit")
    p.add_argument("--allow-fill", action="store_true", help="Allow filling fields; never presses Save")
    a = p.parse_args()
    check_url(a.url)
    HOME.mkdir(parents=True, exist_ok=True)
    if a.mode == "queue-check":
        output({"mode": "queue-check", "count": len(load_queue(a.queue)), "status": "PASS"})
        return
    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE), headless=False, channel="chrome",
            viewport={"width": 1440, "height": 900}, accept_downloads=False
        )
        try:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto(a.url, wait_until="domcontentloaded")
            if a.mode == "audit":
                print("Sign in interactively if required; finish MFA in browser. Press Enter to audit.")
                input()
                check_url(page.url)
                output(audit(page))
            else:
                if not a.allow_fill or not a.queue or not a.mapping:
                    raise ValueError("fill requires --allow-fill, --queue and --mapping")
                mapping = json.loads(Path(a.mapping).read_text(encoding="utf-8"))
                rows = load_queue(a.queue)
                for row in rows:
                    output(fill_form(page, row, mapping))
                    print("Inspect the unsaved form; press Enter to continue to next. No Save clicks.")
                    input()
        finally:
            ctx.close()

if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, OSError) as exc:
        print(type(exc).__name__ + ": " + str(exc), file=sys.stderr)
        sys.exit(1)
