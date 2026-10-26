#!/usr/bin/env python3
"""Read-only exact business-ID probe across Salesforce Lightning frames and shadow DOM."""
import argparse,json,re
from pathlib import Path
from playwright.sync_api import sync_playwright,Error as PWError
from runner import check_url

JS=r"""(ids) => {
 const matches=[],seen=new Set();
 function walk(root){
  if(!root||seen.has(root))return;
  seen.add(root);
  for(const el of root.querySelectorAll('*')){
   if(el.shadowRoot)walk(el.shadowRoot);
   if(el.children.length>4)continue;
   const content=(el.innerText||el.textContent||'').trim();
   if(!content||content.length>500)continue;
   for(const id of ids){
    if(content.includes(id)){
     matches.push({id,tag:el.localName,text:content.slice(0,220),
       parent:(el.parentElement?.innerText||'').trim().slice(0,350),
       in_record_field:!!el.closest('.test-id__output-root'),
       in_list_header:!!el.closest('[role="columnheader"],th')});
    }
   }
  }
 }
 walk(document);
 return {roots:seen.size,matches:matches.slice(0,60)};
}"""
def main():
 p=argparse.ArgumentParser()
 p.add_argument("--cdp-url",default="http://127.0.0.1:9222")
 p.add_argument("--output",required=True)
 p.add_argument("--expected",action="append",required=True,help="Business ID from Details, e.g. Opp-2026-10-23-291068")
 a=p.parse_args()
 for v in a.expected:
  if not re.fullmatch(r"Opp-\d{4}-\d{2}-\d{2}-\d+",v):p.error("Invalid business ID")
 with sync_playwright() as pw:
  browser=pw.chromium.connect_over_cdp(a.cdp_url)
  pages=[]
  for ctx in browser.contexts:
   for page in ctx.pages:
    try:
     check_url(page.url)
     if "opportunity" in page.title().lower() and "new opportunity" not in page.title().lower():
      pages.append(page)
    except (PWError,ValueError):pass
  if len(pages)!=1:raise RuntimeError(f"Expected exactly one Opportunity tab, found {len(pages)}")
  page=pages[0]
  m=re.search(r"/lightning/r/Opportunity/([A-Za-z0-9]{15,18})(?:/|$)",page.url)
  if not m:raise RuntimeError("Expected an existing Opportunity record URL")
  input("Open the section showing the business Opportunity ID in Salesforce, then press Enter: ")
  result={"version":"exact-business-id-probe-v1","record_id":m.group(1),"expected":a.expected,"frames":[],"salesforce_modified":False}
  for frame in page.frames:
   entry={"frame_name":frame.name,"matches":[],"locator_counts":{}}
   try:entry.update(frame.evaluate(JS,a.expected))
   except PWError as e:entry["error"]=type(e).__name__
   for id in a.expected:
    try:
     loc=frame.get_by_text(id,exact=False)
     entry["locator_counts"][id]=loc.count()
    except PWError:entry["locator_counts"][id]=-1
   result["frames"].append(entry)
  dest=Path(a.output);dest.parent.mkdir(parents=True,exist_ok=True)
  dest.write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding="utf-8")
  for id in a.expected:
   print(id,"DOM_MATCHES:",sum(sum(x["id"]==id for x in frame.get("matches",[])) for frame in result["frames"]),
         "PLAYWRIGHT_MATCHES:",sum(frame["locator_counts"].get(id,0) for frame in result["frames"] if frame["locator_counts"].get(id,0)>0))
  print("REPORT:",dest)
  print("No Salesforce edits or Save.")
if __name__=="__main__":main()
