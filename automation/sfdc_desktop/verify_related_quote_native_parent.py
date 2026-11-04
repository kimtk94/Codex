#!/usr/bin/env python3
"""Independently verify existing Quotation native ID and Opportunity parent.

Read-only browser traversal of the exact Salesforce Opportunity and Quotation
records. Never clicks Save, creates a quote, or logs customer identifiers.
Only the private workstation output contains native 006/a0P IDs.
"""
import argparse
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

HOST = "novogene.lightning.force.com"
OPPO = re.compile(r"006[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?\Z")
QUOTE = re.compile(r"a0P[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?\Z")
HREF_RE = re.compile(r"/lightning/r/(?:Opportunity|Quotation__c)/([^/?#]+)/view")
LINK_JS = r"""() => {
 const links=[], seen=new Set();
 function nearbyScope(el, kind) {
  let cursor=el;
  for(let n=0;cursor && n<12;n++) {
   const tag=(cursor.localName||'').toLowerCase();
   if(kind==='Opportunity') {
    if(tag==='record_flexipage-record-field') {
     // Reject unrelated console navigation: the parent must be in a
     // labelled field of the currently open Quotation Details.
     const label=(cursor.innerText||'').slice(0,250);
     return /(?:^|\s)Opportunity(?:\s+Name)?(?:\s|$)/i.test(label);
    }
   } else if(kind==='Quotation__c') {
    if(tag==='article' || tag==='lst-related-list-single-container' ||
       tag==='records-related-list') {
     const heading=cursor.querySelector('h2,h3,.slds-card__header-title');
     const title=(heading?.innerText||heading?.textContent||'').trim();
     return /^Quotations?(?:\s*\(\d+\))?$/i.test(title);
    }
   }
   cursor=cursor.parentElement || cursor.getRootNode()?.host || null;
  }
  return false;
 }
 function visit(root) {
  if(!root||seen.has(root))return;
  seen.add(root);
  for(const el of root.querySelectorAll('*')) {
    if(el.shadowRoot)visit(el.shadowRoot);
    if(el.tagName!=='A')continue;
    const href=el.getAttribute('href')||'';
    const match=href.match(/\/lightning\/r\/(Opportunity|Quotation__c)\/[A-Za-z0-9]{15,18}\/view(?:[/?#]|$)/);
    if(!match)continue;
    links.push({href, kind:match[1], scoped:nearbyScope(el, match[1])});
  }
 }
 visit(document);
 return links;
}"""


def same_native(a,b):
    if not isinstance(a,str) or not isinstance(b,str):
        return False
    if not ((OPPO.fullmatch(a) and OPPO.fullmatch(b)) or
            (QUOTE.fullmatch(a) and QUOTE.fullmatch(b))):
        return False
    return a==b if len(a)==len(b) else a[:15]==b[:15]


def identity_result(expected_opportunity, quote_ids, parents):
    if not OPPO.fullmatch(str(expected_opportunity or "")):
        return {"status":"HOLD_INVALID_OPPORTUNITY_ID","quote_id_verified":False,"parent_verified":False}
    if not isinstance(quote_ids,set) or not isinstance(parents,set):
        return {"status":"HOLD_INVALID_LINK_EVIDENCE","quote_id_verified":False,"parent_verified":False}
    if len(quote_ids)!=1 or not all(QUOTE.fullmatch(x) for x in quote_ids):
        return {"status":"HOLD_QUOTE_LINK_NOT_UNIQUE","quote_id_verified":False,"parent_verified":False}
    if len(parents)!=1 or not all(OPPO.fullmatch(x) for x in parents):
        return {"status":"HOLD_QUOTE_PARENT_NOT_UNIQUE","quote_id_verified":True,"parent_verified":False}
    actual=next(iter(parents))
    if not same_native(expected_opportunity,actual):
        return {"status":"HOLD_QUOTE_PARENT_ID_MISMATCH","quote_id_verified":True,"parent_verified":False}
    return {"status":"QUOTE_NATIVE_PARENT_MATCH_REVIEW_COMPLETE","quote_id_verified":True,"parent_verified":True}


def scoped_link_ids(items):
    """Only trust links in a labelled field or the Quotation Related section.

    An unrelated Salesforce console tab, global search result, or another
    record's link cannot supply proof of the current Quote's native parent.
    """
    out={"Opportunity":set(),"Quotation__c":set()}
    if not isinstance(items,list):
        return out
    for row in items:
        if not isinstance(row,dict) or row.get("scoped") is not True:
            continue
        kind=row.get("kind")
        href=row.get("href")
        if kind not in out or not isinstance(href,str):
            continue
        match=HREF_RE.search(href)
        if not match:continue
        record=match.group(1)
        if (kind=="Opportunity" and "/Opportunity/" in href and OPPO.fullmatch(record)) or (
                kind=="Quotation__c" and "/Quotation__c/" in href and QUOTE.fullmatch(record)):
            out[kind].add(record)
    return out


def get_links(page):
    candidates=[]
    for frame in page.frames:
        try:
            candidates.extend(frame.evaluate(LINK_JS))
        except Exception:
            continue
    return scoped_link_ids(candidates)


def run_live(expected):
    from playwright.sync_api import sync_playwright
    from audit_quote_related_after_save import classify_related_text
    with sync_playwright() as pw:
        browser=pw.chromium.connect_over_cdp("http://127.0.0.1:9222",timeout=15000)
        if len(browser.contexts)!=1:
            return {"status":"HOLD_CHROME_CONTEXT_COUNT","quote_id_verified":False,"parent_verified":False}
        ctx=browser.contexts[0]
        page=ctx.new_page()
        try:
            page.goto("https://"+HOST+"/lightning/r/Opportunity/"+expected+"/view",
                      wait_until="domcontentloaded",timeout=35000)
            if (urlsplit(page.url).hostname != HOST or
                    urlsplit(page.url).path != "/lightning/r/Opportunity/"+expected+"/view"):
                return {"status":"HOLD_OPPORTUNITY_NAVIGATION","quote_id_verified":False,"parent_verified":False}
            tabs=[]
            for _ in range(30):
                tabs=[]
                for frame in page.frames:
                    try:
                        candidate=frame.get_by_role("tab",name="Related",exact=True)
                        if candidate.count()==1 and candidate.is_visible():
                            tabs.append(candidate)
                    except Exception:continue
                if len(tabs)==1:break
                page.wait_for_timeout(500)
            if len(tabs)!=1:
                return {"status":"HOLD_RELATED_TAB_NOT_UNIQUE","quote_id_verified":False,"parent_verified":False}
            tabs[0].click(timeout=12000)
            link_ids=set()
            related=None
            for _ in range(30):
                page.wait_for_timeout(400)
                related=classify_related_text(page.locator("body").inner_text(timeout=5000))
                if related["related_quote_count"]==1:
                    link_ids=get_links(page)["Quotation__c"]
                    if link_ids:break
            if not related or related["related_quote_count"]!=1:
                return {"status":"HOLD_RELATED_COUNT_NOT_EXACTLY_ONE","quote_id_verified":False,"parent_verified":False}
            if len(link_ids)!=1:
                return {"status":"HOLD_QUOTE_ANCHOR_NOT_UNIQUE","quote_id_verified":False,"parent_verified":False}
            quote_id=next(iter(link_ids))
            q=ctx.new_page()
            try:
                q.goto("https://"+HOST+"/lightning/r/Quotation__c/"+quote_id+"/view",
                      wait_until="domcontentloaded",timeout=35000)
                if (urlsplit(q.url).hostname!=HOST or
                        urlsplit(q.url).path != "/lightning/r/Quotation__c/"+quote_id+"/view"):
                    return {"status":"HOLD_QUOTE_NAVIGATION","quote_id_verified":False,"parent_verified":False}
                tab=q.get_by_role("tab",name="Details",exact=True)
                if tab.count()==1:tab.click(timeout=7000)
                parents=set()
                for _ in range(24):
                    q.wait_for_timeout(400)
                    parents=get_links(q)["Opportunity"]
                    if parents:break
                verdict=identity_result(expected,{quote_id},parents)
                verdict.update({"opportunity_id_private":expected,
                                "quotation_id_private":quote_id,
                                "parent_link_count":len(parents)})
                return verdict
            finally:q.close()
        finally:page.close()


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--source",default=str(Path.home()/".sfdc_desktop"/"created_pmp_250pe_5sample_oppo_quote_PRIVATE.json"))
    p.add_argument("--output",default=str(Path.home()/".sfdc_desktop"/"quote_parent_native_verification_PRIVATE.json"))
    args=p.parse_args()
    source=json.loads(Path(args.source).read_text(encoding="utf-8-sig"))
    expected=source.get("new_opportunity_record_id")
    if not OPPO.fullmatch(str(expected or "")):
        raise SystemExit("HOLD_PRIVATE_OPPORTUNITY_ID_UNVERIFIED")
    result=run_live(expected)
    result.update({"version":"sfdc-quote-parent-native-audit-v1",
                   "read_only":True,"save_clicked":False,"create_allowed":False})
    target=Path(args.output)
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print("QUOTE_IDENTITY_STATUS",result["status"])
    print("QUOTE_ID_VERIFIED",result.get("quote_id_verified",False))
    print("PARENT_VERIFIED",result.get("parent_verified",False))
    print("CREATE_ALLOWED",False)


if __name__=="__main__":
    main()
