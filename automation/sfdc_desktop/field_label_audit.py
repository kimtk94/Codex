#!/usr/bin/env python3
"""Read-only Salesforce Lightning field-label probe. No field values or screenshots."""
import argparse
import json
import time
from collections import Counter
from playwright.sync_api import sync_playwright, Error as PlaywrightError
from runner import check_url, PROFILE

VERSION="field-label-v2"
EXPECTED=["Opportunity Name","Account Name","Main Contact","Amount","Opportunity Currency",
          "Close Date","Service Line","Stage","Forecast Category","Progress Description","Status"]
JS=r"""(expected) => {
 const found = Object.fromEntries(expected.map(name => [name,{label_matches:0,required_labels:0}]));
 const seen = new Set();
 function visit(root) {
   if (!root || seen.has(root)) return;
   seen.add(root);
   for(const el of root.querySelectorAll('*')) {
     if(el.matches('label,legend,.slds-form-element__label')) {
       const original=(el.textContent || '');
       const label=original.replace(/\s+/g,' ').replace(/^\s*\*\s*/,'').trim();
       if (Object.prototype.hasOwnProperty.call(found,label)) {
         found[label].label_matches++;
         if(el.querySelector('abbr[title="required"]') ||
            el.getAttribute('aria-required')==='true' ||
            original.trim().startsWith('*')) found[label].required_labels++;
       }
     }
     if(el.shadowRoot) visit(el.shadowRoot);
   }
 }
 visit(document);
 return found;
}"""

def error_category(exc):
    msg=str(exc).lower()
    if "execution context was destroyed" in msg or "navigation" in msg:
        return "NAVIGATION"
    if "syntaxerror" in msg or "unexpected token" in msg:
        return "JAVASCRIPT_SYNTAX"
    if "timeout" in msg:
        return "TIMEOUT"
    if "detached" in msg:
        return "FRAME_DETACHED"
    return "EVALUATION_ERROR"

def inspect(context):
    counts={name:{"label_matches":0,"required_labels":0} for name in EXPECTED}
    failures=Counter(); successful=0; frames=0
    for page in context.pages:
        if page.is_closed(): continue
        for frame in page.frames:
            frames+=1
            for attempt in range(5):
                try:
                    found=frame.evaluate(JS,EXPECTED)
                    successful+=1
                    for name in EXPECTED:
                        row=found.get(name,{})
                        for col in ("label_matches","required_labels"):
                            counts[name][col]+=int(row.get(col,0))
                    break
                except PlaywrightError as exc:
                    category=error_category(exc)
                    if category in ("NAVIGATION","FRAME_DETACHED") and attempt<4:
                        time.sleep(0.5)
                        continue
                    failures[category]+=1
                    break
    return {"version":VERSION,"frames_total":frames,"frames_inspected":successful,
            "frames_unavailable":sum(failures.values()),"failure_categories":dict(failures),
            "field_labels":counts,"note":"Only expected field names and counts; no customer values or selectors."}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--url",required=True)
    args=parser.parse_args()
    check_url(args.url)
    print("SFDC_FIELD_AUDIT_VERSION="+VERSION,flush=True)
    with sync_playwright() as pw:
        ctx=pw.chromium.launch_persistent_context(user_data_dir=str(PROFILE),
                       channel="chrome",headless=False)
        try:
            page=ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto(args.url,wait_until="domcontentloaded")
            input("Open New Opportunity in THIS Chrome window, then press Enter: ")
            time.sleep(0.8)
            print(json.dumps(inspect(ctx),ensure_ascii=False,indent=2))
        finally:
            ctx.close()

if __name__=="__main__":
    main()
