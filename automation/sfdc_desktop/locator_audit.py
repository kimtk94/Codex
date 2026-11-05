#!/usr/bin/env python3
"""Privacy-safe Salesforce UI structure diagnostics, v3.

Only counts controls. Traverses open shadow roots and browser frames.
Does not read input values, labels, emails, IDs, HTML, screenshots, or credentials.
"""
import argparse
import json
import time
from playwright.sync_api import Error as PlaywrightError, sync_playwright

AUDIT_VERSION = "3.0-shadow-frame"
JS = """() => {
 const selector='input,select,textarea,button,[role="textbox"],[role="combobox"],lightning-input,lightning-combobox,lightning-dual-listbox';
 const counts={}; let dialogs=0, shadowRoots=0, required=0;
 const visited=new Set();
 function walk(root) {
   if (!root || visited.has(root)) return;
   visited.add(root);
   for (const node of root.querySelectorAll('*')) {
     if (node.matches('[role="dialog"],section.slds-modal')) dialogs++;
     if (node.matches(selector)) {
       const tag=node.tagName.toLowerCase();
       counts[tag]=(counts[tag]||0)+1;
       if(node.hasAttribute('required') || node.getAttribute('aria-required')==='true') required++;
     }
     if(node.shadowRoot) {shadowRoots++;walk(node.shadowRoot);}
   }
 }
 walk(document);
 return {dialogs,shadow_roots:shadowRoots,control_types:counts,
         control_count:Object.values(counts).reduce((a,b)=>a+b,0),
         required_count:required};
}"""

def inspect_frame(frame):
    value=frame.evaluate(JS)
    return {k:value[k] for k in ("dialogs","shadow_roots","control_types","control_count","required_count")}

def inspect_context(context):
    results=[]; errors=0; tabs=0; total_frames=0
    for page in context.pages:
        if page.is_closed():continue
        tabs+=1
        for frame in page.frames:
            total_frames+=1
            for attempt in range(5):
                try:
                    result=inspect_frame(frame)
                    if result["dialogs"] or result["control_count"]:
                        results.append(result)
                    break
                except PlaywrightError as exc:
                    msg=str(exc).lower()
                    if attempt==4 or not any(x in msg for x in ("execution context was destroyed","navigation","detached")):
                        errors+=1;break
                    time.sleep(0.6)
    return {"audit_version":AUDIT_VERSION,"inspected_tabs":tabs,
            "inspected_frames":total_frames,"frames_with_controls":len(results),
            "frame_inspections_failed":errors,"results":results,
            "note":"Only counts. No customer fields, data, URLs or record identifiers captured."}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--url",required=True)
    args=p.parse_args()
    from runner import check_url, PROFILE
    check_url(args.url)
    print("SFDC_AUDIT_VERSION="+AUDIT_VERSION,flush=True)
    with sync_playwright() as pw:
        context=pw.chromium.launch_persistent_context(user_data_dir=str(PROFILE),
                 channel="chrome",headless=False)
        try:
            page=context.pages[0] if context.pages else context.new_page()
            page.goto(args.url,wait_until="domcontentloaded")
            input("Open New Opportunity in THIS Chrome window, then press Enter: ")
            time.sleep(0.75)
            print(json.dumps(inspect_context(context),ensure_ascii=False,indent=2))
        finally:
            context.close()

if __name__=="__main__":
    main()
