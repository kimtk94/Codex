#!/usr/bin/env python3
"""Compare SFDC business Opportunity ID displayed in a live record with Catalog.
No guessed mapping and no Salesforce writes.
"""
import argparse,json,re
from pathlib import Path

def main():
 p=argparse.ArgumentParser()
 p.add_argument("--snapshot",required=True)
 p.add_argument("--matches",required=True)
 p.add_argument("--output",default="")
 p.add_argument("--observed-business-id",default="",help="Opportunity ID visibly confirmed in System Information; requires manual review")
 a=p.parse_args()
 snap=json.loads(Path(a.snapshot).read_text(encoding="utf-8-sig"))
 matches=json.loads(Path(a.matches).read_text(encoding="utf-8-sig")).get("matches",[])
 evidence=[]
 for frame in snap.get("frames",[]):
  for item in frame.get("fields",[]):
   label=str(item.get("label") or "")
   value=str(item.get("value") or "")
   for found in re.findall(r"Opp-\d{4}-\d{2}-\d{2}-\d+",value):
    evidence.append({"label":label,"business_id":found,"source":"visible_field_value"})
 for frame in snap.get("frames",[]):
  for candidate in frame.get("business_id_candidates",[]):
   found=str(candidate.get("id") or "").strip()
   if re.fullmatch(r"Opp-\\d{4}-\\d{2}-\\d{2}-\\d+",found):
    evidence.append({"label":"Opportunity ID nearby",
                     "business_id":found,"source":"labeled_rendered_context_candidate"})
 if a.observed_business_id:
  if not re.fullmatch(r"Opp-\d{4}-\d{2}-\d{2}-\d+",a.observed_business_id):
   p.error("Invalid observed business ID format")
  evidence.append({"label":"System Information > Opportunity ID",
                   "business_id":a.observed_business_id,
                   "source":"user_confirmed_visible_system_information"})
 unique=sorted(set(item["business_id"] for item in evidence))
 direct=[m for m in matches if str(m.get("opportunity_id")) in unique]
 status=("VERIFIED_BY_USER_SYSTEM_INFORMATION" if len(unique)==1 and len(direct)==1 and any(x["source"]=="user_confirmed_visible_system_information" for x in evidence) else
         "VERIFIED_BUSINESS_ID_MATCH" if len(unique)==1 and len(direct)==1 and any(x["source"]=="visible_field_value" for x in evidence) else
         "CANDIDATE_MATCH_NEEDS_REVIEW" if len(unique)==1 and len(direct)==1 else
         "CONFLICTING_BUSINESS_IDS" if len(unique)>1 else "BUSINESS_ID_NOT_FOUND_OR_NOT_UNIQUE")
 result={"version":"business-id-bridge-v1","web_record_id":snap.get("record_id_from_url"),
         "business_id_evidence":evidence,"status":status,
         "matched_catalog_business_ids":[m.get("opportunity_id") for m in direct],
         "save_allowed":False}
 out=Path(a.output) if a.output else Path(a.snapshot).with_name("business_id_bridge.json")
 out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
 print("BUSINESS ID EVIDENCE:",json.dumps(evidence,ensure_ascii=False))
 print("MAPPING STATUS:",status)
 print("REPORT:",out)
if __name__=="__main__":main()
