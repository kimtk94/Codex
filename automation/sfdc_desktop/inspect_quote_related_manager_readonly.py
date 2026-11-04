#!/usr/bin/env python3
"""Local authenticated Quotation card structure audit, without leaking record data."""
import json
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright
from verify_related_quote_native_parent import HOST, OPPO

JS=r"""() => {
 const out=[], visited=new Set();
 function visit(root) {
  if(!root||visited.has(root))return;
  visited.add(root);
  for(const el of root.querySelectorAll('*')){
   if(el.shadowRoot)visit(el.shadowRoot);
   if(el.localName!=='lst-related-list-view-manager' &&
      el.localName!=='lst-common-list-internal' &&
      el.localName!=='lightning-datatable' &&
      el.localName!=='lst-related-list-single-container')continue;
   const seen=new Set(), all=[];
   function walk(parent){
    if(!parent||seen.has(parent))return;
    seen.add(parent);
    for(const child of parent.querySelectorAll('*')){
     all.push(child);
     if(child.shadowRoot)walk(child.shadowRoot);
    }
   }
   walk(el.shadowRoot||el);
   const anchors=all.filter(x=>x.localName==='a');
   const links=anchors.map(x=>{
    const href=x.getAttribute('href')||'';
    const text=(x.textContent||'').replace(/\s+/g,' ').trim();
    let category='OTHER';
    if(/\/Quotation__c\//.test(href))category='QUOTE_OBJECT_ROUTE';
    else if(/\/related\//.test(href))category='RELATED_ROUTE';
    else if(/\/lightning\//.test(href))category='LIGHTNING_OTHER_ROUTE';
    else if(!href || href==='#')category='EMPTY_OR_HASH';
    return {category,view_all:/^view all$/i.test(text),
       quotation_heading:/^quotations?(?:\s*\(\d+\))?$/i.test(text),
       has_data_record:!!x.getAttribute('data-recordid'),href_length:href.length};
   });
   out.push({host:el.localName,light_dom_children:el.children.length,
     shadow_present:!!el.shadowRoot,deep_nodes:all.length,
     anchor_count:anchors.length,links:links.slice(0,20),
     buttons:all.filter(x=>x.localName==='button').length,
     row_count:all.filter(x=>x.localName==='tr'||x.getAttribute('role')==='row').length,
     has_datatable:all.some(x=>x.localName==='lightning-datatable'),
     has_related_list:all.some(x=>x.localName==='lst-related-list-view-manager')});
  }
 }
 visit(document);
 return out.slice(0,20);
}"""

def main():
    src=Path.home()/".sfdc_desktop"/"created_pmp_250pe_5sample_oppo_quote_PRIVATE.json"
    opp=json.loads(src.read_text(encoding="utf-8-sig")).get("new_opportunity_record_id")
    if not isinstance(opp,str) or not OPPO.fullmatch(opp):raise SystemExit("HOLD_INVALID_OPPORTUNITY")
    with sync_playwright() as pw:
        b=pw.chromium.connect_over_cdp("http://127.0.0.1:9222")
        if len(b.contexts)!=1:raise SystemExit("HOLD_CONTEXT_COUNT")
        p=b.contexts[0].new_page()
        try:
            p.goto("https://"+HOST+"/lightning/r/Opportunity/"+opp+"/view",
                   wait_until="domcontentloaded",timeout=35000)
            if urlsplit(p.url).hostname!=HOST:raise SystemExit("HOLD_AUTH")
            tabs=[]
            for _ in range(30):
                tabs=[]
                for frame in p.frames:
                    try:
                        loc=frame.get_by_role("tab",name="Related",exact=True)
                        if loc.count()==1 and loc.is_visible():tabs.append(loc)
                    except Exception:pass
                if len(tabs)==1:break
                p.wait_for_timeout(500)
            if len(tabs)!=1:raise SystemExit("HOLD_TABS")
            tabs[0].click(timeout=12000)
            p.wait_for_timeout(3500)
            result=[]
            for frame in p.frames:
                try:result+=frame.evaluate(JS)
                except Exception:pass
            print(json.dumps({"structure":result[:12],"save_clicked":False},ensure_ascii=True))
        finally:p.close()
if __name__=="__main__":main()
