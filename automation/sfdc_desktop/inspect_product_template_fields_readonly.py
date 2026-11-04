#!/usr/bin/env python3
"""Inspect existing Quote line Product Template field labels; read only."""
import json
import re
from pathlib import Path
from playwright.sync_api import sync_playwright

PRIVATE=Path.home()/".sfdc_desktop"
PATTERN=re.compile(r"/lightning/r/Product_Template__c/(a0G[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?)/view")
JS="""() => {
 const labels=[];
 const seen=new Set();
 function walk(root){
   if(!root||seen.has(root))return;
   seen.add(root);
   for(const el of root.querySelectorAll('*')){
     if(el.shadowRoot)walk(el.shadowRoot);
     if(el.localName==='record_flexipage-record-field'||
        el.localName==='lightning-output-field'){
       labels.push((el.innerText||'').split('\\n')[0].slice(0,70));
     }
   }
 }
 walk(document);
 return labels;
}"""

def main():
    x=json.loads((PRIVATE/"quote_source_line_inspect_20261103_PRIVATE.json").read_text(encoding="utf-8-sig"))
    matches={m.group(1) for a in x.get("links",[]) if isinstance(a,dict)
             for m in [PATTERN.fullmatch(a.get("href",""))] if m}
    if len(matches)!=1 or x.get("save_clicked") is not False:
        raise SystemExit("HOLD_TEMPLATE_REFERENCE_AMBIGUOUS")
    tid=next(iter(matches))
    present=set()
    with sync_playwright() as pw:
        b=pw.chromium.connect_over_cdp("http://127.0.0.1:9222")
        if len(b.contexts)!=1:raise SystemExit("HOLD_BROWSER_CONTEXT")
        page=b.contexts[0].new_page()
        try:
            page.goto("https://novogene.lightning.force.com/lightning/r/Product_Template__c/"+tid+"/view",
                      wait_until="domcontentloaded",timeout=35000)
            if tid not in page.url:raise SystemExit("HOLD_ROUTE")
            for tab in ("Details","Related"):
                t=page.get_by_role("tab",name=tab,exact=True)
                if t.count()==1:t.click(timeout=7000)
                page.wait_for_timeout(1000)
                for frame in page.frames:
                    try:present.update(s.casefold() for s in frame.evaluate(JS))
                    except Exception:pass
        finally:page.close()
    checks={k:any(k in field for field in present) for k in
            ("price","pricebook","unit price","currency","discount","amount","product")}
    out={"template_record_opened":True,"field_count":len(present),
         "price_related_label_presence":checks,"pricebook_entry_verified":False,
         "current_quote_price_verified":False,"salesforce_save_allowed":False}
    (PRIVATE/"existing_product_template_field_audit_PRIVATE.json").write_text(
        json.dumps(out,indent=2),encoding="utf-8")
    print("PRODUCT_TEMPLATE_READONLY",json.dumps(out,sort_keys=True))

if __name__=="__main__":
    main()
