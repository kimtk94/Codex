#!/usr/bin/env python3
"""Anonymous field-scoping probe for Opportunity-linked Korean Contacts.

All source records remain in a private local folder. Outputs structural
counts only; never prints names, email, native IDs, URLs, or browser contents.
No Salesforce mutation or Save.
"""
import json
import re
from pathlib import Path

from playwright.sync_api import sync_playwright
from contact_oppo_selection import ID_CONTACT, ID_OPPORTUNITY

ROOT=Path.home()/".sfdc_desktop"
HOST="novogene.lightning.force.com"
HANGUL=re.compile(r"^[가-힣]{2,6}(?:\s|$)")

ANCESTORS=r"""(el)=>{
 const res=[];
 let cur=el;
 for(let depth=0;cur&&depth<12;depth++){
  const nodes=[];
  const seen=new Set();
  function scan(root){
   if(!root||seen.has(root))return;
   seen.add(root);
   for(const x of root.querySelectorAll('*')){nodes.push(x);if(x.shadowRoot)scan(x.shadowRoot);}
  }
  scan(cur.shadowRoot||cur);
  const links=nodes.filter(x=>x.tagName==='A').map(x=>x.getAttribute('href')||'');
  res.push({tag:cur.localName,depth,
    contact:links.filter(x=>/\/(?:Contact\/)?003[A-Za-z0-9]{12}/.test(x)).length,
    account:links.filter(x=>/\/(?:Account\/)?001[A-Za-z0-9]{12}/.test(x)).length,
    opportunity:links.filter(x=>/\/(?:Opportunity\/)?006[A-Za-z0-9]{12}/.test(x)).length,
    mailto:links.filter(x=>x.startsWith('mailto:')).length,
    link_total:links.length,
    lightning_links:links.filter(x=>x.includes("/lightning/r/")).length,
    text_length:(cur.innerText||'').length,
    field_host:/record_flexipage-record-field|lightning-output-field/.test(cur.localName||'')
  });
  cur=cur.parentElement||cur.getRootNode()?.host||null;
 }
 return res;
}"""


def choose():
    manifest={x["opportunity_id"]:x for x in json.loads(
        (ROOT/"oppo_linked_contact_candidate_manifest_PRIVATE.json").read_text(encoding="utf-8-sig"))}
    raw=json.loads((ROOT/"oppo_main_contact_identity_batch180_PRIVATE.json").read_text(encoding="utf-8-sig"))
    candidates=[]
    for record in raw:
        if record.get("result")!="PASS_ID_AND_CANDIDATE":
            continue
        opp=record.get("opportunity_id")
        entry=manifest.get(opp)
        ids=record.get("actual_contact_ids",[])
        if not entry or len(ids)!=1 or not ID_CONTACT.fullmatch(ids[0]) or not ID_OPPORTUNITY.fullmatch(opp):
            continue
        if HANGUL.match(entry.get("contact_display") or ""):
            candidates.append((opp,ids[0],entry["contact_display"]))
    if not candidates:
        raise ValueError("NO_KOREAN_CONTACT_LINK_CANDIDATE")
    return candidates[0]


def collect(page,label):
    locator=page.get_by_text(label,exact=True)
    count=locator.count()
    profiles=[]
    for i in range(min(count,4)):
        try:
            profiles.append(locator.nth(i).evaluate(ANCESTORS))
        except Exception:
            continue
    return {"label_occurrences":count,"profiles":profiles}


def detail_tab(page):
    tab=page.get_by_role("tab",name="Details",exact=True)
    tab.wait_for(state="visible",timeout=18000)
    if tab.get_attribute("aria-selected")!="true":
        tab.click(timeout=8000)
    page.wait_for_timeout(1100)


def run():
    opp,cid,display=choose()
    with sync_playwright() as pw:
        browser=pw.chromium.connect_over_cdp("http://127.0.0.1:9222",timeout=16000)
        if len(browser.contexts)!=1:
            raise ValueError("CHROME_CONTEXT_AMBIGUOUS")
        page=browser.contexts[0].new_page()
        try:
            results={}
            for kind,identifier in (("Opportunity",opp),("Contact",cid)):
                url="https://"+HOST+"/lightning/r/"+kind+"/"+identifier+"/view"
                page.goto(url,wait_until="domcontentloaded",timeout=36000)
                if not page.url.startswith(url):
                    raise ValueError("RECORD_ROUTE_CHANGED")
                detail_tab(page)
                info={}
                for label in (("Main Contact","Account Name") if kind=="Opportunity" else
                              ("Account Name","Email","Full Name","First Name","Last Name")):
                    info[label]=collect(page,label)
                headings=page.get_by_role("heading").all_text_contents()
                results[kind]={"fields":info,
                               "bilingual_name_in_headings":any(display in x for x in headings),
                               "headings_count":len(headings)}
            print(json.dumps({"status":"STRUCTURE_ONLY","source_has_korean":True,
                              "results":results,"save_clicked":False},ensure_ascii=True))
        finally:
            page.close()

if __name__=="__main__":
    run()
