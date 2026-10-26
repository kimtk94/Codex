#!/usr/bin/env python3
"""One-pass UNSAVED Salesforce New Opportunity template fill.
Copies observed historical source values only, never invents missing fields.
A historical source is not a valid new sale until reviewed; Save is forbidden.
"""
import argparse,json,re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo
from pathlib import Path
from playwright.sync_api import sync_playwright,Error as PWError
from runner import check_url
from lookup_preflight import prepare_lookup
from accessible_lookup_selection import run as select_lookup
from bulk_required_fill import do_fill,do_pick
from lookup_batch_audit import window_inventory,focus_and_maximize

LABELS=("Opportunity Name","Account Name","Main Contact","Amount",
 "Close Date","Service Line","Stage","Forecast Category","Progress Description","Status")
def read(path):return json.loads(Path(path).read_text(encoding="utf-8-sig"))
def normalized(s):return re.sub(r"\s+"," ",str(s or "")).strip()
def amount_numeric(value):
 raw=str(value or "").strip()
 # Accept Salesforce-rendered KRW amounts, but never send currency text
 # into an HTML numeric input.
 raw=re.sub(r"^(?:KRW|₩)\s*", "", raw, flags=re.I).replace(",", "").strip()
 if not re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)",raw):
  raise ValueError("Invalid Amount; explicit numeric amount required")
 try: number=Decimal(raw)
 except InvalidOperation as exc:raise ValueError("Invalid Amount") from exc
 if not number.is_finite() or number < 0:raise ValueError("Invalid Amount")
 return format(number,"f")

def progress_for_today(value, stage):
 text=str(value or "").strip()
 today=datetime.now(ZoneInfo("Asia/Seoul")).strftime("%m%d")
 # Accept either multiline or the existing single-line description convention.
 m=re.match(r"^\d{4}\s+",text)
 if not m:return text
 body=text[m.end():].strip()
 known_stage=(stage or "").strip()
 if known_stage and body.casefold().startswith(known_stage.casefold()):
  detail=body[len(known_stage):].strip()
  return today+" "+known_stage+("\n"+detail if detail else "")
 # Historical cases often say "Quote Issued" even when Stage was changed.
 for original in ("Quote Issued","Quotation Issued","Closed Won"):
  if body.casefold().startswith(original.casefold()):
   detail=body[len(original):].strip()
   return today+" "+original+("\n"+detail if detail else "")
 # Unknown text pattern must not be transformed or invented.
 return text

def first(*values):
 for v in values:
  if normalized(v):return normalized(v)
 return ""
def historical_data(draft):
 web=draft.get("existing_opportunity_reference") or {}
 catalog=draft.get("existing_catalog_reference") or {}
 return {
  "Opportunity Name":first(web.get("Opportunity Name"),catalog.get("opportunity_name")),
  "Account Name":first(draft.get("Account Name"),web.get("Account Name")),
  "Main Contact":first(draft.get("Main Contact"),web.get("Main Contact")),
  "Amount":first(web.get("Amount"),catalog.get("amount")),
  "Close Date":first(web.get("Close Date"),catalog.get("close_date")),
  "Service Line":first(web.get("Service Line"),catalog.get("service_line")),
  "Stage":first(web.get("Stage"),catalog.get("historical_stage")),
  "Forecast Category":first(web.get("Forecast Category"),catalog.get("forecast_category")),
  "Progress Description":str(web.get("Progress Description") or catalog.get("progress_description") or "").strip(),
  "Status":first(web.get("Status"),catalog.get("status"))
 }
def find_page(ctx):
 hits=[]
 for pg in ctx.pages:
  try:
   check_url(pg.url)
   if not pg.is_closed() and "new opportunity" in pg.title().lower():hits.append(pg)
  except (ValueError,PWError):pass
 if len(hits)!=1:raise RuntimeError("Exactly one New Opportunity tab required")
 return hits[0]
def service_line(page,value):
 if not value:return {"status":"NO_SOURCE_VALUE"}
 # Never click buttons by ordinal index. Find exact source option in one dual listbox.
 hosts=[]
 for frame in page.frames:
  try:
   loc=frame.locator("lightning-dual-listbox")
   for i in range(loc.count()):
    x=loc.nth(i)
    if x.is_visible():hosts.append(x)
  except PWError:pass
 if len(hosts)!=1:return {"status":"DUAL_LISTBOX_NOT_UNIQUE","count":len(hosts)}
 host=hosts[0]
 try:
  # Native select-backed dual-listbox, if exposed by this Salesforce variant.
  selects=host.locator("select")
  available=[]
  for i in range(selects.count()):
   options=selects.nth(i).locator("option")
   for j in range(options.count()):
    o=options.nth(j)
    if normalized(o.inner_text())==normalized(value):
     available.append((selects.nth(i),o.get_attribute("value")))
  if len(available)!=1:return {"status":"SERVICE_OPTION_NOT_UNIQUE","count":len(available)}
  select,optvalue=available[0]
  select.select_option(value=optvalue)
  # Selection in Available is not transfer to Chosen.
  add=host.get_by_role("button",name=re.compile(r"move.*selected.*chosen|move.*to.*chosen|add",re.I))
  if add.count()!=1:return {"status":"AVAILABLE_SELECTED_TRANSFER_NOT_VERIFIED"}
  add.click(timeout=2500)
  return {"status":"TRANSFER_CLICKED_NOT_VERIFIED"}
 except PWError:return {"status":"SERVICE_CONTROL_UNSUPPORTED"}
def main():
 p=argparse.ArgumentParser()
 p.add_argument("--draft",required=True)
 p.add_argument("--values",default="",help="Optional JSON of explicitly approved current opportunity values")
 p.add_argument("--cdp-url",default="http://127.0.0.1:9222")
 p.add_argument("--output",default="")
 a=p.parse_args()
 draft=read(a.draft)
 prepare_lookup(draft)
 if draft.get("source_opportunity_id")!="Opp-2026-10-23-291068":
  p.error("Only verified historical source Opp-2026-10-23-291068 supported")
 values=historical_data(draft)
 overrides=read(a.values) if a.values else {}
 for k,v in overrides.items():
  if k in LABELS:values[k]=str(v).strip() if k=="Progress Description" else normalized(v)
 if values["Amount"]:values["Amount"]=amount_numeric(values["Amount"])
 if values["Progress Description"]:
  values["Progress Description"]=progress_for_today(values["Progress Description"],values.get("Stage",""))
 missing=[x for x in LABELS if x!="Forecast Category" and not values.get(x)]
 print("SOURCE:",draft["source_opportunity_id"],"MODE: historical template, NOT an approved new sale")
 print("VALUES:",json.dumps(values,ensure_ascii=False))
 print("MISSING:",", ".join(missing) or "(none)")
 with sync_playwright() as pw:
  browser=pw.chromium.connect_over_cdp(a.cdp_url)
  if not browser.contexts:raise RuntimeError("No CDP Chrome context")
  ctx=browser.contexts[0]
  input("Open ONE unsaved New Opportunity. Enter to populate all available values, WITHOUT Save: ")
  page=find_page(ctx)
  focus_and_maximize(page)
  result={"version":"one-pass-historical-v1","source_id":draft["source_opportunity_id"],
          "mode":"historical_reference_only","save_clicked":False,
          "fields":{},"missing":missing}
  for label in ("Account Name","Main Contact"):
   result["fields"][label]=select_lookup(page,label,values[label]) if values[label] else {"status":"NO_SOURCE_VALUE"}
   print(label,result["fields"][label]["status"])
  for label in ("Opportunity Name","Amount","Close Date","Progress Description"):
   result["fields"][label]=do_fill(ctx,label,values[label])
   print(label,result["fields"][label]["status"])
  for label in ("Stage","Status"):
   result["fields"][label]=do_pick(ctx,label,values[label])
   print(label,result["fields"][label]["status"])
  result["fields"]["Forecast Category"]={"status":"AUTO_FROM_STAGE_NOT_TOUCHED"}
  result["fields"]["Service Line"]=service_line(page,values["Service Line"])
  print("Service Line",result["fields"]["Service Line"]["status"])
  result["fields"]["Opportunity Currency"]={"status":"KEEP_EXISTING_DEFAULT_NOT_TOUCHED"}
  result["all_required_verified"]=False
  out=Path(a.output) if a.output else Path(a.draft).with_name("one_pass_form_report.json")
  out.parent.mkdir(parents=True,exist_ok=True)
  out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
  print("REPORT:",out)
  print("DO NOT SAVE: copied values describe an earlier Opportunity; selections may be unverified.")
if __name__=="__main__":main()
