#!/usr/bin/env python3
"""Find an existing Opportunity in a local Catalog export by Salesforce record ID.

Strict ID match only (15/18-char compatibility). Does not change drafts or Salesforce.
"""
import argparse,csv,json
from pathlib import Path

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--snapshot",required=True)
    p.add_argument("--catalog-csv",required=True)
    p.add_argument("--output",default="")
    a=p.parse_args()
    snap=json.loads(Path(a.snapshot).read_text(encoding="utf-8-sig"))
    record_id=str(snap.get("record_id_from_url") or "").strip()
    if not record_id or snap.get("record_id_evidence")!="lightning_opportunity_route":
        p.error("No authoritative existing Opportunity ID in snapshot")
    with open(a.catalog_csv,encoding="utf-8-sig",newline="") as f:
        rows=list(csv.DictReader(f))
    hits=[row for row in rows if str(row.get("Opportunity ID") or "").strip()[:15]==record_id[:15]]
    if len(hits)!=1:
        print("MATCH_COUNT:",len(hits))
        print("No unique matching Catalog row. Do not auto-link or copy values.")
        return
    result={"version":"catalog-existing-id-match-v1","record_id":record_id,
            "catalog_row":hits[0],"identity_match":"VERIFIED_ID_MATCH_15_PREFIX",
            "save_allowed":False}
    dest=Path(a.output) if a.output else Path(a.snapshot).with_name("catalog_existing_id_match.json")
    dest.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print("MATCH_COUNT: 1")
    print("OPPORTUNITY:",hits[0].get("Opportunity Name"))
    print("REPORT:",dest)
    print("READ ONLY; no draft edits and no Salesforce Save.")
if __name__=="__main__":main()
