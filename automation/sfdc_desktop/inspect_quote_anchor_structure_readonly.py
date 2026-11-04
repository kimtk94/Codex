#!/usr/bin/env python3
"""Read-only Salesforce Related quotation anchor structure inspector.

Only shape/counts are emitted. No customer names, record IDs, URLs, screenshots,
forms, Save, or CRM mutations.
"""
import json
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright
from verify_related_quote_native_parent import HOST, OPPO

JS=r"""() => {
 const out=[], seen=new Set();
 function descend(root) {
  if(!root||seen.has(root))return;
  seen.add(root);
  for(const el of root.querySelectorAll('*')) {
   if(el.shadowRoot)descend(el.shadowRoot);
   if(el.tagName!=='A')continue;
   const href=el.getAttribute('href')||'';
   if(!/\/Quotation__c\//.test(href))continue;
   const chain=[];
   let node=el;
   for(let i=0;i<14&&node;i++) {
    const tag=node.localName||'?';
    chain.push(tag);
    node=node.parentElement||node.getRootNode()?.host||null;
   }
   const area=el.closest('article,[role="region"],section,.slds-card,lst-related-list-single-container');
   const heading=area?.querySelector('h2,h3,.slds-card__header-title');
   const title=(heading?.textContent||'').trim();
   out.push({view_link:/\/view(?:[/?#]|$)/.test(href),
             chain,area_tag:area?.localName||null,
             area_heading_is_quote:/^Quotations?(?:\s*\(\d+\))?$/i.test(title),
             area_heading_present:!!title});
  }
 }
 descend(document);
 return out;
}"""


def main():
    src=Path.home()/".sfdc_desktop"/"created_pmp_250pe_5sample_oppo_quote_PRIVATE.json"
    data=json.loads(src.read_text(encoding="utf-8-sig"))
    record=data.get("new_opportunity_record_id")
    if not isinstance(record,str) or not OPPO.fullmatch(record):
        raise SystemExit("HOLD_INVALID_PRIVATE_OPPORTUNITY")
    with sync_playwright() as pw:
        b=pw.chromium.connect_over_cdp("http://127.0.0.1:9222",timeout=16000)
        if len(b.contexts)!=1:
            raise SystemExit("HOLD_CHROME_CONTEXT_COUNT")
        p=b.contexts[0].new_page()
        try:
            p.goto("https://"+HOST+"/lightning/r/Opportunity/"+record+"/view",
                   wait_until="domcontentloaded",timeout=35000)
            if urlsplit(p.url).hostname!=HOST:
                raise SystemExit("HOLD_LOGIN_OR_NAVIGATION")
            tabs=[]
            for _ in range(30):
                tabs=[]
                for frame in p.frames:
                    try:
                        t=frame.get_by_role("tab",name="Related",exact=True)
                        if t.count()==1 and t.is_visible(): tabs.append(t)
                    except Exception: continue
                if len(tabs)==1:break
                p.wait_for_timeout(500)
            if len(tabs)!=1:raise SystemExit("HOLD_RELATED_TAB_NOT_UNIQUE")
            tabs[0].click(timeout=10000)
            payload=[]
            for _ in range(28):
                p.wait_for_timeout(450)
                payload=[]
                for frame in p.frames:
                    try:
                        payload += frame.evaluate(JS)
                    except Exception:continue
                if payload:break
            report={"status":"READ_ONLY_SHAPE_CAPTURED","quote_anchor_count":len(payload),
                    "details":payload[:10],"save_clicked":False}
            print(json.dumps(report,ensure_ascii=True))
        finally:
            p.close()


if __name__=="__main__":
    main()
