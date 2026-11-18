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
  const normalize=s=>(s||"").replace(/\s+/g," ").replace(/^\s*\*\s*/,"").trim().toLowerCase();
  const tag=label==="Progress Description"?"lightning-textarea":"lightning-input";
  const roots=[],seen=new Set();
  function visit(r){
    if(!r||seen.has(r))return;seen.add(r);roots.push(r);
    for(const el of r.querySelectorAll("*"))if(el.shadowRoot)visit(el.shadowRoot);
  }
  visit(document);
  const controls=new Set(),labels=[];
  function inner(host){
    const visited=new Set();
    function run(root){
      if(!root||visited.has(root))return;visited.add(root);
      for(const el of root.querySelectorAll("input,textarea")){
        if(el.disabled||el.readOnly||el.type==="hidden")continue;
        if(label==="Progress Description"?el.tagName==="TEXTAREA":el.tagName==="INPUT")
          controls.add(el);
      }
      for(const el of root.querySelectorAll("*"))if(el.shadowRoot)run(el.shadowRoot);
    }
    run(host.shadowRoot||host);
  }
  for(const root of roots)for(const lab of root.querySelectorAll("label,legend,.slds-form-element__label")){
    if(normalize(lab.textContent)!==normalize(label))continue;
    labels.push(lab);
    let r=lab.getRootNode();
    for(let i=0;i<12&&r&&r.host;i++){
      if(r.host.tagName?.toLowerCase()===tag){inner(r.host);break}
      r=r.host.getRootNode();
    }
    const id=lab.getAttribute("for");
    const linked=id?root.getElementById?.(id):null;
    if(linked){
      if(label==="Progress Description"?linked.tagName==="TEXTAREA":linked.tagName==="INPUT")
        controls.add(linked);
    }
  }
  for(const root of roots)for(const host of root.querySelectorAll(tag)){
    if(normalize(host.getAttribute("label"))===normalize(label))inner(host);
  }
  const unique=[...controls].filter(el=>el.getClientRects().length>0);
  if(unique.length===1)
    unique[0].setAttribute("data-local-unsaved-field",label.replace(/\s/g,"_"));
  return {matched:unique.length,marked:unique.length===1,label_count:labels.length};
}"""

async def main():
 output={"status":"HOLD_UNSAVED_DRAFT_PREPARE","salesforce_write":False,
         "save_clicked":False,"crm_writes":0,"page_open":False,
         "fields":{},"missing_for_save":["Account","Main Contact","Amount",
          "Currency","Service Line","Stage","Forecast Category",
          "Native Product/Process/Pack","Duplicate Check"]}
 try:
  output["stage"]="READ_STDIN"
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
  output["stage"]="CDP_CONNECT"
  async with async_playwright() as pw:
   br=await pw.chromium.connect_over_cdp("http://127.0.0.1:9222",timeout=16000)
   if not br.contexts:raise RuntimeError("CHROME_NOT_AUTHENTICATED")
   output["stage"]="NEW_TAB"
   page=await br.contexts[0].new_page()
   try:
    output["stage"]="OPPORTUNITY_LIST_NAVIGATION"
    await page.goto(HOST+"/lightning/o/Opportunity/list",
      wait_until="domcontentloaded",timeout=35000)
    output["stage"]="FIND_NEW_OPPO_BUTTON"
    new=page.get_by_role("button",name="New",exact=True)
    await new.wait_for(state="visible",timeout=25000)
    if await new.count()!=1:raise RuntimeError("NEW_OPPORTUNITY_NOT_UNIQUE")
    output["stage"]="OPEN_NEW_OPPORTUNITY_MODAL"
    await new.click(timeout=15000)
    output["stage"]="WAIT_NEW_OPPORTUNITY_MODAL"
    await page.get_by_role("dialog").wait_for(state="visible",timeout=30000)
    await page.wait_for_timeout(1600)
    complete=True
    for label,value in (("Opportunity Name",name),("Close Date",dt),
                        ("Progress Description",description)):
      output["stage"]="FIND_FIELD_"+label.replace(" ","_")
      try:
       located=await page.evaluate(LABEL_JS,label)
      except Exception:
       output["fields"][label]="HOLD_FIELD_DOM_TRANSIENT";complete=False;continue
      if not located["marked"]:
       output["fields"][label]="HOLD_FIELD_NOT_UNIQUE_"+str(located["matched"])
       complete=False;continue
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
    output["stage"]="DRAFT_FILLED_NOT_SAVED"
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
