#!/usr/bin/env python3
"""Read-only targeted inspection of Salesforce NEW Opportunity lookup controls."""
import argparse,json
from pathlib import Path
from playwright.sync_api import sync_playwright,Error as PWError
from runner import check_url

JS=r"""() => {
 const tidy=s=>(s||'').replace(/\s+/g,' ').trim();
 const seen=new Set(),out=[];
 function deep(root){
  if(!root||seen.has(root))return;
  seen.add(root);
  for(const e of root.querySelectorAll('*')){
   if(e.shadowRoot)deep(e.shadowRoot);
   if(e.localName!=='lightning-lookup')continue;
   const fieldText=tidy(e.innerText).slice(0,180);
   const found=[];
   function descend(r){
    if(!r)return;
    for(const x of r.querySelectorAll('*')){
     if(x.shadowRoot)descend(x.shadowRoot);
     if(x.matches('input,lightning-pill,.slds-pill,[data-selection],button,[role="button"]'))
      found.push({tag:x.localName,role:x.getAttribute('role'),
       aria:x.getAttribute('aria-label'),title:x.getAttribute('title'),
       value:x.matches('input')?x.value:null,
       text:tidy(x.innerText||x.textContent).slice(0,150)});
    }
   }
   descend(e);
   out.push({field_text:fieldText,controls:found.slice(0,70)});
  }
 }
 deep(document);
 return {lookup_count:out.length,lookups:out};
}"""
def main():
 p=argparse.ArgumentParser()
 p.add_argument("--cdp-url",default="http://127.0.0.1:9222")
 p.add_argument("--output",required=True)
 a=p.parse_args()
 with sync_playwright() as pw:
  browser=pw.chromium.connect_over_cdp(a.cdp_url)
  pages=[]
  for ctx in browser.contexts:
   for page in ctx.pages:
    try:
     check_url(page.url)
     if "new opportunity" in page.title().lower():pages.append(page)
    except (PWError,ValueError):pass
  if len(pages)!=1:raise RuntimeError("Open exactly one New Opportunity tab")
  result={"version":"lookup-control-readonly-v1","frames":[],"save_clicked":False}
  for frame in pages[0].frames:
   try:result["frames"].append(frame.evaluate(JS))
   except PWError:pass
  dest=Path(a.output);dest.parent.mkdir(parents=True,exist_ok=True)
  dest.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
  print("LOOKUPS:",sum(x["lookup_count"] for x in result["frames"]))
  print("REPORT:",dest)
  print("No clicks or Salesforce changes.")
if __name__=="__main__":main()
