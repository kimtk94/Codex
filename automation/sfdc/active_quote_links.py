#!/usr/bin/env python3
"""Strict Salesforce Opportunity/Quote related-ID reconciliation.
Only the Salesforce Active checkbox is authoritative; quote lifecycle status is separate.
"""
import json
from collections import Counter
from followup_stage1 import auth, call, OUTPUT_ID
from opportunity_quote_mirror import range_data, replace_tab

TAB="SFDC Active Quote Links"
AUDIT="SFDC Quote Link Audit"
HEAD=["sfdc_quotation_id","amea_quotation_id","opportunity_id","quote_name","quote_status","is_active","link_result","valid_quote","reason","matched_opportunity_name","match_method"]
def pick(h,options):
    normalized={str(k).strip().lower():i for i,k in enumerate(h)}
    for candidate in options:
        if candidate.lower() in normalized:return normalized[candidate.lower()]
    return None
def get(row,i):
    return str(row[i]).strip() if i is not None and i<len(row) and row[i] is not None else ""
def main():
    sess=auth()
    q=range_data(sess,OUTPUT_ID,"Quotation",2000)
    o=range_data(sess,OUTPUT_ID,"Opportunity",2000)
    if not q or not o: raise RuntimeError("Missing mirrored Opportunity/Quotation")
    qi=pick(q[0],["SFDC Quotation ID","Salesforce Quotation ID","Quote Record ID","Id"])
    amea=pick(q[0],["Quotation ID","AMEA No.","AMEA ID"])
    oi=pick(q[0],["Opportunity ID","OpportunityId","Opportunity: ID"])
    st=pick(q[0],["Quote Status","Quotation Status","Status"])
    active=pick(q[0],["IsActive","Is Active","Active","Is Active Quote"])
    name=pick(q[0],["Quote Name","Quotation Name","Name","Opportunity Name"])
    opportunity_id=pick(o[0],["Opportunity ID","OpportunityId","Id"])
    known={get(row,opportunity_id) for row in o[1:] if get(row,opportunity_id)} if opportunity_id is not None else set()
    def normalized(v):return " ".join(str(v or "").strip().casefold().split())
    qname=pick(q[0],["Opportunity Name"])
    oname=pick(o[0],["Opportunity Name"])
    names={}
    if oname is not None:
        for opp in o[1:]:
            key=normalized(get(opp,oname))
            if key:names.setdefault(key,[]).append(opp)
    rows=[HEAD];stats=Counter();match_stats=Counter()
    for row in q[1:]:
        status=get(row,st)
        flag=get(row,active).lower()
        valid="YES" if flag in ("true","yes","1","✓","✔","checked") else "NO" if flag in ("false","no","0","unchecked") else "UNKNOWN"
        qid=get(row,qi);oid=get(row,oi)
        candidates=names.get(normalized(get(row,qname)),[]) if qname is not None else []
        matched_name=""
        method="NONE"
        if oid and oid in known:
            link="MATCHED_BY_ID"
            method="OPPORTUNITY_ID"
        elif len(candidates)==1:
            link="NAME_MATCH_UNIQUE"
            matched_name=get(candidates[0],oname)
            method="EXACT_NORMALIZED_NAME"
        elif len(candidates)>1:
            link="NAME_AMBIGUOUS"
        else:
            link="NO_NAME_MATCH"
        match_stats[link]+=1
        reason=("missing Active checkbox" if valid=="UNKNOWN" else
                "not explicitly active" if valid=="NO" else
                "active but related Opportunity ID not verified" if link!="MATCHED" else "verified")
        rows.append([qid,get(row,amea),oid,get(row,name),status,flag,link,valid,reason,matched_name,method])
        stats[valid]+=1
    root="https://sheets.googleapis.com/v4/spreadsheets/"+OUTPUT_ID
    meta=call(sess,"GET",root+"?fields=sheets.properties",stage="quote_link_metadata")
    existing={item["properties"]["title"] for item in meta["sheets"]}
    requests=[{"addSheet":{"properties":{"title":tab,"hidden":True}}} for tab in (TAB,AUDIT) if tab not in existing]
    if requests:call(sess,"POST",root+":batchUpdate",json={"requests":requests},stage="quote_link_create")
    replace_tab(sess,TAB,rows)
    audit=[["metric","value"],["quote_rows",len(q)-1],["active",stats["YES"]],
           ["inactive",stats["NO"]],["unknown_status",stats["UNKNOWN"]],
           ["sfdc_quote_id_column_present",str(qi is not None)],["amea_quote_id_column_present",str(amea is not None)],["related_opportunity_id_column_present",str(oi is not None)],
           ["opportunity_id_column_present",str(opportunity_id is not None)],
           ["name_match_unique",match_stats["NAME_MATCH_UNIQUE"]],["name_match_ambiguous",match_stats["NAME_AMBIGUOUS"]],["name_match_missing",match_stats["NO_NAME_MATCH"]],["source","SFDC_Auto exported snapshot; not live Salesforce"]]
    replace_tab(sess,AUDIT,audit)
    print(json.dumps({"quote_rows":len(q)-1,"active":stats["YES"],"inactive":stats["NO"],
      "unknown":stats["UNKNOWN"],"related_ids_available":oi is not None and opportunity_id is not None}))
if __name__=="__main__":main()
