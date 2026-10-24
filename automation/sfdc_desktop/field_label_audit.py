#!/usr/bin/env python3
"""Read-only field-label inventory for Salesforce Lightning. No field values or saving.

Runs inside browser already authenticated interactively. Generates local aggregate
metadata by visible label; no text entered by users is read or logged.
"""
import argparse
import json
from playwright.sync_api import sync_playwright
from runner import check_url, PROFILE

EXPECTED = ["Opportunity Name","Account Name","Main Contact","Amount","Opportunity Currency","Close Date","Service Line","Stage","Forecast Category","Progress Description","Status"]

JS = """() => {
 const expected = arguments[0]; // playwright evaluate passes arg separately; use function param below
}"""
JS = """(expected) => {
 const found = {};
 for (const name of expected) found[name] = {label_matches:0, required_labels:0};
 const seen = new Set();
 function visit(root) {
   if (!root || seen.has(root)) return;
   seen.add(root);
   for (const el of root.querySelectorAll('*')) {
     if (el.matches('label,[class*="form-element__label"],legend')) {
       const text = (el.textContent || '').replace(/\\s+/g,' ').replace(/^\\s*\\*/,'').trim();
       for (const name of expected) {
         if (text === name) {
           found[name].label_matches++;
           if (el.querySelector('abbr[title="required"]') ||
               el.getAttribute('aria-required')==='true' ||
               el.textContent.trim().startsWith('*')) found[name].required_labels++;
         }
       }
     }
     if (el.shadowRoot) visit(el.shadowRoot);
   }
 }
 visit(document);
 return found;
}"""

def inspect(context):
    outcome={x:{"label_matches":0,"required_labels":0} for x in EXPECTED}
    inspected=0; errors=0
    for page in context.pages:
        if page.is_closed(): continue
        for frame in page.frames:
            try:
                found=frame.evaluate(JS, EXPECTED)
                inspected+=1
                for key,item in found.items():
                    outcome[key]["label_matches"]+=item["label_matches"]
                    outcome[key]["required_labels"]+=item["required_labels"]
            except Exception:
                errors+=1
    return {"version":"field-label-v1","frames_inspected":inspected,
            "frames_unavailable":errors,"field_labels":outcome,
            "note":"No values or selectors collected; duplicated labels across page may inflate counts."}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--url",required=True)
    args=p.parse_args()
    check_url(args.url)
    with sync_playwright() as pw:
        ctx=pw.chromium.launch_persistent_context(user_data_dir=str(PROFILE),
                        channel="chrome",headless=False)
        try:
            page=ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto(args.url,wait_until="domcontentloaded")
            input("Open New Opportunity in this Chrome window. Press Enter when ready: ")
            print(json.dumps(inspect(ctx),ensure_ascii=False,indent=2))
        finally:
            ctx.close()

if __name__=="__main__":
    main()
