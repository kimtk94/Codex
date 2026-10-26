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
 const seen=new Set(),pairs=[],structures=[];
 const tidy=s=>(s||'').replace(/\s+/g,' ').trim();
 function all(root,sel) {
   const results=[];
   function walk(r) {
     if(!r)return;
     for(const e of r.querySelectorAll('*')) {
       if(e.matches(sel))results.push(e);
       if(e.shadowRoot)walk(e.shadowRoot);
     }
   }
   walk(root);return results;
 }
 function text(el) {
   if(!el)return '';
   // textContent of custom element misses text rendered in shadow root.
   const parts=[tidy(el.textContent)];
   if(el.shadowRoot)parts.push(...all(el.shadowRoot,'span,a,lightning-formatted-text,lightning-formatted-number,lightning-formatted-date-time').map(e=>tidy(e.textContent)));
   return tidy(parts.filter(Boolean).join(' ')).slice(0,250);
 }
 function visit(root){
   if(!root||seen.has(root))return;
   seen.add(root);
   for(const el of root.querySelectorAll('*')){
     if(el.shadowRoot)visit(el.shadowRoot);
     if(!el.matches('.slds-form-element,lightning-output-field,records-record-layout-item'))continue;
     const labels=all(el,'.slds-form-element__label,label,dt,[slot="label"]')
          .map(text).filter(Boolean);
     const values=all(el,'.slds-form-element__static,[slot="outputField"],[slot="output"],dd,lightning-formatted-text,lightning-formatted-number,lightning-formatted-date-time')
          .map(text).filter(Boolean);
     // Values may render in sibling slots, nested record-output elements or
     // shadow text nodes not matched by standard static selectors.
     const fallback=text(el);
     const markup=el.outerHTML.slice(0,900);
     const children=[...el.children].slice(0,12).map(x=>({
       tag:x.localName,slot:x.getAttribute('slot')||'',
       text:tidy(x.textContent).slice(0,100),
       shadow_text:tidy(x.shadowRoot?.textContent).slice(0,100)}));
     const rendered=tidy(el.innerText).slice(0,300);
     structures.push({tag:el.localName,labels:labels.slice(0,3),values:values.slice(0,3),
       sample:fallback.slice(0,120),rendered,children,markup});
     if(labels.length) {
       const label=labels[0];
       // LWC slots render composed text in innerText even when textContent is empty.
       const control=el.querySelector('.slds-form-element__control');
       const controlRendered=tidy(control?.innerText);
       const fullRendered=tidy(el.innerText);
       let value=controlRendered || (values.length?values[0]:'');
       if(!value && fullRendered.startsWith(label))
         value=tidy(fullRendered.slice(label.length));
       // Never interpret the inline Edit action itself as a value.
       value=value.replace(new RegExp('\\s*Edit\\s+'+label.replace(/[.*+?^${}()|[\\]\\]/g,'\\\\     if(labels.length && values.length) pairs.push({label:labels[0],value:values[0],method:'deep_scoped'});')+'\\s*
   }
 }
 visit(document);
 const unique=new Map();
 for(const x of pairs)unique.set(x.label+'|'+x.value,x);
 return {shadow_roots:seen.size-1,inspected_count:structures.length,
   structures:structures.slice(0,60),fields:[...unique.values()].slice(0,250)};
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
        result={"version":"existing-opportunity-live-v2","title":page.title(),
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
        print("FRAME INSPECTION:",json.dumps([{"shadow_roots":x["shadow_roots"],"selector_counts":{"inspected_count":x["inspected_count"]},"field_count":len(x["fields"])} for x in result["frames"]],ensure_ascii=False))
        print("REPORT:",path)
        print("READ ONLY; Salesforce data not modified.")
if __name__=="__main__":main()
,'i'),'').trim();
       if(value && value!==label && value.toLowerCase()!=='edit '+label.toLowerCase())
         pairs.push({label,value:value.slice(0,350),method:'rendered_control_innerText'});
     }
   }
 }
 visit(document);
 const unique=new Map();
 for(const x of pairs)unique.set(x.label+'|'+x.value,x);
 return {shadow_roots:seen.size-1,inspected_count:structures.length,
   structures:structures.slice(0,60),fields:[...unique.values()].slice(0,250)};
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
        print("FRAME INSPECTION:",json.dumps([{"shadow_roots":x["shadow_roots"],"selector_counts":{"inspected_count":x["inspected_count"]},"field_count":len(x["fields"])} for x in result["frames"]],ensure_ascii=False))
        print("REPORT:",path)
        print("READ ONLY; Salesforce data not modified.")
if __name__=="__main__":main()
