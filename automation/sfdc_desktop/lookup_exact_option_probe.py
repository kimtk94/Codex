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

SELECTED_JS = r"""({label, expected}) => {
 const norm=s=>(s||'').replace(/\s+/g,' ').trim().toLowerCase();
 const seen=new Set(), labels=[];
 function walk(root) {
   if(!root||seen.has(root))return;
   seen.add(root);
   for(const el of root.querySelectorAll('*')) {
     if(el.shadowRoot)walk(el.shadowRoot);
     if(el.matches('label') && norm(el.textContent).replace(/^\*\s*/,'')===norm(label))
       labels.push(el);
   }
 }
 walk(document);
 if(labels.length!==1)return false;
 let n=labels[0];
 for(let depth=0;n&&depth<6;depth++) {
   const pills=new Set();
   function scan(root) {
     if(!root?.querySelectorAll)return;
     for(const e of root.querySelectorAll('*')) {
       if(e.shadowRoot)scan(e.shadowRoot);
       if(e.matches('lightning-pill,.slds-pill,[class*="pill"]'))pills.add(e);
     }
   }
   scan(n.shadowRoot||n);
   // Lightning pills may have a remove button in their own shadow root.
   const selected=[...pills].filter(p=>{
     const text=norm(p.getAttribute('label')||p.getAttribute('title')||
                    p.querySelector('.slds-pill__label')?.textContent||p.textContent);
     return text===norm(expected) || text.startsWith(norm(expected)+' ');
   });
   if(selected.length===1)return true;
   n=n.parentElement||n.getRootNode()?.host||null;
 }
 return false;
}"""

def verify_selected(context,label,name):
    for page in context.pages:
        if page.is_closed():continue
        for frame in page.frames:
            try:
                if frame.evaluate(SELECTED_JS,{"label":label,"expected":name}):return True
            except PWError:continue
    return False

def select(context,label,name):
    inp,status=find_input(context,label)
    if inp is None:
        if verify_selected(context,label,name):return {"status":"SELECTED_PILL_VERIFIED","source":"already_selected"}
        return {"status":status}
    try:
        if verify_selected(context,label,name):return {"status":"SELECTED_PILL_VERIFIED","source":"already_selected"}
        inp.click(timeout=2500)
        inp.fill(name,timeout=3500)
        # Salesforce lookup uses a search affordance; fill alone may NOT open the dropdown.
        inp.press("ArrowDown",timeout=2000)
        time.sleep(0.3)
        # Search icon is often adjacent to the input. Scoped click only; never click other forms.
        trigger=inp.evaluate_handle("""el => {
          let n=el;
          while(n && n.localName!=='lightning-grouped-combobox')
            n=n.parentElement||n.getRootNode()?.host||null;
          if(!n)return null;
          const r=n.shadowRoot||n;
          return [...r.querySelectorAll('button,[role="button"]')].find(x=>
            /search/i.test((x.getAttribute('title')||'')+' '+(x.getAttribute('aria-label')||'')+
              ' '+(x.className?.baseVal||x.className||'')))||null;
        }""").as_element()
        if trigger and trigger.is_visible():trigger.click(timeout=2500)
        else:inp.press("ArrowDown",timeout=2000)
        time.sleep(1.0)
        # Salesforce may portal the list outside the lookup host, into a sibling shadow root.
        # Match text AND Lookup row design; do not mistake the Service Line dual-list options.
        found=[]
        for page in context.pages:
            if page.is_closed():continue
            for frame in page.frames:
                try:
                    handles=frame.evaluate_handle("""expected => {
                      const norm=s=>(s||'').replace(/\\s+/g,' ').trim().toLowerCase();
                      const seen=new Set(),out=[];
                      function walk(root){
                        if(!root||seen.has(root))return;
                        seen.add(root);
                        for(const el of root.querySelectorAll('*')){
                          if(el.shadowRoot)walk(el.shadowRoot);
                          if(!el.matches('li,[role="option"],lightning-base-combobox-item,.slds-listbox__option'))continue;
                          if(!el.getClientRects().length)continue;
                          const txt=(el.innerText||el.textContent||'').trim();
                          const first=(txt.split('\\n')[0]||'').trim();
                          if(norm(first)!==norm(expected))continue;
                          if(!el.closest('.slds-listbox_lookup,.slds-listbox,[role="listbox"]') &&
                             !el.matches('lightning-base-combobox-item'))continue;
                          out.push(el);
                        }
                      }
                      walk(document);
                      return out.filter(el=>!out.some(other=>other!==el&&el.contains(other)));
                    }""",name)
                    n=handles.evaluate("(xs)=>xs.length")
                    for i in range(min(n,10)):
                        candidate=handles.evaluate_handle("(xs,i)=>xs[i]",i).as_element()
                        if candidate and candidate.is_visible():found.append(candidate)
                except PWError:continue
        if len(found)!=1:return {"status":"NO_EXACT_UNIQUE_SUGGESTION","count":len(found),
                                  "note":"Lookup search icon triggered; inspect actual dropdown."}
        found[0].click(timeout=3500)
        time.sleep(0.4)
        verified=verify_selected(context,label,name)
        return {"status":"SELECTED_PILL_VERIFIED" if verified else "CLICKED_NOT_VERIFIED"}
    except PWError:
        return {"status":"LOOKUP_UI_CHANGED"}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--url",required=True);p.add_argument("--draft",required=True)
    p.add_argument("--account-query",default="",help="Override catalog account label with actual Salesforce account name")
    p.add_argument("--output",default="")
    p.add_argument("--cdp-url",default="",help="Attach to already authenticated Chrome debugging port instead of launching Chrome")
    a=p.parse_args();check_url(a.url)
    values=prepare_lookup(json.loads(Path(a.draft).read_text(encoding="utf-8-sig")))
    if a.account_query:values["Account Name"]=a.account_query
    with sync_playwright() as pw:
        attached=bool(a.cdp_url)
        browser=None
        if attached:
            browser=pw.chromium.connect_over_cdp(a.cdp_url)
            if not browser.contexts:raise RuntimeError("No active Chrome context attached")
            ctx=browser.contexts[0]
        else:
            ctx=pw.chromium.launch_persistent_context(user_data_dir=str(PROFILE),headless=False,channel="chrome")
        try:
            page=ctx.pages[0] if ctx.pages else ctx.new_page()
            if not attached:page.goto(a.url,wait_until="domcontentloaded")
            input("Use THIS authenticated Chrome, open New Opportunity, press Enter ONCE: ")
            result={}
            for label in ("Account Name","Main Contact"):
                result[label]=select(ctx,label,values[label])
                if result[label]["status"]!="SELECTED_PILL_VERIFIED":break
            report={"lookup":result,"lookup_verified":all(result.get(x,{}).get("status")=="SELECTED_PILL_VERIFIED" for x in ("Account Name","Main Contact")),
                "save_clicked":False,"note":"No Salesforce Save. Inspect selected lookup pills and account/contact affiliation."}
            out=Path(a.output) if a.output else Path(a.draft).with_name("lookup_selection_report.json")
            out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
            print(json.dumps(report,ensure_ascii=False,indent=2));print("REPORT:",out)
            input("Inspect UI; press Enter to finish: ")
        finally:
            if not attached:ctx.close()
            # When attached over CDP, leave Chrome and its authenticated session running.

if __name__=="__main__":main()
