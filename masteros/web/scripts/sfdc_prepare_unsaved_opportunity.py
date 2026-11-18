"""User-initiated, explicit three-field draft fill in Salesforce New Opportunity.

Only an authenticated operator laptop may run this script via loopback API.
It creates one visible UNSAVED Opportunity modal in a separate Chrome tab and
fills Opportunity Name / Close Date / Progress Description, no Account/Contact
selection, Amount, or Stage. Never clicks Save. Salesforce record writes: ZERO.
"""
import json,sys,asyncio
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
    // Salesforce Lightning Locker forbids ShadowRoot.getElementById.
    // Deliberately rely only on label-host ancestry and host label match.
  }
  for(const root of roots)for(const host of root.querySelectorAll(tag)){
    if(normalize(host.getAttribute("label"))===normalize(label))inner(host);
  }
  const unique=[...controls].filter(el=>el.getClientRects().length>0);
  if(unique.length===1)
    unique[0].setAttribute("data-local-unsaved-field",label.replace(/\s/g,"_"));
  return {matched:unique.length,marked:unique.length===1,label_count:labels.length};
}"""

def reuse_decision(open_forms, desired):
  """Never overwrite an existing draft or create additional ambiguous modals."""
  if not isinstance(open_forms,list) or not isinstance(desired,dict):
   return "HOLD_INVALID_EXISTING_MODAL_SNAPSHOT"
  if len(open_forms)==0:
   return "OPEN_NEW"
  if len(open_forms)>1:
   return "HOLD_MULTIPLE_UNSAVED_OPPORTUNITY_MODALS"
  if not isinstance(open_forms[0],dict) or set(desired)!=set(open_forms[0]):
   return "HOLD_EXISTING_UNSAVED_FIELDS_NOT_VERIFIED"
  if all(open_forms[0][k]==v for k,v in desired.items()):
   return "REUSE_UNMODIFIED_EXISTING_FORM"
  return "HOLD_EXISTING_UNSAVED_FIELDS_DIFFER"


async def existing_opportunity_pages(context, desired):
  """Only inspect native authenticated current tabs; don't close or save any."""
  from urllib.parse import urlparse
  found=[]
  for page in context.pages:
   if page.is_closed() or urlparse(page.url).hostname!="novogene.lightning.force.com":
    continue
   try:
    dialog=page.get_by_role("dialog")
    if await dialog.count()!=1 or not await dialog.is_visible():
     continue
    caption=await dialog.inner_text(timeout=2500)
    if "New Opportunity" not in caption:
     continue
    # Avoid touching existing user input when multiple drafts are open.
    found.append(page)
   except Exception:
    continue
  if len(found)!=1:
   return found, reuse_decision([{} for _ in found],desired)
  values={}
  for label in ("Opportunity Name","Close Date","Progress Description"):
   meta=await found[0].evaluate(LABEL_JS,label)
   if not meta.get("marked"):
    return found,"HOLD_EXISTING_UNSAVED_FIELDS_NOT_VERIFIED"
   marker='[data-local-unsaved-field="'+label.replace(" ","_")+'"]'
   control=found[0].locator(marker)
   if await control.count()!=1:
    return found,"HOLD_EXISTING_UNSAVED_FIELDS_NOT_VERIFIED"
   values[label]=await control.input_value()
  return found,reuse_decision([values],desired)


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
  from playwright.async_api import async_playwright
  async with async_playwright() as pw:
   br=await pw.chromium.connect_over_cdp("http://127.0.0.1:9222",timeout=16000)
   if not br.contexts:raise RuntimeError("CHROME_NOT_AUTHENTICATED")
   output["stage"]="FIND_EXISTING_UNSAVED_DRAFT"
   desired={"Opportunity Name":name,"Close Date":dt,
      "Progress Description":description}
   existing,decision=await existing_opportunity_pages(br.contexts[0],desired)
   if decision=="REUSE_UNMODIFIED_EXISTING_FORM":
    output["status"]="UNSAVED_OPPORTUNITY_FORM_READY"
    output["stage"]="REUSED_EXISTING_EXACT_UNSAVED_DRAFT"
    output["page_open"]=True
    output["fields"]={field:"REUSED_UNSAVED" for field in desired}
    output["new_tabs_opened"]=0
    await br.close()
    print(json.dumps(output,ensure_ascii=False))
    return
   if decision!="OPEN_NEW":
    output["status"]="HOLD_FORM_PARTIAL"
    output["stage"]="EXISTING_UNSAVED_DRAFT_REQUIRES_REVIEW"
    output["reason"]=decision
    output["existing_modal_count"]=len(existing)
    output["page_open"]=len(existing)>0
    output["new_tabs_opened"]=0
    await br.close()
    print(json.dumps(output,ensure_ascii=False))
    return
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
    output["new_tabs_opened"]=1
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
