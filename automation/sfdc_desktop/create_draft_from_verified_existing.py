#!/usr/bin/env python3
"""Create a safe, unsaved new Opportunity draft from a verified existing record."""
import argparse,json
from pathlib import Path

VERIFIED={"VERIFIED_BY_USER_SYSTEM_INFORMATION","VERIFIED_BUSINESS_ID_MATCH"}
FIELDS=("Opportunity Name","Account Name","Main Contact","Amount",
        "Opportunity Currency","Close Date","Service Line","Stage",
        "Forecast Category","Progress Description","Status")
def main():
 p=argparse.ArgumentParser()
 p.add_argument("--bridge",required=True)
 p.add_argument("--matches",required=True)
 p.add_argument("--snapshot",required=True)
 p.add_argument("--output",default="")
 a=p.parse_args()
 bridge=json.loads(Path(a.bridge).read_text(encoding="utf-8-sig"))
 matches=json.loads(Path(a.matches).read_text(encoding="utf-8-sig")).get("matches",[])
 snap=json.loads(Path(a.snapshot).read_text(encoding="utf-8-sig"))
 if bridge.get("status") not in VERIFIED:p.error("Business ID verification not complete")
 ids=bridge.get("matched_catalog_business_ids",[])
 selected=[m for m in matches if m.get("opportunity_id") in ids]
 if len(ids)!=1 or len(selected)!=1:p.error("Exactly one verified Catalog row required")
 if bridge.get("web_record_id")!=snap.get("record_id_from_url"):
  p.error("Bridge and snapshot Salesforce record IDs differ")
 if bridge.get("save_allowed") is not False or snap.get("saved_or_modified") is not False:
  p.error("Read-only safety evidence missing")
 actual={}
 for frame in snap.get("frames",[]):
  for f in frame.get("fields",[]):
   k=str(f.get("label") or "").strip()
   v=str(f.get("value") or "").strip()
   if k in FIELDS and v: actual.setdefault(k,set()).add(v)
 reference={k:next(iter(v)) for k,v in actual.items() if len(v)==1}
 row=selected[0]
 # Historical information is reference data, never automatically assigned to
 # the new Opportunity's financial, status, or transaction-specific fields.
 draft={k:"" for k in FIELDS if k!="Opportunity Currency"}
 draft.update({
  "Account Name":str(row.get("account") or ""),
  "Main Contact":str(row.get("contact") or ""),
  "source_opportunity_id":row["opportunity_id"],
  "source_salesforce_record_id":snap.get("record_id_from_url"),
  "existing_opportunity_reference":reference,
  "existing_catalog_reference":row,
  "lookup_verified":False,
  "review_required":True,
  "save_allowed":False,
  "salesforce_save_performed":False
 })
 output=Path(a.output) if a.output else Path(a.bridge).with_name("verified_existing_to_new_draft.json")
 output.parent.mkdir(parents=True,exist_ok=True)
 output.write_text(json.dumps(draft,ensure_ascii=False,indent=2),encoding="utf-8")
 print("VERIFIED SOURCE BUSINESS ID:",row["opportunity_id"])
 print("SOURCE WEB FIELDS:",len(reference))
 print("NEW DRAFT FILLED: Account Name, Main Contact (not yet lookup-verified)")
 print("OTHER NEW OPPORTUNITY FIELDS: BLANK")
 print("REPORT:",output)
 print("No Salesforce changes; Save forbidden.")
if __name__=="__main__":main()
