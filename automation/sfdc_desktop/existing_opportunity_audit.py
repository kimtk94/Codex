#!/usr/bin/env python3
"""Read-only Lightning existing Opportunity structural audit, v2.

Aggregates UI structure across shadow roots and frames. Never reads customer values,
record identifiers, field values, page HTML, URLs, or screenshots.
"""
import argparse
import json
import time
from collections import Counter
from playwright.sync_api import sync_playwright, Error as PlaywrightError
from runner import check_url, PROFILE

VERSION="existing-opportunity-v2"
JS=r"""() => {
 const names=['Details','Related','Opportunity Information','Main Contact','Account Name',
              'Service Line','Quotation','Opportunity Contacts','Opportunity Team','Activity'];
 const result=Object.fromEntries(names.map(x=>[x,0]));
 let inlineEdit=0, editable=0, shadowRoots=0;
 const visited=new Set();
 function walk(root) {
   if(!root||visited.has(root))return;
   visited.add(root);
   for(const el of root.querySelectorAll('*')) {
     if(el.shadowRoot){shadowRoots++;walk(el.shadowRoot);}
     const role=el.getAttribute('role')||'';
     if(el.matches('a,button,[role="tab"],[role="button"],span,div,lightning-tab')) {
       const text=(el.childNodes.length===1 && el.firstChild.nodeType===3
            ? el.textContent : '').trim();
       if(Object.prototype.hasOwnProperty.call(result,text))result[text]++;
     }
     const title=(el.getAttribute('title')||'').toLowerCase();
     const aria=(el.getAttribute('aria-label')||'').toLowerCase();
     if(title.startsWith('edit ')||aria.startsWith('edit '))inlineEdit++;
     if(el.matches('input,textarea,select,[contenteditable="true"]'))editable++;
   }
 }
 walk(document);
 return {labels:result,inline_edit_controls:inlineEdit,editable_controls:editable,
         shadow_roots:shadowRoots};
}"""

def inspect_context(ctx):
    aggregate=Counter();labels=Counter();failures=Counter();frames=0;successful=0
    for page in ctx.pages:
        if page.is_closed():continue
        for frame in page.frames:
            frames+=1
            for attempt in range(4):
                try:
                    data=frame.evaluate(JS)
                    successful+=1
                    for k,v in data["labels"].items():labels[k]+=v
                    for k in ("inline_edit_controls","editable_controls","shadow_roots"):
                        aggregate[k]+=data[k]
                    break
                except PlaywrightError as exc:
                    message=str(exc).lower()
                    category="NAVIGATION" if "execution context was destroyed" in message else (
                         "FRAME_DETACHED" if "detached" in message else "OTHER")
                    if category in ("NAVIGATION","FRAME_DETACHED") and attempt<3:
                        time.sleep(0.5);continue
                    failures[category]+=1;break
    return {"version":VERSION,"frames_total":frames,"frames_inspected":successful,
        "frame_failures":dict(failures),"visible_label_indicators":dict(labels),
        "inline_edit_controls":aggregate["inline_edit_controls"],
        "editable_controls":aggregate["editable_controls"],"shadow_roots":aggregate["shadow_roots"],
        "note":"UI metadata only; counts do not prove save/edit permission."}

def main():
    p=argparse.ArgumentParser();p.add_argument("--url",required=True);a=p.parse_args()
    check_url(a.url)
    print("SFDC_EXISTING_AUDIT_VERSION="+VERSION,flush=True)
    with sync_playwright() as pw:
        ctx=pw.chromium.launch_persistent_context(user_data_dir=str(PROFILE),
                    channel="chrome",headless=False)
        try:
            page=ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto(a.url,wait_until="domcontentloaded")
            input("Open existing Opportunity -> Details in THIS Chrome, then press Enter: ")
            print(json.dumps(inspect_context(ctx),ensure_ascii=False,indent=2))
        finally:ctx.close()
if __name__=="__main__":main()
