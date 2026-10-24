#!/usr/bin/env python3
"""Read-only Salesforce Opportunity identity routing audit v2.

No identifiers, URLs, field values, customer names, HTML or screenshots printed.
Counts links/routes only. Candidate links DO NOT prove the current record ID.
"""
import argparse
import json
import re
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright
from runner import check_url, PROFILE

VERSION="opportunity-identity-v2"
RECORD_PATH=re.compile(r"/lightning/r/Opportunity/([A-Za-z0-9]{15}(?:[A-Za-z0-9]{3})?)/view(?:/|$)")
ANY_RECORD=re.compile(r"/lightning/r/Opportunity/([^/]+)/view(?:/|$)")
JS=r"""() => {
  const attrs=['href','data-record-id','data-recordid','data-target','data-url'];
  const seen=new Set(), tokens=[];
  let shadows=0, activeTabCount=0;
  function walk(root){
    if(!root||seen.has(root))return;
    seen.add(root);
    for(const el of root.querySelectorAll('*')){
      if(el.shadowRoot){shadows++;walk(el.shadowRoot);}
      if(el.matches('[role="tab"][aria-selected="true"], .slds-is-active[role="tab"]'))activeTabCount++;
      for(const attr of attrs){
        const raw=el.getAttribute(attr);
        if(raw && raw.length<2048 && (raw.includes('/lightning/r/Opportunity/') ||
          (attr.startsWith('data-record') && /^[A-Za-z0-9]{15}(?:[A-Za-z0-9]{3})?$/.test(raw)))){
           tokens.push({kind:attr,route:raw.includes('/lightning/r/Opportunity/'),
                        record_id_shape:/^[A-Za-z0-9]{15}(?:[A-Za-z0-9]{3})?$/.test(raw)});
        }
      }
    }
  }
  walk(document);
  return {shadow_roots:shadows,active_tab_indicators:activeTabCount,
    opportunity_link_candidates:tokens.filter(x=>x.route).length,
    record_id_attribute_candidates:tokens.filter(x=>x.record_id_shape).length};
}"""

def classify_url(url):
    check_url(url)
    path=urlparse(url).path
    return {"has_opportunity_record_route":bool(ANY_RECORD.search(path)),
            "valid_id_in_route":bool(RECORD_PATH.search(path)),
            "lightning_workspace_or_list":path.startswith("/lightning/") and not bool(ANY_RECORD.search(path))}

def inspect_context(ctx):
    result={"version":VERSION,"pages":0,"frames_inspected":0,"frames_failed":0,
      "route_record_id":False,"route_opportunity":False,"workspace_or_list_route":False,
      "opportunity_link_candidates":0,"record_id_attribute_candidates":0,
      "active_tab_indicators":0,"shadow_roots":0}
    for page in ctx.pages:
      if page.is_closed():continue
      try: route=classify_url(page.url)
      except ValueError:continue
      result["pages"]+=1
      result["route_record_id"] |= route["valid_id_in_route"]
      result["route_opportunity"] |= route["has_opportunity_record_route"]
      result["workspace_or_list_route"] |= route["lightning_workspace_or_list"]
      for frame in page.frames:
        try:
          data=frame.evaluate(JS)
          result["frames_inspected"]+=1
          for k in ("opportunity_link_candidates","record_id_attribute_candidates","active_tab_indicators","shadow_roots"):
            result[k]+=int(data[k])
        except Exception:
          result["frames_failed"]+=1
    result["note"]="Candidate links may refer to OTHER records. Do not infer current record ID from these counts."
    return result

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--url",required=True)
    a=p.parse_args();check_url(a.url)
    print("SFDC_ID_AUDIT_VERSION="+VERSION,flush=True)
    with sync_playwright() as pw:
        ctx=pw.chromium.launch_persistent_context(user_data_dir=str(PROFILE),channel="chrome",headless=False)
        try:
            page=ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto(a.url,wait_until="domcontentloaded")
            input("Open existing Opportunity Details in THIS Chrome, then press Enter: ")
            print(json.dumps(inspect_context(ctx),ensure_ascii=False,indent=2))
        finally:ctx.close()

if __name__=="__main__":main()
