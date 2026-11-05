#!/usr/bin/env python3
"""Audit Salesforce lookup suggestion text across open Shadow DOM and frames.
Single MFA/session, two fields, no option click and no Save.
Report contains customer names: keep it local, do not commit or paste publicly.
"""
import argparse,json,time
from pathlib import Path
from playwright.sync_api import sync_playwright,Error as PWError
from runner import check_url,PROFILE
from lookup_preflight import find_input,prepare_lookup
JS=r"""() => {
 const seen=new Set(), out=[];
 function visit(root) {
   if(!root || seen.has(root)) return;
   seen.add(root);
   for(const el of root.querySelectorAll('*')) {
     if(el.shadowRoot) visit(el.shadowRoot);
     const role=el.getAttribute('role');
     if(role==='option' || el.matches('lightning-base-combobox-item,li[role="option"]')) {
       const text=(el.innerText||el.textContent||'').replace(/\s+/g,' ').trim();
       if(text && el.getClientRects().length) out.push({tag:el.localName,role:role||'',
         text:text.slice(0,180)});
     }
   }
 }
 visit(document);
 const unique=[], keys=new Set();
 for(const item of out) {
   const k=item.tag+'|'+item.text;
   if(!keys.has(k)){keys.add(k);unique.push(item);}
 }
 return unique.slice(0,25);
}"""
def inspect(context):
    found=[]
    for page in context.pages:
        if page.is_closed():continue
        for frame in page.frames:
            try:found.extend(frame.evaluate(JS))
            except PWError:continue
    return found[:25]

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--url",required=True)
    ap.add_argument("--draft",required=True)
    ap.add_argument("--account-query",default="")
    ap.add_argument("--contact-query",default="")
    ap.add_argument("--output",default="")
    a=ap.parse_args();check_url(a.url)
    values=prepare_lookup(json.loads(Path(a.draft).read_text(encoding="utf-8-sig")))
    if a.account_query:values["Account Name"]=a.account_query
    if a.contact_query:values["Main Contact"]=a.contact_query
    with sync_playwright() as pw:
        ctx=pw.chromium.launch_persistent_context(user_data_dir=str(PROFILE),channel="chrome",headless=False)
        try:
            page=ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto(a.url,wait_until="domcontentloaded")
            input("Complete MFA, open New Opportunity, press Enter ONCE: ")
            report={"fields":{},"option_clicked":False,"save_clicked":False}
            for label in ("Account Name","Main Contact"):
                loc,status=find_input(ctx,label)
                if loc is None:
                    report["fields"][label]={"status":status};continue
                try:
                    loc.fill(values[label],timeout=3000)
                    time.sleep(1.0)
                    report["fields"][label]={"status":"QUERY_ENTERED","query":values[label],
                      "visible_options":inspect(ctx)}
                except PWError:
                    report["fields"][label]={"status":"FRAME_CHANGED"}
            path=Path(a.output) if a.output else Path(a.draft).with_name("lookup_suggestions_local.json")
            path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
            print(json.dumps(report,ensure_ascii=False,indent=2))
            print("LOCAL REPORT:",path)
            input("Inspect results in Chrome; Enter to close: ")
        finally:ctx.close()
if __name__=="__main__":main()
