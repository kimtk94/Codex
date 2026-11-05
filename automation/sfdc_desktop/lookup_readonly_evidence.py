#!/usr/bin/env python3
"""Read-only audit of selected Salesforce New Opportunity lookup pills. NO input or Save."""
import argparse,json
from pathlib import Path
from playwright.sync_api import sync_playwright,Error as PWError
from runner import check_url

JS=r"""(labels) => {
 const tidy=s=>(s||'').replace(/\s+/g,' ').trim();
 const out={};
 function deep(root,arr=[],visited=new Set()){
  if(!root||visited.has(root))return arr;
  visited.add(root);
  for(const e of root.querySelectorAll('*')){
   arr.push(e);
   if(e.shadowRoot)deep(e.shadowRoot,arr,visited);
  }
  return arr;
 }
 const nodes=deep(document);
 for(const label of labels){
  const norm=s=>tidy(s).replace(/^\*/,'').trim().toLowerCase();
  const matching=nodes.filter(e=>e.matches('label,.slds-form-element__label') &&
     norm(e.textContent)===norm(label));
  const evidence=[];
  for(const el of matching){
   let cur=el;
   const ancestors=[];
   for(let i=0;i<12&&cur;i++){
    ancestors.push(cur);
    cur=cur.parentElement||cur.getRootNode()?.host||null;
   }
   let containers=ancestors.filter(e=>e.matches('lightning-grouped-combobox,.slds-form-element,lightning-input-field,.slds-form-element__control'));
   if(!containers.length)containers=ancestors.slice(1,5);
   for(const region of containers.slice(0,4)){
    const descendants=deep(region);
    const pills=descendants.filter(e=>e.matches('lightning-pill,.slds-pill,[data-selection]')).map(e=>({
      tag:e.localName,text:tidy(e.innerText||e.textContent).slice(0,180),
      label:e.getAttribute('label')||'',
      buttons:deep(e).filter(x=>x.matches('button,[role="button"]')).map(x=>x.getAttribute('title')||x.getAttribute('aria-label')||'').filter(Boolean).slice(0,4)
    })).slice(0,8);
    evidence.push({container_tag:region.localName,container_class:String(region.className||'').slice(0,100),
      pill_count:pills.length,pills,selected_text:tidy(region.innerText).slice(0,180)});
   }
  }
  out[label]={label_count:matching.length,evidence};
 }
 return out;
}"""
def main():
 p=argparse.ArgumentParser()
 p.add_argument("--cdp-url",default="http://127.0.0.1:9222")
 p.add_argument("--draft",required=True)
 p.add_argument("--output",default="")
 a=p.parse_args()
 draft=json.loads(Path(a.draft).read_text(encoding="utf-8-sig"))
 with sync_playwright() as pw:
  browser=pw.chromium.connect_over_cdp(a.cdp_url)
  pages=[]
  for ctx in browser.contexts:
   for page in ctx.pages:
    try:
     check_url(page.url)
     if "new opportunity" in page.title().lower():pages.append(page)
    except (PWError,ValueError):pass
  if len(pages)!=1:raise RuntimeError("Expected exactly one New Opportunity tab")
  result={"version":"new-opportunity-lookup-readonly-v1","fields":{},"save_clicked":False}
  for frame in pages[0].frames:
   try:
    data=frame.evaluate(JS,["Account Name","Main Contact"])
    for label,item in data.items():
     if item["label_count"]:result["fields"].setdefault(label,[]).append(item)
   except PWError:pass
  for label in ("Account Name","Main Contact"):
   expected=str(draft.get(label) or "").strip()
   regions=result["fields"].get(label,[])
   matched=any(expected and expected.casefold() in (p["text"]+" "+p["label"]).casefold()
       for region in regions for ev in region["evidence"] for p in ev["pills"])
   print(label,"PILL_TEXT_MATCH" if matched else "UNVERIFIED","LABEL_REGIONS",len(regions))
  out=Path(a.output) if a.output else Path(a.draft).with_name("lookup_readonly_evidence.json")
  out.parent.mkdir(parents=True,exist_ok=True)
  out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
  print("REPORT:",out)
  print("No clicks, edits, or Save.")
if __name__=="__main__":main()
