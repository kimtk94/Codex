#!/usr/bin/env python3
"""SFDC Lookup resolver v2: inspect ONLY dropdown attached to the active lookup.
Safe by default: no Save; exact unique suggestion and confirmed selected pill required.
"""
import argparse,json,re,time
from pathlib import Path
from playwright.sync_api import sync_playwright, Error as PWError
from runner import check_url, PROFILE
from lookup_preflight import prepare_lookup, find_input

def norm(value):
    return re.sub(r"\s+"," ",str(value or "")).strip().casefold()

# Evaluate relative to the ACTUAL input, not all options on the page.
SUGGESTION_JS=r"""(input) => {
 const root=input.getRootNode();
 const owners=[];
 let n=input;
 while(n){owners.push(n);if(n.localName==='lightning-grouped-combobox')break;
   n=n.parentElement||n.getRootNode()?.host||null;}
 const host=owners[owners.length-1];
 const controls=input.getAttribute('aria-controls')||input.getAttribute('aria-owns');
 const selectors=['[role="listbox"]','[role="option"]',
                   'lightning-base-combobox-item','.slds-listbox__item'];
 const regions=new Set();
 // Search only the lookup host and its parents until the grouped-combobox.
 for(const node of owners){
   if(!node.querySelectorAll)continue;
   for(const sel of selectors.slice(0,1)){
     for(const el of node.querySelectorAll(sel)) regions.add(el);
     if(node.shadowRoot)for(const el of node.shadowRoot.querySelectorAll(sel))regions.add(el);
   }
 }
 if(controls){
   for(const r of [root,document,host?.shadowRoot]){
     if(!r?.querySelectorAll)continue;
     for(const el of r.querySelectorAll('[id]'))
       if(el.id===controls)regions.add(el);
   }
 }
 function allDeep(node,selector,out=new Set()){
   if(!node?.querySelectorAll)return out;
   for(const el of node.querySelectorAll('*')){
     if(el.matches(selector))out.add(el);
     if(el.shadowRoot)allDeep(el.shadowRoot,selector,out);
   }
   return out;
 }
 if(host) for(const el of allDeep(host,'[role="listbox"]'))regions.add(el);
 const items=new Set();
 for(const region of regions)
   for(const el of allDeep(region,'[role="option"],lightning-base-combobox-item,.slds-listbox__item'))items.add(el);
 // Salesforce may render a listbox directly under grouped host without role=listbox.
 if(items.size===0 && host){
   for(const el of allDeep(host,'[role="option"],lightning-base-combobox-item'))items.add(el);
 }
 const result=[];
 for(const el of items){
   if(!el.getClientRects().length)continue;
   const text=(el.innerText||el.textContent||'').trim();
   if(!text)continue;
   const titleEl=el.querySelector('.slds-listbox__option-text,.slds-truncate,[title]');
   const primary=(titleEl?.textContent||text.split('\n')[0]||'').trim();
   const normalized=s=>s.replace(/\s+/g,' ').trim().toLowerCase();
   if(normalized(text)==='new account'||normalized(text)==='new contact')continue;
   result.push({primary,text:text.slice(0,180), element:el});
 }
 return {regionCount:regions.size,items:result};
}"""
PILL_JS=r"""(input,expected) => {
 const equal=s=>(s||'').replace(/\s+/g,' ').trim().toLowerCase()===expected.trim().toLowerCase();
 let node=input;
 while(node && node.localName!=='lightning-grouped-combobox')
   node=node.parentElement||node.getRootNode()?.host||null;
 if(!node)return false;
 function deep(root,out=[]){
   if(!root?.querySelectorAll)return out;
   for(const el of root.querySelectorAll('*')){
     if(el.shadowRoot)deep(el.shadowRoot,out);
     if(el.matches('lightning-pill,.slds-pill,[data-selection]'))out.push(el);
   }
   return out;
 }
 return deep(node.shadowRoot||node).some(p=>equal(p.querySelector('.slds-pill__label')?.textContent||p.textContent));
}"""

def select(context,label,name):
    inp,status=find_input(context,label)
    if inp is None:return {"status":status}
    try:
        inp.fill(name,timeout=3500)
        snapshot=None
        for _ in range(6):
            time.sleep(0.4)
            snapshot=inp.evaluate_handle(SUGGESTION_JS)
            items=snapshot.get_property("items")
            count=items.evaluate("(x)=>x.length")
            if count: break
            snapshot.dispose()
        if not count:return {"status":"NO_SCOPED_SUGGESTIONS","count":0}
        matches=[]
        for i in range(count):
            item=items.evaluate_handle("(xs,i)=>xs[i]",i)
            primary=item.get_property("primary").json_value()
            text=item.get_property("text").json_value()
            if norm(primary)==norm(name):
                matches.append((item,text))
            else:item.dispose()
        if len(matches)!=1:
            return {"status":"NO_EXACT_UNIQUE_SUGGESTION","count":len(matches),
                    "scoped_candidates":[items.evaluate("(xs,i)=>xs[i].primary",i) for i in range(min(count,10))]}
        matches[0][0].get_property("element").as_element().click(timeout=3500)
        time.sleep(0.3)
        # A lookup is NOT verified just because a suggestion was clicked.
        # Salesforce selection usually creates a pill and clears editable search.
        try:
            verified=bool(inp.evaluate(PILL_JS,name))
        except PWError:
            verified=False
        return {"status":"SELECTED_PILL_VERIFIED" if verified else "CLICKED_NOT_VERIFIED",
                "option_text":matches[0][1]}
    except PWError as e:
        return {"status":"LOOKUP_UI_CHANGED","reason_type":type(e).__name__}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--url",required=True);p.add_argument("--draft",required=True)
    p.add_argument("--account-query",default="",help="Override catalog account label with actual Salesforce account name")
    p.add_argument("--output",default="")
    a=p.parse_args();check_url(a.url)
    values=prepare_lookup(json.loads(Path(a.draft).read_text(encoding="utf-8-sig")))
    if a.account_query:values["Account Name"]=a.account_query
    with sync_playwright() as pw:
        ctx=pw.chromium.launch_persistent_context(user_data_dir=str(PROFILE),headless=False,channel="chrome")
        try:
            page=ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto(a.url,wait_until="domcontentloaded")
            input("Complete MFA, open New Opportunity, press Enter ONCE: ")
            result={}
            for label in ("Account Name","Main Contact"):
                result[label]=select(ctx,label,values[label])
                if result[label]["status"]!="SELECTED_PILL_VERIFIED":break
            report={"lookup":result,"lookup_verified":all(result.get(x,{}).get("status")=="SELECTED_PILL_VERIFIED" for x in ("Account Name","Main Contact")),
                "save_clicked":False,"note":"No Salesforce Save. Inspect selected lookup pills and account/contact affiliation."}
            out=Path(a.output) if a.output else Path(a.draft).with_name("lookup_selection_report.json")
            out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
            print(json.dumps(report,ensure_ascii=False,indent=2));print("REPORT:",out)
            input("Inspect UI; press Enter to close: ")
        finally:ctx.close()
if __name__=="__main__":main()
