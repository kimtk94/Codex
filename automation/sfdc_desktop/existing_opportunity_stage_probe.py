#!/usr/bin/env python3
"""Read-only Salesforce Opportunity stage/date diagnostic. Never modifies UI."""
import argparse,json,re
from pathlib import Path
from playwright.sync_api import sync_playwright,Error as PWError
from runner import check_url

JS=r"""() => {
 const terms=/^(Stage|Created Date|Last Modified Date|Forecast Category|Status)$/i;
 const found=[],seen=new Set();
 const tidy=s=>(s||'').replace(/\s+/g,' ').trim();
 function visit(root){
  if(!root||seen.has(root))return;
  seen.add(root);
  for(const el of root.querySelectorAll('*')){
   if(el.shadowRoot)visit(el.shadowRoot);
   if(!el.matches('.slds-form-element.test-id__output-root'))continue;
   const label=tidy(el.querySelector('.test-id__field-label')?.textContent);
   if(!terms.test(label))continue;
   const control=el.querySelector('.slds-form-element__control');
   let val=tidy(control?.innerText);
   const suffix='Edit '+label;
   if(val.toLowerCase().endsWith(suffix.toLowerCase()))val=val.slice(0,-suffix.length).trim();
   found.push({label,value:val||null,field_region:'record_detail_output',
               status:val?'CANDIDATE_VALUE':'EMPTY_OR_NOT_RENDERED'});
  }
 }
 visit(document);
 return {shadow_roots:seen.size-1,candidates:found.slice(0,100)};
}"""

def main():
 p=argparse.ArgumentParser()
 p.add_argument("--cdp-url",default="http://127.0.0.1:9222")
 p.add_argument("--output",required=True)
 a=p.parse_args()
 with sync_playwright() as pw:
  browser=pw.chromium.connect_over_cdp(a.cdp_url)
  candidates=[]
  for ctx in browser.contexts:
   for page in ctx.pages:
    try:
     check_url(page.url)
     if "opportunity" in page.title().lower() and "new opportunity" not in page.title().lower():
      candidates.append(page)
    except (PWError,ValueError):pass
  if len(candidates)!=1:raise RuntimeError(f"Expected one existing Opportunity page, found {len(candidates)}")
  page=candidates[0]
  input("Open Details on the existing Opportunity (without editing), then press Enter: ")
  info={"version":"stage-probe-v2","record_id":None,"frames":[],"read_only":True}
  m=re.search(r"/lightning/r/Opportunity/([A-Za-z0-9]{15,18})(?:/|$)",page.url)
  if m:info["record_id"]=m.group(1)
  if not info["record_id"]:raise RuntimeError("Not on a canonical Opportunity record route")
  for frame in page.frames:
   try:info["frames"].append(frame.evaluate(JS))
   except PWError:pass
  dest=Path(a.output)
  dest.parent.mkdir(parents=True,exist_ok=True)
  dest.write_text(json.dumps(info,ensure_ascii=False,indent=2),encoding="utf-8")
  print("RECORD ID:",info["record_id"] or "NOT_FOUND")
  print("STAGE/DATE LABEL CANDIDATES:",sum(len(f["candidates"]) for f in info["frames"]))
  print("REPORT:",dest)
  print("Read only. Candidate text is not verified as the field value.")
if __name__=="__main__":main()
