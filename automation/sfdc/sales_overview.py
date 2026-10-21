#!/usr/bin/env python3
"""SFDC snapshot sales dashboard. No unverified cross-entity joins."""
import collections
import datetime as dt
import json
from followup_stage1 import auth, OUTPUT_ID, call
from opportunity_quote_mirror import range_data, replace_tab

TAB="SFDC Sales Overview"
def val(row,index):
    return row[index] if index is not None and index < len(row) else ""
def find(header,key):
    try: return header.index(key)
    except ValueError: return None
def main():
    session=auth()
    opp=range_data(session,OUTPUT_ID,"Opportunity",2000)
    quote=range_data(session,OUTPUT_ID,"Quotation",2000)
    if not opp or not quote: raise RuntimeError("Opportunity or Quotation mirror missing")
    oh=opp[0]; qh=quote[0]
    for c in ["Stage","Opportunity Name","Amount"]:
        if c not in oh: raise RuntimeError("Opportunity missing "+c)
    if "Stage" not in qh: raise RuntimeError("Quotation missing Stage")
    stage=collections.Counter(str(val(r,find(oh,"Stage"))).strip() or "BLANK" for r in opp[1:])
    qstage=collections.Counter(str(val(r,find(qh,"Stage"))).strip() or "BLANK" for r in quote[1:])
    audit=range_data(session,OUTPUT_ID,"SFDC CSS Match Audit",20)
    matched=next((int(r[1]) for r in audit[1:] if len(r)>1 and r[0]=="MATCHED"),0) if audit else 0
    link_audit=range_data(session,OUTPUT_ID,"SFDC Quote Link Audit",30)
    link_metrics={r[0]:r[1] for r in link_audit[1:] if len(r)>1} if link_audit else {}
    now=dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat()
    rows=[["section","metric","value","data_origin","checked_at_kst","warning"],
          ["SUMMARY","Opportunity records",len(opp)-1,"SFDC_Auto snapshot",now,"Snapshot is not live SFDC"],
          ["SUMMARY","Quotation snapshot records (active unverified)",len(quote)-1,"SFDC_Auto snapshot",now,"Do not sum as additional opportunities"],
          ["SUMMARY","Opportunity-CSS verified links",matched,"SFDC CSS Match Audit",now,"No verified AMEA links in previous audit"]]
    for metric,key in [("Opportunity name-unique Quote links","name_match_unique"),("Ambiguous Quote links","name_match_ambiguous"),("Unmatched Quote links","name_match_missing"),("Active confirmed Quotes","active"),("Active status unknown Quotes","unknown_status")]:
        rows.append(["QUOTE_RELATION",metric,link_metrics.get(key,"NOT_CHECKED"),"SFDC Quote Link Audit",now,
            "Name-only join is provisional; Active must be explicitly checked"])
    for k,n in sorted(stage.items()):rows.append(["OPPORTUNITY_STAGE",k,n,"Opportunity mirror",now,""])
    for k,n in sorted(qstage.items()):rows.append(["QUOTATION_STAGE (unverified)",k,n,"Quotation mirror",now,"Not Active Quote count"])
    root="https://sheets.googleapis.com/v4/spreadsheets/"+OUTPUT_ID
    meta=call(session,"GET",root+"?fields=sheets.properties",stage="overview_metadata")
    if TAB not in {s["properties"]["title"] for s in meta["sheets"]}:
        call(session,"POST",root+":batchUpdate",json={"requests":[{"addSheet":{"properties":{"title":TAB}}}]},stage="overview_create")
    replace_tab(session,TAB,rows)
    print(json.dumps({"status":"ok","opportunities":len(opp)-1,"quotations":len(quote)-1,
                      "opportunity_stage_categories":len(stage),"quotation_stage_categories":len(qstage)}))
if __name__=="__main__":main()
