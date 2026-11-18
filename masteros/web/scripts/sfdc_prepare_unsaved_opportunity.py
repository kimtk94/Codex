"""User-initiated, explicit three-field draft fill in Salesforce New Opportunity.

Only an authenticated operator laptop may run this script via loopback API.
It creates one visible UNSAVED Opportunity modal in a separate Chrome tab and
fills Opportunity Name / Close Date / Progress Description, no Account/Contact
selection, Amount, or Stage. Never clicks Save. Salesforce record writes: ZERO.
"""
import json,sys,asyncio
from playwright.async_api import async_playwright
HOST="https://novogene.lightning.force.com"
LABEL_JS=r"""(label) => {
 const normal=s=>(s||"").replace(/\s+/g," ").replace(/^\s*\*\s*/,"").trim().toLowerCase();
 const roots=[],seen=new Set();
 function visit(r){if(!r||seen.has(r))return;seen.add(r);roots.push(r);
   for(const e of r.querySelectorAll("*"))if(e.shadowRoot)visit(e.shadowRoot)}
 visit(document);
 const candidates=[],included=new Set();
 function add(x){if(!x||included.has(x)||x.disabled||x.readOnly||
    !x.matches("input:not([type=hidden]),textarea"))return;
    included.add(x);candidates.push(x)}
 for(const root of roots)for(const l of root.querySelectorAll("label,.slds-form-element__label")){
  if(normal(l.textContent)!==normal(label))continue;
  const id=l.getAttribute("for");
  if(id&&root.getElementById){const x=root.getElementById(id);if(x)add(x)}
  let p=l;
  for(let i=0;i<7&&p;i++,p=p.parentElement){
   if(p.matches?.("lightning-input,lightning-textarea,lightning-input-field,.slds-form-element")){
     const sub=p.shadowRoot||p;
     for(const x of sub.querySelectorAll("input,textarea"))add(x);
     break;
   }
  }
 }
 for(const root of roots)for(const host of root.querySelectorAll(
   "lightning-input,lightning-textarea,lightning-input-field")){
   if(normal(host.getAttribute("label"))!==normal(label))continue;
   for(const x of (host.shadowRoot||host).querySelectorAll("input,textarea"))add(x)
 }
 const appropriate=candidates.filter(x=>label==="Progress Description"?
   x.tagName==="TEXTAREA":x.tagName==="INPUT");
 if(appropriate.length===1){
    appropriate[0].setAttribute("data-local-unsaved-field",label.replace(/\s/g,"_"));
 }
 return {matched:appropriate.length,marked:appropriate.length===1};
}"""
async def main():
 output={"status":"HOLD_UNSAVED_DRAFT_PREPARE","salesforce_write":False,
         "save_clicked":False,"crm_writes":0,"page_open":False,
         "fields":{},"missing_for_save":["Account","Main Contact","Amount",
          "Currency","Service Line","Stage","Forecast Category",
          "Native Product/Process/Pack","Duplicate Check"]}
 try:
  obj=json.loads(sys.stdin.read(9000))
  if not isinstance(obj,dict) or set(obj)!={"name","closeDate","description"}:
   raise ValueError("INVALID_FIELDS")
  name,dt,description=obj["name"],obj["closeDate"],obj["description"]
  if not isinstance(name,str) or not 5<=len(name)<=180 or "\n" in name:
   raise ValueError("INVALID_NAME")
  if not isinstance(dt,str) or len(dt)!=10 or dt[4]!="-":
   raise ValueError("INVALID_CLOSE_DATE")
  if not isinstance(description,str) or not 5<=len(description)<=3000:
   raise ValueError("INVALID_DESCRIPTION")
  async with async_playwright() as pw:
   br=await pw.chromium.connect_over_cdp("http://127.0.0.1:9222",timeout=16000)
   if not br.contexts:raise RuntimeError("CHROME_NOT_AUTHENTICATED")
   page=await br.contexts[0].new_page()
   try:
    await page.goto(HOST+"/lightning/o/Opportunity/list",
      wait_until="domcontentloaded",timeout=35000)
    new=page.get_by_role("button",name="New",exact=True)
    await new.wait_for(state="visible",timeout=25000)
    if await new.count()!=1:raise RuntimeError("NEW_OPPORTUNITY_NOT_UNIQUE")
    await new.click(timeout=15000)
    await page.get_by_text("Opportunity Name",exact=False).first.wait_for(timeout=30000)
    complete=True
    for label,value in (("Opportunity Name",name),("Close Date",dt),
                        ("Progress Description",description)):
      located=await page.evaluate(LABEL_JS,label)
      if not located["marked"]:
       output["fields"][label]="HOLD_FIELD_NOT_UNIQUE";complete=False;continue
      selector='[data-local-unsaved-field="'+label.replace(" ","_")+'"]'
      control=page.locator(selector)
      try:
       if await control.count()!=1:raise RuntimeError("MARKER_NOT_UNIQUE")
       await control.fill(value,timeout=7000)
       actual=await control.input_value()
       if actual!=value:raise RuntimeError("VALUE_READBACK_MISMATCH")
       output["fields"][label]="FILLED_UNSAVED"
      except Exception as e:
       complete=False;output["fields"][label]="HOLD_"+type(e).__name__
    output["page_open"]=True
    output["status"]="UNSAVED_OPPORTUNITY_FORM_READY" if complete else "HOLD_FORM_PARTIAL"
    # Intentionally DO NOT close the page. The user must inspect manually.
   except Exception:
    await page.close()
    raise
   finally:
    await br.close() # CDP disconnect, not a Salesforce Save.
 except Exception as e:
  output["status"]="HOLD_UNSAVED_"+type(e).__name__
 print(json.dumps(output,ensure_ascii=False))
if __name__=="__main__":
 asyncio.run(main())
