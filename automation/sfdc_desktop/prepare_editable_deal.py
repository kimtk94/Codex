#!/usr/bin/env python3
"""Prepare per-deal editable Salesforce JSON without overwriting user edits.
Never modifies Salesforce or copies historical money/date as approved current values.
"""
import argparse,json,sys
from pathlib import Path
from datetime import datetime
from datetime import timezone, timedelta

sys.path.insert(0,str(Path(__file__).resolve().parent))
from one_pass_existing_template_fill import historical_data, amount_numeric

def main():
 p=argparse.ArgumentParser()
 p.add_argument("--draft",required=True)
 p.add_argument("--output",required=True)
 p.add_argument("--fill-blanks",action="store_true",help="Prefill only blank fields in an existing deal file")
 a=p.parse_args()
 draft=json.loads(Path(a.draft).read_text(encoding="utf-8-sig"))
 if draft.get("save_allowed") is not False:p.error("Expected read-only existing-source draft")
 output=Path(a.output)
 if output.exists() and not a.fill_blanks:
  print("PRESERVED_EXISTING_EDITABLE_FILE:",output)
  return
 ref=historical_data(draft)
 today=datetime.now(timezone(timedelta(hours=9))).strftime("%m%d")
 payload={
  "_instructions":"Edit only the current deal values. Historical values below are reference, not automatically approved. Never Save.",
  "_source_opportunity_id":draft.get("source_opportunity_id",""),
  "_historical_reference":ref,
  "Opportunity Name":ref.get("Opportunity Name",""),
  "Account Name":ref.get("Account Name",""),
  "Main Contact":ref.get("Main Contact",""),
  "Amount":amount_numeric(ref["Amount"]) if ref.get("Amount") else "",
  "Close Date":ref.get("Close Date",""),
  "Service Line":ref.get("Service Line",""),
  "Stage":ref.get("Stage",""),
  "Progress Description":today+" Quote Issued\nmRNA-Seq 5 samples * 180,000KRW",
  "Status":"Smoothly"
 }
 if output.exists():
  existing=json.loads(output.read_text(encoding="utf-8-sig"))
  filled=[]
  for key in ("Opportunity Name","Amount","Close Date","Service Line","Stage"):
   if not str(existing.get(key,"")).strip() and payload[key]:
    existing[key]=payload[key]
    filled.append(key)
  payload=existing
  print("FILLED_BLANK_FIELDS:",", ".join(filled) or "(none)")
 output.parent.mkdir(parents=True,exist_ok=True)
 output.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
 print("EDIT_CURRENT_DEAL_JSON:",output)
 print("Historical defaults prefilled; review Amount/Close Date before use. Existing nonblank edits preserved.")
if __name__=="__main__":main()
