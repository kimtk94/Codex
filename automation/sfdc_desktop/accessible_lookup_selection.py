#!/usr/bin/env python3
"""Account/Contact lookup selection probe using unique accessible comboboxes.
Never saves. Distinguishes exact option click from established relationship.
"""
import argparse,json,re
from pathlib import Path
from playwright.sync_api import sync_playwright,Error as PWError
from runner import check_url
from lookup_preflight import prepare_lookup

def norm(s):return re.sub(r"\s+"," ",str(s or "")).strip().casefold()
def run(page,label,expected):
 frames=[]
 for frame in page.frames:
  try:
   x=frame.get_by_role("combobox",name=label,exact=True)
   if x.count()==1 and x.is_visible() and x.is_enabled():frames.append((frame,x))
  except PWError:pass
 if len(frames)!=1:return {"status":"COMBOBOX_NOT_UNIQUE","count":len(frames)}
 frame,field=frames[0]
 before=field.input_value()
 field.fill(expected)
 try:field.press("ArrowDown")
 except PWError:pass
 page.wait_for_timeout(850)
 # Scope to the owning frame and only currently visible options. Never click
 # other buttons, including New Contact or New Account.
 options=[]
 for opt in frame.get_by_role("option").all():
  try:
   if not opt.is_visible():continue
   label_text=opt.inner_text(timeout=900)
   if norm(label_text.splitlines()[0])==norm(expected):
    options.append(opt)
  except PWError:pass
 if len(options)!=1:
  return {"status":"NO_UNIQUE_EXACT_OPTION","matching_options":len(options),
          "before_value":before,"current_value":field.input_value()}
 options[0].click(timeout=2500)
 page.wait_for_timeout(400)
 # A click does not establish the relationship. Read back control state.
 status={"status":"OPTION_CLICKED_RELATION_UNVERIFIED","matching_options":1,
         "before_value":before}
 try:
  status["combobox_value_after"]=field.input_value(timeout=800)
 except PWError:status["combobox_value_after"]=None
 try:
  host=field.evaluate("""el=>{
   let x=el;
   for(let i=0;i<12&&x;i++){
    if(x.localName==='lightning-grouped-combobox')return x;
    x=x.parentElement||x.getRootNode()?.host||null;
   }
   return null;
  }""")
  status["grouped_combobox_host_found"]=bool(host)
 except PWError:status["grouped_combobox_host_found"]=False
 return status

def main():
 p=argparse.ArgumentParser()
 p.add_argument("--draft",required=True)
 p.add_argument("--cdp-url",default="http://127.0.0.1:9222")
 p.add_argument("--output",default="")
 a=p.parse_args()
 draft=json.loads(Path(a.draft).read_text(encoding="utf-8-sig"))
 values=prepare_lookup(draft)
 with sync_playwright() as pw:
  browser=pw.chromium.connect_over_cdp(a.cdp_url)
  pages=[]
  for ctx in browser.contexts:
   for pg in ctx.pages:
    try:
     check_url(pg.url)
     if "new opportunity" in pg.title().lower():pages.append(pg)
    except (PWError,ValueError):pass
  if len(pages)!=1:raise RuntimeError("Exactly one New Opportunity tab required")
  input("Inspect ONE New Opportunity form and press Enter to attempt exact lookup selections: ")
  result={"version":"accessible-lookup-selection-v1","fields":{},"save_clicked":False}
  for label in ("Account Name","Main Contact"):
   try:result["fields"][label]=run(pages[0],label,values[label])
   except PWError as exc:result["fields"][label]={"status":"PLAYWRIGHT_ERROR","exception":type(exc).__name__}
   print(label,result["fields"][label]["status"])
  result["lookup_verified"]=False
  dest=Path(a.output) if a.output else Path(a.draft).with_name("accessible_lookup_selection.json")
  dest.parent.mkdir(parents=True,exist_ok=True)
  dest.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
  print("REPORT:",dest)
  print("No Save; exact option click is NOT relationship verification.")
if __name__=="__main__":main()
