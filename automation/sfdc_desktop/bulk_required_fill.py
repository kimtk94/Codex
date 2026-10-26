#!/usr/bin/env python3
"""Bulk unsaved Salesforce Opportunity form fill on an authenticated CDP Chrome.
Never clicks Save. No guessed business amounts, close dates or mandatory options.
"""
import argparse,json,re,time
from pathlib import Path
from playwright.sync_api import sync_playwright, Error as PWError
from runner import check_url
from lookup_batch_audit import window_inventory,focus_and_maximize
from lookup_exact_option_probe import select,selected_state

TEXT_FIELDS=("Opportunity Name","Amount","Close Date","Progress Description")
PICK_FIELDS=("Opportunity Currency","Stage","Forecast Category","Status")
REQUIRED=("Opportunity Name","Account Name","Main Contact","Amount","Opportunity Currency",
          "Close Date","Service Line","Stage","Forecast Category","Progress Description","Status")
FIND_JS=r"""(label) => {
 const norm=s=>(s||'').replace(/\s+/g,' ').replace(/^\*\s*/,'').trim();
 const visited=new Set(),out=[];
 function walk(root){
  if(!root||visited.has(root))return;
  visited.add(root);
  for(const e of root.querySelectorAll('*')){
   if(e.shadowRoot)walk(e.shadowRoot);
   if(e.matches('label')&&norm(e.textContent)===label)out.push(e);
  }
 }
 walk(document);
 let controls=[];
 for(const e of out){
  let n=e;
  for(let depth=0;depth<6&&n;depth++){
   if(n.localName?.startsWith('lightning-') && (
      n.localName==='lightning-input'||n.localName==='lightning-textarea'||
      n.localName==='lightning-combobox'||n.localName==='lightning-dual-listbox'))break;
   n=n.parentElement||n.getRootNode()?.host||null;
  }
  if(n){
   const found=[];
   function collect(root){
    if(!root?.querySelectorAll)return;
    for(const x of root.querySelectorAll('*')){
     if(x.matches('input:not([type="hidden"]),textarea,button[role="combobox"],[role="combobox"]'))found.push(x);
     if(x.shadowRoot)collect(x.shadowRoot);
    }
   }
   collect(n.shadowRoot||n);
   if(found.length===1)controls.push(found[0]);
  }
 }
 return controls.length===1?controls[0]:null;
}"""

def field_control(ctx,label):
    matches=[]
    for page in ctx.pages:
        if page.is_closed():continue
        for frame in page.frames:
            try:
                e=frame.evaluate_handle(FIND_JS,label).as_element()
                if e and e.is_visible() and e.is_enabled():matches.append(e)
            except PWError:continue
    return matches[0] if len(matches)==1 else None

def do_fill(ctx,label,value):
    if not str(value).strip():return {"status":"MISSING_VALUE"}
    locator=field_control(ctx,label)
    if locator is None:return {"status":"CONTROL_NOT_UNIQUE"}
    try:
        locator.fill(str(value),timeout=2500)
        actual=locator.input_value(timeout=1500)
        return {"status":"FILLED_NOT_SAVED" if actual==str(value) else "VALUE_MISMATCH"}
    except PWError:return {"status":"FILL_FAILED"}

def do_pick(ctx,label,value):
    if not str(value).strip():return {"status":"MISSING_VALUE"}
    locator=field_control(ctx,label)
    if locator is None:return {"status":"CONTROL_NOT_UNIQUE"}
    try:
        locator.click(timeout=2500)
        # Exact unique displayed option; do not select similarly named values.
        found=[]
        for page in ctx.pages:
            if page.is_closed():continue
            for frame in page.frames:
                try:
                    loc=frame.get_by_role("option",name=str(value),exact=True)
                    for i in range(loc.count()):
                        x=loc.nth(i)
                        if x.is_visible():found.append(x)
                except PWError:continue
        if len(found)!=1:return {"status":"OPTION_NOT_UNIQUE","count":len(found)}
        found[0].click(timeout=2500)
        return {"status":"OPTION_CLICKED_NOT_VERIFIED"}
    except PWError:return {"status":"PICK_FAILED"}

def main():
    a=argparse.ArgumentParser()
    a.add_argument("--url",required=True)
    a.add_argument("--draft",required=True)
    a.add_argument("--values",default="",help="JSON file with actual business values; overrides draft")
    a.add_argument("--cdp-url",default="http://127.0.0.1:9222")
    a.add_argument("--output",default="")
    args=a.parse_args();check_url(args.url)
    data=json.loads(Path(args.draft).read_text(encoding="utf-8-sig"))
    if args.values:data.update(json.loads(Path(args.values).read_text(encoding="utf-8-sig")))
    # Produce a useful template before connecting to Chrome, never invent mandatory fields.
    missing=[k for k in REQUIRED if not str(data.get(k,"")).strip()]
    template=Path(args.draft).with_name("required_values_template.json")
    if not args.values:
        template.write_text(json.dumps({k:data.get(k,"") for k in REQUIRED},ensure_ascii=False,indent=2),encoding="utf-8")
        print("Required values template:",template)
    if missing:
        print("Missing values (will SKIP these fields, not Save):",", ".join(missing))
    if not any(str(data.get(k,"")).strip() for k in REQUIRED):
        print("No supplied data; no Salesforce changes attempted.")
        return
    with sync_playwright() as pw:
        browser=pw.chromium.connect_over_cdp(args.cdp_url)
        if not browser.contexts:raise RuntimeError("No authenticated Chrome context")
        ctx=browser.contexts[0]
        input("Open ONE New Opportunity in the CDP Chrome, press Enter ONCE: ")
        inventory=window_inventory(ctx)
        matches=[]
        for item in inventory:
            page=ctx.pages[item["tab_index"]]
            try:title=page.title().lower()
            except PWError:title=""
            if "new opportunity" in title and (item["origin"].endswith("force.com") or item["origin"].endswith("salesforce.com")):
                matches.append(item)
        if len(matches)!=1:raise RuntimeError("Cannot identify exactly one New Opportunity tab; no input")
        focus=focus_and_maximize(ctx.pages[matches[0]["tab_index"]])
        result={}
        for label in ("Account Name","Main Contact"):
            try:
                if selected_state(ctx,label,str(data[label])).get("verified"):
                    result[label]={"status":"SELECTED_PILL_VERIFIED"}
                else:result[label]=select(ctx,label,str(data[label]))
            except Exception as exc:result[label]={"status":"ERROR","type":type(exc).__name__}
            print(label, result[label]["status"])
        for label in TEXT_FIELDS:
            result[label]=do_fill(ctx,label,data[label])
            print(label,result[label]["status"])
        for label in PICK_FIELDS:
            result[label]=do_pick(ctx,label,data[label])
            print(label,result[label]["status"])
        result["Service Line"]={"status":"NOT_IMPLEMENTED_DUAL_LISTBOX" if str(data.get("Service Line","")).strip() else "MISSING_VALUE"}
        report={"version":"bulk-required-p1","window":focus,"missing_values":missing,"fields":result,
                "save_clicked":False,"all_required_verified":False}
        out=Path(args.output) if args.output else Path(args.draft).with_name("bulk_required_report.json")
        out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
        print("REPORT:",out)
        print("Save NOT clicked; Service Line requires separate validated dual-listbox handling.")
        input("Inspect New Opportunity fields, Enter to finish; Chrome stays open: ")

if __name__=="__main__":main()
