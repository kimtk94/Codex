#!/usr/bin/env python3
"""Local-only Lightning modal control audit. No values, screenshots, or API requests."""
import argparse
import json
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright

ALLOWED = {"input", "select", "textarea", "button", "lightning-input", "lightning-combobox", "lightning-dual-listbox"}
def classify(tag):
    return tag.lower() if tag and tag.lower() in ALLOWED else "other"

def inspect(page):
    # Avoid .inputValue(), HTML dumping, selectors containing record values.
    script = """() => {
      const dialog = document.querySelector('[role="dialog"]');
      if (!dialog) return {dialog_found:false, controls:[]};
      const els = [...dialog.querySelectorAll('input,select,textarea,button,lightning-input,lightning-combobox,lightning-dual-listbox')];
      return {dialog_found:true, controls:els.map(e => ({
        tag:e.tagName.toLowerCase(),
        role:e.getAttribute('role') || '',
        type:e.getAttribute('type') || '',
        required:e.hasAttribute('required') || e.getAttribute('aria-required') === 'true',
        label_present: !!(e.getAttribute('aria-label') || e.labels?.length || e.querySelector('label'))
      }))};
    }"""
    raw = page.evaluate(script)
    return {"dialog_found": bool(raw.get("dialog_found")),
            "control_count": len(raw.get("controls", [])),
            "control_types": {name: sum(1 for item in raw.get("controls", []) if classify(item["tag"]) == name)
                              for name in sorted({classify(item["tag"]) for item in raw.get("controls", [])})},
            "required_count": sum(bool(item.get("required")) for item in raw.get("controls", [])),
            "unlabeled_count": sum(not bool(item.get("label_present")) for item in raw.get("controls", [])),
            "note":"Counts only: no names, values, selectors, IDs, URLs, or customer data."}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--url", required=True)
    args=p.parse_args()
    from runner import check_url, PROFILE
    check_url(args.url)
    with sync_playwright() as pw:
        context=pw.chromium.launch_persistent_context(user_data_dir=str(PROFILE),
               channel="chrome", headless=False)
        try:
            page=context.pages[0] if context.pages else context.new_page()
            page.goto(args.url, wait_until="domcontentloaded")
            input("Log in normally and open the New Opportunity modal; then press Enter here: ")
            check_url(page.url)
            print(json.dumps(inspect(page), ensure_ascii=False, indent=2))
        finally:
            context.close()

if __name__=="__main__":
    main()
