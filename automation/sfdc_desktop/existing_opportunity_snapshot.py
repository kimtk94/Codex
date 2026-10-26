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
 const visited=new Set(), pairs=[], counts={};
 const tidy=s=>(s||'').replace(/\s+/g,' ').trim();
 function inspect(root) {
  if(!root||visited.has(root))return;
  visited.add(root);
  for(const el of root.querySelectorAll('*')){
   if(el.shadowRoot)inspect(el.shadowRoot);
   for(const selector of ['lightning-output-field','records-record-layout-item',
       '.slds-form-element','dt','[data-field-name]']){
     if(!el.matches(selector))continue;
     counts[selector]=(counts[selector]||0)+1;
   }
   let label='',value='',method='';
   if(el.matches('lightning-output-field')){
     label=el.getAttribute('field-name')||'';
     value=tidy(el.textContent);method='output_field';
   }else if(el.matches('.slds-form-element')){
     label=tidy(el.querySelector('.slds-form-element__label')?.textContent);
     value=tidy(el.querySelector('.slds-form-element__static')?.textContent);
     method='slds_form_element';
   }else if(el.matches('dt')){
     label=tidy(el.textContent);
     value=tidy(el.nextElementSibling?.textContent);
     method='definition_list';
   }else if(el.matches('[data-field-name]')){
     label=el.getAttribute('data-field-name')||'';
     value=tidy(el.querySelector('lightning-formatted-text,lightning-formatted-number,.slds-form-element__static')?.textContent);
     method='data_field_name';
   }
   if(label&&value&&label!==value&&label.length<120)
     pairs.push({label:label.slice(0,120),value:value.slice(0,350),method});
  }
 }
 inspect(document);
 const unique=new Map();
 for(const x of pairs)unique.set(x.label+'|'+x.value,x);
 const visibleText=tidy(document.body?.innerText).slice(0,500);
 return {shadow_roots:visited.size-1,selector_counts:counts,
   visible_text_sample:visibleText, fields:[...unique.values()].slice(0,250)};
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
                result["frames"].append(data)
            except PWError:pass
        path=Path(args.output) if args.output else Path.home()/"sfdc_existing_opportunity_snapshot.json"
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
        print("LIVE FIELD PAIRS:",sum(len(f["fields"]) for f in result["frames"]))
        print("FRAME INSPECTION:",json.dumps([{"shadow_roots":x["shadow_roots"],"selector_counts":x["selector_counts"],"field_count":len(x["fields"])} for x in result["frames"]],ensure_ascii=False))
        print("REPORT:",path)
        print("READ ONLY; Salesforce data not modified.")
if __name__=="__main__":main()
