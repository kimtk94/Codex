#!/usr/bin/env python3
"""Anonymized HTML structure inspection for the live Quotation Related card.

Never prints contact names, record IDs, text values, hrefs or tokens.
Read-only Salesforce browser navigation only.
"""
import json
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright
from verify_related_quote_native_parent import HOST, OPPO

JS=r"""() => {
 const hits=[], roots=new Set();
 function scan(root){
  if(!root||roots.has(root))return;
  roots.add(root);
  for(const el of root.querySelectorAll('*')){
    if(el.shadowRoot)scan(el.shadowRoot);
    if(hits.length>=18)continue;
    if(!['H1','H2','H3','SPAN','DIV','A','P','LIGHTNING-ICON'].includes(el.tagName))continue;
    const t=(el.textContent||'').replace(/\s+/g,' ').trim();
    if(!/^Quotations?\s*\(\d+\)$/i.test(t)||el.children.length>4)continue;
    const parents=[];
    let node=el;
    for(let j=0;j<9&&node;j++){
      const stats={tag:node.localName||'?',role:node.getAttribute?.('role')||'',
          direct_children:node.children?.length||0};
      const subtree=node.shadowRoot||node;
      stats.links=subtree.querySelectorAll?.('a')?.length||0;
      stats.buttons=subtree.querySelectorAll?.('button')?.length||0;
      stats.rows=subtree.querySelectorAll?.('tr,[role="row"]')?.length||0;
      stats.recordid_elements=subtree.querySelectorAll?.('[data-recordid],[data-record-id]')?.length||0;
      stats.lightning_url=subtree.querySelectorAll?.('lightning-formatted-url')?.length||0;
      parents.push(stats);
      node=node.parentElement||node.getRootNode()?.host||null;
    }
    hits.push({hit_tag:el.localName,parents});
  }
 }
 scan(document);
 return {hits:hits.slice(0,8),root_count:roots.size};
}"""

def main():
    src=Path.home()/".sfdc_desktop"/"created_pmp_250pe_5sample_oppo_quote_PRIVATE.json"
    ref=json.loads(src.read_text(encoding="utf-8-sig")).get("new_opportunity_record_id")
    if not isinstance(ref,str) or not OPPO.fullmatch(ref):raise SystemExit("HOLD_INVALID_REFERENCE")
    with sync_playwright() as pw:
        b=pw.chromium.connect_over_cdp("http://127.0.0.1:9222")
        if len(b.contexts)!=1:raise SystemExit("HOLD_CONTEXT")
        p=b.contexts[0].new_page()
        try:
            p.goto("https://"+HOST+"/lightning/r/Opportunity/"+ref+"/view",
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
            tabs[0].click(timeout=10000)
            result=[]
            for _ in range(20):
                p.wait_for_timeout(400)
                result=[]
                for frame in p.frames:
                    try:
                        data=frame.evaluate(JS)
                        result+=data["hits"]
                    except Exception:pass
                if result:break
            print(json.dumps({"matching_heading_nodes":len(result),
                              "shape":result[:3],"save_clicked":False},ensure_ascii=True))
        finally:p.close()

if __name__=="__main__":
    main()
