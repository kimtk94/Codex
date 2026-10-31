#!/usr/bin/env python3
"""Three-path Salesforce Lightning lookup inspector. READ ONLY, NO SAVE.

In one authenticated Chrome session, compares:
A. Label -> closest Lightning grouped-combobox across shadow hosts
B. HTML label[for] -> input[id] association across open roots
C. Playwright accessible name/role and host-scoped locator counts
No values, customer identities, screenshots, URLs or selectors in output.
"""
import argparse
import json
import time
from pathlib import Path
from playwright.sync_api import sync_playwright, Error as PWError
from runner import check_url, PROFILE

FIELDS = ("Account Name", "Main Contact")
JS = r"""(target) => {
 const norm = s => (s||'').replace(/\s+/g,' ').replace(/^\*\s*/, '').trim();
 const roots=[], seen=new Set();
 function visit(root) {
   if(!root || seen.has(root)) return;
   seen.add(root); roots.push(root);
   for(const e of root.querySelectorAll('*')) if(e.shadowRoot) visit(e.shadowRoot);
 }
 visit(document);
 const labels=[], hosts=[], inputs=[];
 for(const root of roots) for(const e of root.querySelectorAll('*')) {
   if(e.matches('label') && norm(e.textContent)===target) labels.push(e);
   if(e.matches('lightning-grouped-combobox')) hosts.push(e);
   if(e.matches('input:not([type="hidden"])')) inputs.push(e);
 }
 const strategyA=[];
 for(const label of labels){
   let n=label;
   while(n && n.tagName?.toLowerCase()!=='lightning-grouped-combobox')
      n=n.parentElement || n.getRootNode()?.host || null;
   if(n && !strategyA.includes(n)) strategyA.push(n);
 }
 function descendantInputCount(host) {
    const found = new Set();
    function scan(root) {
      if(!root)return;
      for(const e of root.querySelectorAll('*')){
        if(e.matches('input:not([type="hidden"])')) found.add(e);
        if(e.shadowRoot)scan(e.shadowRoot);
      }
    }
    scan(host.shadowRoot || host);
    return {inputs:found.size, usable:[...found].filter(e=>!e.disabled && e.getClientRects().length>0).length};
 }
 // Strategy B: for/id scoped to the label's root; do not emit IDs.
 let idLinks=0, idUsable=0;
 for(const label of labels) {
   const id=label.getAttribute('for');
   if(!id)continue;
   const root=label.getRootNode();
   const el=[...root.querySelectorAll('input')].find(e=>e.id===id);
   if(el){idLinks++;if(!el.disabled && el.getClientRects().length>0) idUsable++;}
 }
 const aCounts=strategyA.map(descendantInputCount);
 // Strategy C candidate scope: host input structure, without any entered values.
 const hostCounts=hosts.map(descendantInputCount);
 return {label_count:labels.length, grouped_hosts:hosts.length,
   shadow_roots:roots.length-1,
   strategy_A:{host_count:strategyA.length, input_count:aCounts.reduce((s,x)=>s+x.inputs,0),
     usable_count:aCounts.reduce((s,x)=>s+x.usable,0)},
   strategy_B:{linked_input_count:idLinks,usable_count:idUsable},
   strategy_C_host_inventory:{hosts_with_one_input:hostCounts.filter(x=>x.inputs===1).length,
     hosts_with_usable_input:hostCounts.filter(x=>x.usable===1).length}};
}"""

def one_pass(context):
    results={field:{"frames":[], "strategy_C_accessibility":{"by_label":0,"textbox":0,"combobox":0}} for field in FIELDS}
    errors={}
    for page in context.pages:
        if page.is_closed():continue
        for idx,frame in enumerate(page.frames):
            for field in FIELDS:
                try:
                    result=frame.evaluate(JS,field)
                    if result["label_count"] or result["strategy_A"]["host_count"]:
                        results[field]["frames"].append(result)
                except PWError as exc:
                    msg=str(exc).lower()
                    key=("FRAME_DETACHED" if "detached" in msg else
                         "NAVIGATION" if "navigation" in msg or "execution context" in msg else
                         "OTHER")
                    errors[key]=errors.get(key,0)+1
        for field in FIELDS:
            for role, getter in (("by_label",lambda:page.get_by_label(field,exact=True)),
                                 ("textbox",lambda:page.get_by_role("textbox",name=field,exact=True)),
                                 ("combobox",lambda:page.get_by_role("combobox",name=field,exact=True))):
                try:results[field]["strategy_C_accessibility"][role]+=getter().count()
                except PWError: errors["ACCESSIBILITY_ERROR"]=errors.get("ACCESSIBILITY_ERROR",0)+1
    return {"fields":results,"frame_errors":errors}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--url",required=True)
    p.add_argument("--output",default="sfdc_lookup_three_strategy_report.json")
    p.add_argument("--attempts",type=int,default=5)
    a=p.parse_args()
    check_url(a.url)
    if not 1<=a.attempts<=10: p.error("--attempts range 1..10")
    with sync_playwright() as pw:
        ctx=pw.chromium.launch_persistent_context(user_data_dir=str(PROFILE),channel="chrome",headless=False)
        try:
            page=ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto(a.url,wait_until="domcontentloaded")
            input("Complete MFA, open New Opportunity in THIS Chrome, press Enter once: ")
            passes=[]
            for i in range(a.attempts):
                item=one_pass(ctx)
                item["attempt"]=i+1
                passes.append(item)
                if all(item["fields"][f]["frames"] for f in FIELDS): break
                time.sleep(0.8)
            report={"version":"lookup-three-strategy-v1","mode":"READ_ONLY",
              "passes":passes,"save_clicked":False,"lookup_selected":False,
              "note":"Only structural counts; no input values, labels other than expected, tokens or customer data."}
            Path(a.output).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
            print(json.dumps({"attempts":len(passes),"last":passes[-1],"save_clicked":False},ensure_ascii=False,indent=2))
            print("REPORT:",Path(a.output).resolve())
            input("Press Enter to close the browser: ")
        finally:ctx.close()
if __name__=="__main__":main()
