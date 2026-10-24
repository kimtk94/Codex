#!/usr/bin/env python3
"""Salesforce Lightning read-only control census: all open tabs and same-origin frames.
Prints aggregate control counts only. Does not capture values, DOM HTML, or screenshots.
"""
import argparse
import json
import time
from playwright.sync_api import sync_playwright, Error as PlaywrightError

JS = """() => {
  const selectors = 'input,select,textarea,button,lightning-input,lightning-combobox,lightning-dual-listbox';
  const dialogs = [...document.querySelectorAll('[role="dialog"],section.slds-modal')];
  const scopes = dialogs.length ? dialogs : [document.body];
  const controls = scopes.flatMap(el => [...el.querySelectorAll(selectors)]);
  const totals = {};
  for (const el of controls) {
    const tag = el.tagName.toLowerCase();
    totals[tag] = (totals[tag] || 0) + 1;
  }
  return {dialog_found:dialogs.length>0, control_count:controls.length,
    control_types:totals,
    required_count:controls.filter(e=>e.hasAttribute('required') || e.getAttribute('aria-required')==='true').length,
    mode:dialogs.length?'dialog':'document'};
}"""

def inspect(page):
    raw = page.evaluate(JS)
    return {"dialog_found":raw["dialog_found"], "control_count":raw["control_count"],
            "control_types":raw["control_types"],
            "required_count":raw["required_count"], "mode":raw["mode"]}

def inspect_context(context):
    results = []
    # Every open Playwright tab and attached frame is inspected, not just pages[0].
    for page in context.pages:
        if page.is_closed():
            continue
        for frame in page.frames:
            for attempt in range(6):
                try:
                    result = inspect(frame)
                    if result["control_count"] or result["dialog_found"]:
                        results.append(result)
                    break
                except PlaywrightError as exc:
                    if "execution context was destroyed" not in str(exc).lower() and "navigation" not in str(exc).lower():
                        break
                    time.sleep(0.5)
    return {"inspected_tabs":len([p for p in context.pages if not p.is_closed()]),
            "frames_with_controls":len(results),
            "results":results,
            "note":"Aggregate UI statistics only, no URLs, labels, entered values, or customer data"}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--url",required=True)
    args=parser.parse_args()
    from runner import check_url, PROFILE
    check_url(args.url)
    with sync_playwright() as pw:
        ctx=pw.chromium.launch_persistent_context(user_data_dir=str(PROFILE),
                channel="chrome",headless=False)
        try:
            page=ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto(args.url,wait_until="domcontentloaded")
            input("In the opened automated Chrome window, log in and open New Opportunity. Press Enter: ")
            # Leave time for Lightning render/navigation; inspect every tab/frame.
            time.sleep(1)
            print(json.dumps(inspect_context(ctx),ensure_ascii=False,indent=2))
        finally:
            ctx.close()

if __name__=="__main__":
    main()
