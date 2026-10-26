#!/usr/bin/env python3
"""Conservative Salesforce Lookup preflight: drafts only, never Save.

Uses Playwright's open Shadow DOM traversal. Requires human MFA and opening New Opportunity.
Exact suggestion equality is required; ambiguity means no selection.
"""
import argparse
import json
from pathlib import Path
from playwright.sync_api import sync_playwright
from runner import check_url, PROFILE

def prepare_lookup(draft):
    required=("Account Name","Main Contact")
    if not all(isinstance(draft.get(k),str) and draft[k].strip() for k in required):
        raise ValueError("Draft needs Account Name and Main Contact")
    if draft.get("save_allowed") is not False or draft.get("lookup_verified") is not False:
        raise ValueError("Expected unsaved, unverified draft safety flags")
    return {k:draft[k].strip() for k in required}

LOOKUP_JS = r"""(label) => {
 const seen = new Set(), matches = [];
 function traverse(root) {
   if (!root || seen.has(root)) return;
   seen.add(root);
   for (const el of root.querySelectorAll('*')) {
     if (el.shadowRoot) traverse(el.shadowRoot);
     if (!el.matches('label')) continue;
     if ((el.textContent||'').replace(/\s+/g,' ').trim().replace(/^\*\s*/, '') !== label) continue;
     let node = el, host = null;
     while (node) {
       if (node.tagName?.toLowerCase()==='lightning-grouped-combobox') { host=node; break; }
       node = node.parentElement || node.getRootNode()?.host || null;
     }
     if (host) {
       const inputs=[];
       function deep(n) {
         if (!n) return;
         for (const e of n.querySelectorAll('*')) {
           if (e.matches('input:not([type="hidden"])')) inputs.push(e);
           if (e.shadowRoot) deep(e.shadowRoot);
         }
       }
       deep(host.shadowRoot || host);
       if (inputs.length===1 && !matches.includes(inputs[0])) matches.push(inputs[0]);
     }
   }
 }
 traverse(document);
 return {count:matches.length, element:matches.length===1?matches[0]:null};
}"""

def find_input(context, label):
    from playwright.sync_api import Error as PlaywrightError
    frame_errors = 0
    for page in context.pages:
        if page.is_closed():
            continue
        for frame in page.frames:
            try:
                handle = frame.evaluate_handle(LOOKUP_JS, label)
                try:
                    count = handle.evaluate("(x) => x.count")
                    if count != 1:
                        continue
                    element = handle.get_property("element").as_element()
                    if element is not None and element.is_visible() and element.is_enabled():
                        return element, "READY"
                finally:
                    handle.dispose()
            except PlaywrightError:
                frame_errors += 1
    return None, "INPUT_NOT_UNIQUELY_RESOLVED" if not frame_errors else "INPUT_UNRESOLVED_FRAME_ERRORS"

def run(context, draft):
    values = prepare_lookup(draft)
    result = {}
    for label, value in values.items():
        loc, status = find_input(context, label)
        if loc is None:
            result[label] = status
            continue
        try:
            loc.fill(value)
            result[label] = "TEXT_ENTERED_RELATION_UNVERIFIED"
        except Exception:
            result[label] = "FILL_FAILED"
    return {"lookup":result,"relationship_verified":False,"save_clicked":False}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--url",required=True)
    p.add_argument("--draft",required=True)
    p.add_argument("--output",default="")
    a=p.parse_args()
    check_url(a.url)
    draft=json.loads(Path(a.draft).read_text(encoding="utf-8-sig"))
    prepare_lookup(draft)
    with sync_playwright() as pw:
        ctx=pw.chromium.launch_persistent_context(user_data_dir=str(PROFILE),headless=False,channel="chrome")
        try:
            page=ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto(a.url,wait_until="domcontentloaded")
            input("Complete MFA, open New Opportunity in this Chrome, press Enter: ")
            report=run(ctx,draft)
            report["note"]="Text-only lookup probe. Salesforce relationship not established; no Save."
            out=Path(a.output) if a.output else Path(a.draft).with_name("lookup_preflight.json")
            out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
            print(json.dumps(report,ensure_ascii=False,indent=2))
            print("Report:",out)
            input("Inspect unsaved form. Press Enter to close: ")
        finally:
            ctx.close()
if __name__=="__main__":
    main()
