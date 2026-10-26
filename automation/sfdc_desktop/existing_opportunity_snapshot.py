#!/usr/bin/env python3
"""Read-only snapshot of an EXISTING Salesforce Opportunity opened by the user.
Authenticated Chrome CDP session is reused. No clicks, edits, Save, or screenshots.
Exports visible field labels, rendered values and non-sensitive structural counts.
Contains customer data; keep JSON local.
"""
import argparse,json,re
from pathlib import Path
from playwright.sync_api import sync_playwright,Error as PWError
from runner import check_url

SNAPSHOT_JS=r"""() => {
 const seen=new Set(), labels=[], inputs=[];
 const tidy=s=>(s||'').replace(/\s+/g,' ').trim();
 function walk(root) {
  if(!root||seen.has(root))return;
  seen.add(root);
  for(const el of root.querySelectorAll('*')){
   if(el.shadowRoot)walk(el.shadowRoot);
   if(el.matches('label,dt,[class*="field-label"],[class*="fieldLabel"]')){
    const label=tidy(el.textContent).slice(0,100);
    if(!label)continue;
    const parent=el.closest('lightning-output-field,lightning-record-view-form,.slds-form-element,dl');
    const value=tidy(parent?.querySelector('dd,.slds-form-element__static,lightning-formatted-text,lightning-formatted-number,lightning-formatted-date-time')?.textContent||'').slice(0,350);
    if(value)labels.push({label,value});
   }
   if(el.matches('lightning-output-field')) {
    const label=tidy(el.getAttribute('field-name')||'');
    const value=tidy(el.innerText||el.textContent).slice(0,350);
    if(label&&value)labels.push({label,value});
   }
  }
 }
 walk(document);
 const dedup=new Map();
 for(const x of labels)dedup.set(x.label+'|'+x.value,x);
 return {shadow_roots:seen.size-1,fields:[...dedup.values()].slice(0,250)};
}"""

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--cdp-url",default="http://127.0.0.1:9222")
    p.add_argument("--output",default="")
    args=p.parse_args()
    with sync_playwright() as pw:
        browser=pw.chromium.connect_over_cdp(args.cdp_url)
        if not browser.contexts:raise RuntimeError("No Chrome context connected")
        ctx=browser.contexts[0]
        input("Open an EXISTING Salesforce Opportunity's Details tab (not New Opportunity). Press Enter ONCE: ")
        candidate=[]
        for page in ctx.pages:
            if page.is_closed():continue
            try:
                url=page.url
                check_url(url)
                title=page.title()
                if "opportunity" in title.lower() and "new opportunity" not in title.lower():
                    candidate.append(page)
            except (PWError,ValueError):continue
        if len(candidate)!=1:
            raise RuntimeError("Expected exactly one existing Opportunity tab; tabs matched: "+str(len(candidate)))
        page=candidate[0]
        page.bring_to_front()
        result={"version":"existing-opportunity-live-v1","title":page.title(),
                "source":"Salesforce visible UI","saved_or_modified":False,
                "frames":[]}
        for frame in page.frames:
            try:
                data=frame.evaluate(SNAPSHOT_JS)
                if data["fields"]:result["frames"].append(data)
            except PWError:pass
        path=Path(args.output) if args.output else Path.home()/"sfdc_existing_opportunity_snapshot.json"
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
        print("LIVE FIELD PAIRS:",sum(len(f["fields"]) for f in result["frames"]))
        print("REPORT:",path)
        print("READ ONLY; Salesforce data not modified.")
if __name__=="__main__":main()
